import pathlib
import re
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def github_action_documents(root=ROOT):
    workflows = root / ".github" / "workflows"
    actions = root / ".github" / "actions"
    return (
        sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]),
        sorted([*actions.glob("**/action.yml"), *actions.glob("**/action.yaml")]),
    )


def unquote_scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def yaml_scalar_values_for_key(path, key):
    script = r"""
require "psych"
raw = File.binread(ARGV.fetch(0))
raw.force_encoding(Encoding::UTF_8)
abort("invalid UTF-8") unless raw.valid_encoding?
target = ARGV.fetch(1)
tree = Psych.parse_stream(raw)
abort("YAML stream must contain exactly one document") unless tree.children.length == 1
values = []
walk = nil
walk = lambda do |node|
  if node.is_a?(Psych::Nodes::Mapping)
    node.children.each_slice(2) do |key_node, value_node|
      if key_node.is_a?(Psych::Nodes::Scalar) &&
         key_node.value == target &&
         value_node.is_a?(Psych::Nodes::Scalar)
        values << value_node.value
      end
      walk.call(value_node)
    end
    return
  end
  children = node.respond_to?(:children) ? node.children : nil
  Array(children).each { |child| walk.call(child) }
end
walk.call(tree)
STDOUT.write(values.join("\\0"))
STDOUT.write("\\0") unless values.empty?
"""
    result = subprocess.run(
        ["ruby", "--disable-gems", "-e", script, str(path), key],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{path}: YAML semantic scan failed with exit {result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return [
        value.decode("utf-8", errors="strict")
        for value in result.stdout.split(b"\\0")
        if value
    ]


def docker_action_image_values(path):
    return [
        value
        for value in yaml_scalar_values_for_key(path, "image")
        if value.startswith("docker://")
    ]


def immutable_uses_error(value):
    value = unquote_scalar(value)

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
            for value in yaml_scalar_values_for_key(document, "uses"):
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

    def test_docker_action_manifest_images_are_immutable(self):
        _, action_manifests = github_action_documents()
        for manifest in action_manifests:
            for value in docker_action_image_values(manifest):
                with self.subTest(
                    manifest=str(manifest.relative_to(ROOT)),
                    image=value,
                ):
                    self.assertIsNone(
                        immutable_uses_error(value),
                        f"{manifest.relative_to(ROOT)}: "
                        f"{immutable_uses_error(value)}",
                    )

    def test_docker_action_image_parser_covers_remote_images_only(self):
        digest = "c" * 64
        fixtures = {
            "pinned.yml": (
                "name: pinned\n"
                "runs: {using: docker, image: "
                f"'docker://ghcr.io/example/tool@sha256:{digest}'}}\n"
            ),
            "mutable.yml": (
                "name: mutable\n"
                "runs:\n"
                "  using: docker\n"
                "  image : docker://ghcr.io/example/tool:latest\n"
            ),
            "local.yml": (
                "name: local\n"
                "runs:\n"
                "  using: docker\n"
                "  image: Dockerfile\n"
            ),
        }
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            paths = {}
            for name, content in fixtures.items():
                path = root / name
                path.write_text(content, encoding="utf-8")
                paths[name] = path

            self.assertEqual(
                docker_action_image_values(paths["pinned.yml"]),
                [f"docker://ghcr.io/example/tool@sha256:{digest}"],
            )
            self.assertEqual(
                docker_action_image_values(paths["mutable.yml"]),
                ["docker://ghcr.io/example/tool:latest"],
            )
            self.assertEqual(docker_action_image_values(paths["local.yml"]), [])
            self.assertIsNone(
                immutable_uses_error(docker_action_image_values(paths["pinned.yml"])[0])
            )
            self.assertIsNotNone(
                immutable_uses_error(docker_action_image_values(paths["mutable.yml"])[0])
            )

    def test_yaml_semantic_scan_catches_quoted_spaced_and_flow_uses_keys(self):
        sha = "d" * 40
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            pinned = root / "pinned.yml"
            pinned.write_text(
                "jobs:\n"
                "  audit:\n"
                "    steps: [{\"uses\" : "
                f"\"actions/checkout@{sha}\"}}]\n",
                encoding="utf-8",
            )
            mutable = root / "mutable.yml"
            mutable.write_text(
                "jobs:\n"
                "  audit:\n"
                "    steps: [{uses : actions/checkout@v7}]\n",
                encoding="utf-8",
            )

            self.assertEqual(
                yaml_scalar_values_for_key(pinned, "uses"),
                [f"actions/checkout@{sha}"],
            )
            self.assertIsNone(
                immutable_uses_error(yaml_scalar_values_for_key(pinned, "uses")[0])
            )
            self.assertEqual(
                yaml_scalar_values_for_key(mutable, "uses"),
                ["actions/checkout@v7"],
            )
            self.assertIsNotNone(
                immutable_uses_error(yaml_scalar_values_for_key(mutable, "uses")[0])
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
