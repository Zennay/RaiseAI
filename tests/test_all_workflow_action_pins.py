import pathlib
import re
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ACTIONS = ROOT / ".github" / "actions"


def github_action_documents(root=ROOT):
    workflows = root / ".github" / "workflows"
    actions = root / ".github" / "actions"
    return (
        sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]),
        sorted([*actions.glob("**/action.yml"), *actions.glob("**/action.yaml")]),
    )


def immutable_uses_error(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]

    if value.startswith("./"):
        return None

    if value.startswith("docker://"):
        image = value.removeprefix("docker://")
        name, separator, digest = image.rpartition("@sha256:")
        if not separator or not name or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return (
                f"{value} must pin docker:// images by an immutable "
                "sha256 digest"
            )
        return None

    action, separator, ref = value.rpartition("@")
    if separator != "@" or not action:
        return f"{value} must include an immutable revision"
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        return f"{value} must use an immutable 40-character commit SHA"
    return None


class AllWorkflowActionPinsTests(unittest.TestCase):
    def test_every_remote_uses_ref_is_immutable(self):
        workflows, action_manifests = github_action_documents()
        self.assertTrue(workflows, "repository must retain GitHub Actions workflows")

        remote_refs = []
        for document in [*workflows, *action_manifests]:
            text = document.read_text(encoding="utf-8")
            for match in re.finditer(
                r"^\s*(?:-\s*)?uses:\s*([^\s#]+)",
                text,
                flags=re.MULTILINE,
            ):
                value = match.group(1)
                if value.startswith("./"):
                    continue
                remote_refs.append((str(document.relative_to(ROOT)), value))

        self.assertTrue(remote_refs, "repository must retain at least one remote action")
        for document, value in remote_refs:
            with self.subTest(document=document, uses=value):
                self.assertIsNone(
                    immutable_uses_error(value),
                    f"{document}: {immutable_uses_error(value)}",
                )

    def test_composite_action_manifest_discovery_is_recursive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            workflow = root / ".github" / "workflows" / "quality.yml"
            nested_yaml = root / ".github" / "actions" / "nested" / "action.yaml"
            nested_yml = root / ".github" / "actions" / "deeper" / "check" / "action.yml"
            ignored = root / ".github" / "actions" / "nested" / "README.md"
            for document in (workflow, nested_yaml, nested_yml, ignored):
                document.parent.mkdir(parents=True, exist_ok=True)
                document.write_text("name: fixture\n", encoding="utf-8")

            workflows, action_manifests = github_action_documents(root)

            self.assertEqual(
                [path.relative_to(root).as_posix() for path in workflows],
                [".github/workflows/quality.yml"],
            )
            self.assertEqual(
                [path.relative_to(root).as_posix() for path in action_manifests],
                [
                    ".github/actions/deeper/check/action.yml",
                    ".github/actions/nested/action.yaml",
                ],
            )

    def test_docker_uses_requires_sha256_digest(self):
        digest = "a" * 64
        self.assertIsNone(immutable_uses_error(f"docker://alpine@sha256:{digest}"))

        for value in (
            "docker://alpine:3.20",
            "docker://alpine@latest",
            "docker://alpine@sha256:abc123",
            "docker://@sha256:" + digest,
        ):
            with self.subTest(uses=value):
                self.assertIsNotNone(immutable_uses_error(value))

    def test_quoted_remote_refs_are_validated_after_unquoting(self):
        sha = "b" * 40
        self.assertIsNone(immutable_uses_error(f'"actions/checkout@{sha}"'))
        self.assertIsNone(immutable_uses_error(f"'actions/checkout@{sha}'"))
        self.assertIsNotNone(immutable_uses_error('"actions/checkout@v7"'))


if __name__ == "__main__":
    unittest.main()
