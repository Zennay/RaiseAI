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


def executable_uses_values(path, kind):
    script = r"""
require "psych"
raw = File.binread(ARGV.fetch(0))
raw.force_encoding(Encoding::UTF_8)
abort("invalid UTF-8") unless raw.valid_encoding?
kind = ARGV.fetch(1)
tree = Psych.parse_stream(raw)
abort("YAML stream must contain exactly one document") unless tree.children.length == 1
root = tree.children.fetch(0).root
abort("GitHub Actions document root must be a mapping") unless root.is_a?(Psych::Nodes::Mapping)

lookup = lambda do |mapping, target|
  next nil unless mapping.is_a?(Psych::Nodes::Mapping)
  mapping.children.each_slice(2) do |key_node, value_node|
    next unless key_node.is_a?(Psych::Nodes::Scalar)
    return value_node if key_node.value == target
  end
  nil
end

values = []
append_uses = lambda do |mapping, context|
  uses = lookup.call(mapping, "uses")
  next unless uses
  abort("#{context} uses must be a scalar") unless uses.is_a?(Psych::Nodes::Scalar)
  values << uses.value
end
append_steps = lambda do |steps, context|
  next unless steps
  abort("#{context} steps must be a sequence") unless steps.is_a?(Psych::Nodes::Sequence)
  steps.children.each do |step|
    abort("#{context} steps must be mappings") unless step.is_a?(Psych::Nodes::Mapping)
    append_uses.call(step, "#{context} step")
  end
end

case kind
when "workflow"
  jobs = lookup.call(root, "jobs")
  if jobs
    abort("workflow jobs must be a mapping") unless jobs.is_a?(Psych::Nodes::Mapping)
    jobs.children.each_slice(2) do |job_name, job|
      abort("workflow job names must be scalars") unless job_name.is_a?(Psych::Nodes::Scalar)
      abort("workflow jobs must be mappings") unless job.is_a?(Psych::Nodes::Mapping)
      append_uses.call(job, "workflow job")
      append_steps.call(lookup.call(job, "steps"), "workflow job")
    end
  end
when "action"
  runs = lookup.call(root, "runs")
  if runs
    abort("action runs must be a mapping") unless runs.is_a?(Psych::Nodes::Mapping)
    append_steps.call(lookup.call(runs, "steps"), "composite action")
  end
else
  abort("unknown GitHub Actions document kind")
end

STDOUT.write(values.join("\\0"))
STDOUT.write("\\0") unless values.empty?
"""
    result = subprocess.run(
        ["ruby", "--disable-gems", "-e", script, str(path), kind],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{path}: executable uses scan failed with exit {result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return [
        value.decode("utf-8", errors="strict")
        for value in result.stdout.split(b"\\0")
        if value
    ]


def docker_action_image_values(path):
    script = r"""
require "psych"
raw = File.binread(ARGV.fetch(0))
raw.force_encoding(Encoding::UTF_8)
abort("invalid UTF-8") unless raw.valid_encoding?
tree = Psych.parse_stream(raw)
abort("YAML stream must contain exactly one document") unless tree.children.length == 1
root = tree.children.fetch(0).root
abort("action manifest root must be a mapping") unless root.is_a?(Psych::Nodes::Mapping)

lookup = lambda do |mapping, target|
  next nil unless mapping.is_a?(Psych::Nodes::Mapping)
  mapping.children.each_slice(2) do |key_node, value_node|
    next unless key_node.is_a?(Psych::Nodes::Scalar)
    return value_node if key_node.value == target
  end
  nil
end

value = nil
runs = lookup.call(root, "runs")
if runs
  abort("action runs must be a mapping") unless runs.is_a?(Psych::Nodes::Mapping)
  image = lookup.call(runs, "image")
  if image
    abort("action runs.image must be a scalar") unless image.is_a?(Psych::Nodes::Scalar)
    value = image.value if image.value.start_with?("docker://")
  end
end

STDOUT.write(value) if value
STDOUT.write("\\0") if value
"""
    result = subprocess.run(
        ["ruby", "--disable-gems", "-e", script, str(path)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{path}: Docker action image scan failed with exit {result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return [
        value.decode("utf-8", errors="strict")
        for value in result.stdout.split(b"\\0")
        if value
    ]



def workflow_container_image_values(path):
    script = r"""
require "psych"
raw = File.binread(ARGV.fetch(0))
raw.force_encoding(Encoding::UTF_8)
abort("invalid UTF-8") unless raw.valid_encoding?
tree = Psych.parse_stream(raw)
abort("YAML stream must contain exactly one document") unless tree.children.length == 1
root = tree.children.fetch(0).root
abort("workflow root must be a mapping") unless root.is_a?(Psych::Nodes::Mapping)

lookup = lambda do |mapping, target|
  next nil unless mapping.is_a?(Psych::Nodes::Mapping)
  found = nil
  mapping.children.each_slice(2) do |key_node, value_node|
    if key_node.is_a?(Psych::Nodes::Scalar) && key_node.value == target
      found = value_node
      break
    end
  end
  found
end

values = []
jobs = lookup.call(root, "jobs")
if jobs
  abort("workflow jobs must be a mapping") unless jobs.is_a?(Psych::Nodes::Mapping)
  jobs.children.each_slice(2) do |_job_name, job|
    next unless job.is_a?(Psych::Nodes::Mapping)

    container = lookup.call(job, "container")
    if container.is_a?(Psych::Nodes::Scalar)
      values << container.value
    elsif container
      abort("job container must be a scalar or mapping") unless container.is_a?(Psych::Nodes::Mapping)
      image = lookup.call(container, "image")
      if image
        abort("job container image must be a scalar") unless image.is_a?(Psych::Nodes::Scalar)
        values << image.value
      end
    end

    services = lookup.call(job, "services")
    if services
      abort("job services must be a mapping") unless services.is_a?(Psych::Nodes::Mapping)
      services.children.each_slice(2) do |_service_name, service|
        abort("service definition must be a mapping") unless service.is_a?(Psych::Nodes::Mapping)
        image = lookup.call(service, "image")
        next unless image
        abort("service image must be a scalar") unless image.is_a?(Psych::Nodes::Scalar)
        values << image.value
      end
    end
  end
end

STDOUT.write(values.join("\\0"))
STDOUT.write("\\0") unless values.empty?
"""
    result = subprocess.run(
        ["ruby", "--disable-gems", "-e", script, str(path)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{path}: workflow container scan failed with exit {result.returncode}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return [
        value.decode("utf-8", errors="strict")
        for value in result.stdout.split(b"\\0")
        if value
    ]


def immutable_container_image_error(value):
    value = unquote_scalar(value)
    name, separator, digest = value.rpartition("@sha256:")
    if not separator or not name or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return f"{value} must pin workflow container images by an immutable sha256 digest"
    return None


def local_uses_error(value, root=ROOT):
    value = unquote_scalar(value)
    if not value.startswith("./"):
        return None

    relative = value[2:]
    segments = relative.split("/")
    if not relative or "\\" in relative or any(
        segment in {"", ".", ".."} for segment in segments
    ):
        return f"{value} must use a canonical repository-relative local path"

    target = root.joinpath(*segments)
    if target.is_symlink():
        return f"{value} must not resolve through a symlinked local target"

    if target.is_file():
        workflows = root / ".github" / "workflows"
        if target.parent != workflows or target.suffix not in {".yml", ".yaml"}:
            return (
                f"{value} local file target must be a top-level reusable workflow "
                "under .github/workflows"
            )
        return None

    if target.is_dir():
        manifests = [
            candidate
            for candidate in (target / "action.yml", target / "action.yaml")
            if candidate.exists()
        ]
        if len(manifests) != 1:
            return (
                f"{value} local action directory must contain exactly one "
                "action.yml or action.yaml manifest"
            )
        manifest = manifests[0]
        if manifest.is_symlink() or not manifest.is_file():
            return f"{value} local action manifest must be a regular file"
        return None

    return f"{value} local action target must exist in the repository"

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
    def test_workflow_container_images_are_immutable(self):
        workflows, _ = github_action_documents()
        for workflow in workflows:
            for value in workflow_container_image_values(workflow):
                with self.subTest(
                    workflow=str(workflow.relative_to(ROOT)),
                    image=value,
                ):
                    self.assertIsNone(
                        immutable_container_image_error(value),
                        f"{workflow.relative_to(ROOT)}: "
                        f"{immutable_container_image_error(value)}",
                    )

    def test_workflow_container_image_parser_covers_block_flow_and_shorthand(self):
        digest = "e" * 64
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            pinned = root / "pinned.yml"
            pinned.write_text(
                "jobs:\n"
                "  block:\n"
                "    container:\n"
                f"      image: ghcr.io/example/build@sha256:{digest}\n"
                "    services:\n"
                f"      redis: {{image: redis@sha256:{digest}}}\n"
                "  shorthand:\n"
                f"    container: alpine@sha256:{digest}\n",
                encoding="utf-8",
            )
            mutable = root / "mutable.yml"
            mutable.write_text(
                "jobs:\n"
                "  block:\n"
                "    container: ubuntu:24.04\n"
                "    services:\n"
                "      redis:\n"
                "        image: redis:7\n",
                encoding="utf-8",
            )
            unrelated = root / "unrelated.yml"
            unrelated.write_text(
                "image: ubuntu:latest\n"
                "jobs:\n"
                "  audit:\n"
                "    steps:\n"
                "      - run: echo ok\n"
                "        with:\n"
                "          image: redis:latest\n"
                "          container: alpine:latest\n",
                encoding="utf-8",
            )

            pinned_values = workflow_container_image_values(pinned)
            self.assertEqual(
                set(pinned_values),
                {
                    f"ghcr.io/example/build@sha256:{digest}",
                    f"redis@sha256:{digest}",
                    f"alpine@sha256:{digest}",
                },
            )
            for value in pinned_values:
                self.assertIsNone(immutable_container_image_error(value))

            mutable_values = workflow_container_image_values(mutable)
            self.assertEqual(set(mutable_values), {"ubuntu:24.04", "redis:7"})
            for value in mutable_values:
                self.assertIsNotNone(immutable_container_image_error(value))

            self.assertEqual(
                workflow_container_image_values(unrelated),
                [],
                "unrelated image/container keys outside job container/service positions "
                "must not be treated as executable workflow container images",
            )

    def test_every_local_uses_ref_is_canonical_and_resolvable(self):
        workflows, action_manifests = github_action_documents()

        for document, kind in [
            *((workflow, "workflow") for workflow in workflows),
            *((manifest, "action") for manifest in action_manifests),
        ]:
            for value in executable_uses_values(document, kind):
                if not value.startswith("./"):
                    continue
                with self.subTest(
                    document=str(document.relative_to(ROOT)),
                    uses=value,
                ):
                    self.assertIsNone(
                        local_uses_error(value),
                        f"{document.relative_to(ROOT)}: {local_uses_error(value)}",
                    )

    def test_local_uses_validator_rejects_escape_missing_and_ambiguous_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            workflows = root / ".github" / "workflows"
            action = root / ".github" / "actions" / "check"
            workflows.mkdir(parents=True)
            action.mkdir(parents=True)
            (workflows / "reuse.yml").write_text("name: reuse\n", encoding="utf-8")
            (action / "action.yml").write_text("name: check\n", encoding="utf-8")

            self.assertIsNone(
                local_uses_error("./.github/workflows/reuse.yml", root=root)
            )
            self.assertIsNone(
                local_uses_error("./.github/actions/check", root=root)
            )

            for value in (
                "./../outside",
                "./missing",
                "./.github//actions/check",
                "./.github/workflows/../actions/check",
            ):
                with self.subTest(value=value):
                    self.assertIsNotNone(local_uses_error(value, root=root))

            (action / "action.yaml").write_text("name: duplicate\n", encoding="utf-8")
            self.assertIsNotNone(
                local_uses_error("./.github/actions/check", root=root)
            )

    def test_every_remote_uses_ref_is_immutable(self):
        workflows, action_manifests = github_action_documents()
        self.assertTrue(workflows, "repository must retain GitHub Actions workflows")

        remote_refs = []
        for document, kind in [
            *((workflow, "workflow") for workflow in workflows),
            *((manifest, "action") for manifest in action_manifests),
        ]:
            for value in executable_uses_values(document, kind):
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
            "lookalike.yml": (
                "name: lookalike\n"
                "inputs:\n"
                "  image:\n"
                "    default: docker://ghcr.io/example/unrelated:latest\n"
                "runs: {using: node20, main: index.js}\n"
            ),
            "invalid.yml": (
                "name: invalid\n"
                "runs: {using: docker, image: {repo: example/tool}}\n"
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
            self.assertEqual(
                docker_action_image_values(paths["lookalike.yml"]),
                [],
                "non-runs image keys must not be treated as executable Docker action images",
            )
            with self.assertRaisesRegex(RuntimeError, "runs.image must be a scalar"):
                docker_action_image_values(paths["invalid.yml"])
            self.assertIsNone(
                immutable_uses_error(docker_action_image_values(paths["pinned.yml"])[0])
            )
            self.assertIsNotNone(
                immutable_uses_error(docker_action_image_values(paths["mutable.yml"])[0])
            )

    def test_semantic_uses_scan_is_scoped_to_executable_workflow_positions(self):
        sha = "d" * 40
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            workflow = root / "workflow.yml"
            workflow.write_text(
                "uses: ignored/top-level@v1\n"
                "jobs:\n"
                "  reusable:\n"
                f"    uses: owner/repo/.github/workflows/reuse.yml@{sha}\n"
                "  audit:\n"
                "    env: {uses: ignored/env@v1}\n"
                "    steps:\n"
                f"      - {{\"uses\" : \"actions/checkout@{sha}\", "
                "with: {uses: ignored/input@v1}}\n",
                encoding="utf-8",
            )

            self.assertEqual(
                executable_uses_values(workflow, "workflow"),
                [
                    f"owner/repo/.github/workflows/reuse.yml@{sha}",
                    f"actions/checkout@{sha}",
                ],
            )

    def test_semantic_uses_scan_is_scoped_to_composite_action_steps(self):
        sha = "e" * 40
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            manifest = root / "action.yml"
            manifest.write_text(
                "name: fixture\n"
                "inputs: {uses: {default: ignored/input@v1}}\n"
                "runs:\n"
                "  using: composite\n"
                "  steps:\n"
                f"    - uses: owner/action@{sha}\n"
                "      with: {uses: ignored/nested@v1}\n",
                encoding="utf-8",
            )
            self.assertEqual(
                executable_uses_values(manifest, "action"),
                [f"owner/action@{sha}"],
            )

    def test_semantic_uses_scan_fails_closed_on_non_scalar_executable_uses(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            workflow = root / "invalid.yml"
            workflow.write_text(
                "jobs: {audit: {steps: [{uses: {repo: action}}]}}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "uses must be a scalar"):
                executable_uses_values(workflow, "workflow")

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
