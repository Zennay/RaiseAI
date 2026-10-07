import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "css-surface-contract.yml"
EXPECTED_CRITICAL = {"app/src/main/assets/raiseai_wear/wear.css"}
BIDI_CONTROL_RE = re.compile("[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def tracked_css_paths() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        item
        for item in raw.decode("utf-8").split("\0")
        if item and pathlib.PurePosixPath(item).suffix.lower() == ".css"
    )


def _visible_css_code(text: str, *, label: str) -> str:
    visible: list[str] = []
    index = 0
    state = "code"
    quote = ""

    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""

        if state == "comment":
            if char == "*" and nxt == "/":
                visible.extend((" ", " "))
                state = "code"
                index += 2
                continue
            visible.append("\n" if char == "\n" else " ")
            index += 1
            continue

        if state == "string":
            if char == "\\":
                visible.append(" ")
                if index + 1 >= len(text):
                    raise ValueError(f"{label}: unterminated escape in CSS string")
                visible.append("\n" if nxt == "\n" else " ")
                index += 2
                continue
            if char == quote:
                visible.append(" ")
                state = "code"
                quote = ""
                index += 1
                continue
            if char == "\n":
                raise ValueError(f"{label}: unescaped newline in CSS string")
            visible.append(" ")
            index += 1
            continue

        if char == "/" and nxt == "*":
            visible.extend((" ", " "))
            state = "comment"
            index += 2
            continue
        if char in {'"', "'"}:
            visible.append(" ")
            state = "string"
            quote = char
            index += 1
            continue

        visible.append(char)
        index += 1

    if state == "comment":
        raise ValueError(f"{label}: unterminated CSS comment")
    if state == "string":
        raise ValueError(f"{label}: unterminated CSS string")

    return "".join(visible)



def _css_url_targets(text: str, *, label: str) -> list[str]:
    targets: list[str] = []
    index = 0
    state = "code"
    quote = ""

    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""

        if state == "comment":
            if char == "*" and nxt == "/":
                state = "code"
                index += 2
            else:
                index += 1
            continue

        if state == "string":
            if char == "\\":
                index += 2
                continue
            if char == quote:
                state = "code"
                quote = ""
            index += 1
            continue

        if char == "/" and nxt == "*":
            state = "comment"
            index += 2
            continue
        if char in {'"', "'"}:
            state = "string"
            quote = char
            index += 1
            continue

        if text[index:index + 3].lower() == "url":
            before = text[index - 1] if index else ""
            if before and (before.isalnum() or before in "_-"):
                index += 1
                continue

            cursor = index + 3
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor >= len(text) or text[cursor] != "(":
                index += 1
                continue

            cursor += 1
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor >= len(text):
                raise ValueError(f"{label}: unterminated CSS url()")

            if text[cursor] in {'"', "'"}:
                arg_quote = text[cursor]
                cursor += 1
                value: list[str] = []
                while cursor < len(text):
                    current = text[cursor]
                    if current == "\\":
                        raise ValueError(
                            f"{label}: CSS url() escapes are forbidden; "
                            "use a literal local or data URL"
                        )
                    if current == arg_quote:
                        cursor += 1
                        break
                    if current == "\n":
                        raise ValueError(f"{label}: unescaped newline in CSS url()")
                    value.append(current)
                    cursor += 1
                else:
                    raise ValueError(f"{label}: unterminated quoted CSS url()")

                while cursor < len(text) and text[cursor].isspace():
                    cursor += 1
                if cursor >= len(text) or text[cursor] != ")":
                    raise ValueError(f"{label}: malformed quoted CSS url()")
                targets.append("".join(value).strip())
                index = cursor + 1
                continue

            start = cursor
            while cursor < len(text) and text[cursor] != ")":
                if text[cursor] == "\\":
                    raise ValueError(
                        f"{label}: CSS url() escapes are forbidden; "
                        "use a literal local or data URL"
                    )
                if text[cursor] in {'"', "'", "(", "\n"}:
                    raise ValueError(f"{label}: malformed unquoted CSS url()")
                cursor += 1
            if cursor >= len(text):
                raise ValueError(f"{label}: unterminated CSS url()")
            targets.append(text[start:cursor].strip())
            index = cursor + 1
            continue

        index += 1

    return targets

def validate_css_source(data: bytes, *, label: str) -> None:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label}: CSS source must be strict UTF-8") from exc

    if text.startswith("\ufeff"):
        raise ValueError(f"{label}: CSS source must not start with a UTF-8 BOM")
    if "\x00" in text:
        raise ValueError(f"{label}: CSS source must not contain NUL characters")
    if "\r" in text:
        raise ValueError(f"{label}: CSS source must use LF line endings")
    if BIDI_CONTROL_RE.search(text):
        raise ValueError(f"{label}: CSS source must not contain bidirectional control characters")

    visible = _visible_css_code(text, label=label)
    if "\\" in visible:
        raise ValueError(
            f"{label}: CSS escapes outside strings are forbidden; "
            "use literal reviewable tokens"
        )
    if re.search(r"(?i)(?<![-_a-z0-9])@import\b", visible):
        raise ValueError(f"{label}: CSS @import is forbidden; bundle assets locally")
    if re.search(
        r"(?i)(?<![-_a-z0-9])(?:image-set|-webkit-image-set|image)\s*\(",
        visible,
    ):
        raise ValueError(
            f"{label}: CSS image()/image-set() string URL surfaces are forbidden; "
            "use audited url() targets"
        )

    for target in _css_url_targets(text, label=label):
        lowered = target.lower()
        scheme = re.match(r"^[a-z][a-z0-9+.-]*:", target, flags=re.IGNORECASE)
        if lowered.startswith("//") or (scheme and not lowered.startswith("data:")):
            raise ValueError(
                f"{label}: remote or opaque CSS url() schemes are forbidden; "
                "use relative or data URLs"
            )

    stack: list[tuple[str, int]] = []
    pairs = {"}": "{", ")": "(", "]": "["}
    for index, char in enumerate(visible):
        if char in "{([":
            stack.append((char, index))
        elif char in "})]":
            expected = pairs[char]
            if not stack or stack[-1][0] != expected:
                raise ValueError(
                    f"{label}: unmatched CSS delimiter {char!r} at character {index}"
                )
            stack.pop()

    if stack:
        opener, index = stack[-1]
        raise ValueError(
            f"{label}: unclosed CSS delimiter {opener!r} at character {index}"
        )


class CssSurfaceContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_tracked_css_surface_is_nonempty_and_includes_wear_asset(self):
        paths = tracked_css_paths()
        self.assertTrue(paths, "tracked CSS discovery must find files")
        self.assertTrue(
            EXPECTED_CRITICAL.issubset(paths),
            f"critical CSS missing from discovery: {sorted(EXPECTED_CRITICAL - set(paths))}",
        )

    def test_every_tracked_css_file_is_regular_canonical_and_structurally_valid(self):
        for relative in tracked_css_paths():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertFalse(
                    path.is_symlink(),
                    f"{relative} must be a regular repository file, not a symlink",
                )
                self.assertTrue(path.is_file(), f"{relative} must resolve to a regular file")
                validate_css_source(path.read_bytes(), label=relative)

    def test_validator_accepts_balanced_local_css(self):
        validate_css_source(
            b'/* ok */\n.a[data-x="]"] { width: calc(100% - 2px); background: url("data:image/svg+xml,%3Csvg%3E"); }\n',
            label="fixture.css",
        )

    def test_validator_rejects_encoding_and_line_ending_ambiguity(self):
        cases = (
            (b"safe \xff", "strict UTF-8"),
            ("\ufeff.a {}".encode("utf-8"), "UTF-8 BOM"),
            (b".a {\r\n  color: red;\r\n}\r\n", "LF line endings"),
            (b".a { color: red;\x00 }", "NUL"),
            (".a { content: \"safe\u202eunsafe\"; }\n".encode("utf-8"), "bidirectional control"),
        )
        for payload, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    validate_css_source(payload, label="fixture.css")

    def test_validator_rejects_unbalanced_or_unterminated_css(self):
        cases = (
            (b".a { color: red;", "unclosed CSS delimiter"),
            (b".a { color: red; }}", "unmatched CSS delimiter"),
            (b".a { content: \"oops; }", "unterminated CSS string"),
            (b".a { /* oops", "unterminated CSS comment"),
        )
        for payload, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    validate_css_source(payload, label="fixture.css")

    def test_validator_rejects_remote_import_surface_but_ignores_comments_and_strings(self):
        with self.assertRaisesRegex(ValueError, "@import"):
            validate_css_source(
                b'@import url("https://example.invalid/remote.css");\n.a {}\n',
                label="fixture.css",
            )
        validate_css_source(
            b'/* @import url("https://example.invalid/x.css"); */\n.a { content: "@import"; }\n',
            label="fixture.css",
        )

    def test_validator_rejects_escaped_css_tokens_that_can_hide_fetches(self):
        cases = (
            (b"@\\69mport url(local.css);\n.a {}\n", "escapes outside strings"),
            (b'.a { background: url("https\\://example.invalid/x.png"); }\n', "url\\(\\) escapes"),
            (b".a { background: url(https\\://example.invalid/x.png); }\n", "escapes outside strings"),
        )
        for payload, expected in cases:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, expected):
                    validate_css_source(payload, label="fixture.css")

    def test_validator_rejects_string_url_image_functions(self):
        for function in ("image", "image-set", "-webkit-image-set"):
            with self.subTest(function=function):
                payload = (
                    f'.a {{ background-image: {function}("https://example.invalid/x.png" 1x); }}\n'
                    if "image-set" in function
                    else f'.a {{ background-image: {function}("https://example.invalid/x.png"); }}\n'
                ).encode("utf-8")
                with self.assertRaisesRegex(ValueError, "string URL surfaces"):
                    validate_css_source(payload, label="fixture.css")

        validate_css_source(
            b'/* image("https://example.invalid/x.png") */\n'
            b'.a { content: "image-set(https://example.invalid/x.png)"; }\n',
            label="fixture.css",
        )

    def test_validator_rejects_remote_url_assets_but_allows_local_and_data_targets(self):
        for target in (
            "https://example.invalid/font.woff2",
            "http://example.invalid/image.png",
            "ftp://example.invalid/image.png",
            "file:///tmp/image.png",
            "blob:https://example.invalid/1234",
            "custom-scheme:asset",
            "//cdn.example.invalid/image.png",
        ):
            with self.subTest(target=target):
                payload = f'.a {{ background: url("{target}"); }}\n'.encode("utf-8")
                with self.assertRaisesRegex(ValueError, "remote or opaque CSS url"):
                    validate_css_source(payload, label="fixture.css")

        for payload in (
            b'.a { background: url("local/icon.svg"); }\n',
            b".a { background: url(../icon.svg); }\n",
            b'.a { background: url("data:image/svg+xml,%3Csvg%3E"); }\n',
            b'.a { background: url("/assets/icon.svg"); }\n',
            b'.a { filter: url("#local-filter"); }\n',
            b'.a { content: "url(https://example.invalid/not-a-fetch)"; }\n',
            b'/* url(https://example.invalid/not-a-fetch) */ .a {}\n',
        ):
            with self.subTest(payload=payload):
                validate_css_source(payload, label="fixture.css")

    def _trigger_paths(self, event: str) -> list[str]:
        lines = self.workflow.splitlines()
        start = lines.index(f"  {event}:") + 1
        body = []
        for line in lines[start:]:
            if line and not line.startswith("    "):
                break
            body.append(line)
        self.assertIn("    paths:", body)
        index = body.index("    paths:") + 1
        paths = []
        for line in body[index:]:
            match = re.fullmatch(r'      - "([^"]+)"', line)
            if not match:
                break
            paths.append(match.group(1))
        return paths

    def test_workflow_triggers_cover_current_and_future_css_surfaces(self):
        expected = [
            "*.css",
            "**/*.css",
            "tests/test_css_surface_contract.py",
            ".github/workflows/css-surface-contract.yml",
        ]
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                self.assertEqual(self._trigger_paths(event), expected)

    def test_workflow_is_hosted_read_only_exact_head_bounded_and_secret_free(self):
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        self.assertNotIn("self-hosted", self.workflow)
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotRegex(self.workflow, r"\$\{\{\s*secrets\.")
        self.assertNotIn("pull_request_target:", self.workflow)
        self.assertNotIn("continue-on-error: true", self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^\s+if:\s*")
        self.assertIn("timeout-minutes: 5", self.workflow)
        self.assertIn("cancel-in-progress: true", self.workflow)
        expression = (
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}"
        )
        self.assertEqual(self.workflow.count(expression), 2)
        self.assertIn("persist-credentials: false", self.workflow)
        self.assertEqual(
            self.workflow.count('          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"'),
            1,
        )

    def test_workflow_uses_only_immutable_checkout_action(self):
        refs = re.findall(
            r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)",
            self.workflow,
            flags=re.MULTILINE,
        )
        self.assertEqual([action for action, _ in refs], ["actions/checkout"])
        self.assertRegex(refs[0][1], r"^[0-9a-f]{40}$")
        self.assertIn(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            self.workflow,
        )

    def test_workflow_runs_contract_and_keeps_worktree_clean(self):
        for token in (
            "python3 -m unittest tests.test_css_surface_contract",
            "git diff --exit-code -- .",
            'test -z "$(git ls-files --others --exclude-standard)"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.workflow)

    def test_workflow_rejects_quoted_mapping_keys(self):
        quoted_mapping_key = re.compile(
            r'''(?m)^ {0,10}(?:"[A-Za-z0-9_-]+"|'[A-Za-z0-9_-]+')\s*:'''
        )
        fixtures = (
            '        "continue-on-error": true',
            "        'working-directory': /tmp",
            '    "timeout-minutes": 30',
            "  'pull_request_target':",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertRegex(
                    fixture,
                    quoted_mapping_key,
                    "regression fixture must exercise the quoted-key detector",
                )

        self.assertNotRegex(
            self.workflow,
            quoted_mapping_key,
            "quoted YAML mapping keys can bypass the CSS workflow exact-surface parsers",
        )


    def test_all_run_steps_are_explicit_strict_bash(self):
        lines = self.workflow.splitlines()
        run_indices = [index for index, line in enumerate(lines) if line == "        run: |"]
        self.assertTrue(run_indices)
        step_starts = [
            index for index, line in enumerate(lines) if line.startswith("      - name:")
        ]
        for run_index in run_indices:
            with self.subTest(line=run_index + 1):
                step_start = max(index for index in step_starts if index < run_index)
                following = [index for index in step_starts if index > step_start]
                step_end = min(following) if following else len(lines)
                step = lines[step_start:step_end]
                self.assertIn("        shell: bash", step)
                self.assertEqual(lines[run_index + 1], "          set -euo pipefail")


    def test_workflow_keeps_exact_top_level_and_job_surfaces(self):
        lines = self.workflow.splitlines()
        top_level = []
        for line in lines:
            match = re.fullmatch(r"([A-Za-z0-9_-]+):.*", line)
            if match:
                top_level.append(match.group(1))
        self.assertEqual(
            top_level,
            ["name", "on", "permissions", "concurrency", "jobs"],
        )
        self.assertEqual(lines[0], "name: CSS surface contract CI")

        jobs_block = self.workflow.split("\njobs:\n", 1)[1]
        job_keys = []
        for line in jobs_block.splitlines()[1:]:
            match = re.fullmatch(r"    ([A-Za-z0-9_-]+):.*", line)
            if match:
                job_keys.append(match.group(1))
        self.assertEqual(job_keys, ["runs-on", "timeout-minutes", "env", "steps"])

    def test_workflow_trigger_concurrency_and_env_surfaces_are_exact(self):
        lines = self.workflow.splitlines()

        on_start = lines.index("on:") + 1
        permissions_start = lines.index("permissions:")
        events = [
            match.group(1)
            for line in lines[on_start:permissions_start]
            if (match := re.fullmatch(r"  ([A-Za-z0-9_-]+):", line))
        ]
        self.assertEqual(events, ["push", "pull_request"])

        def event_block(event):
            start = lines.index(f"  {event}:") + 1
            block = []
            for line in lines[start:]:
                if line and not line.startswith("    "):
                    break
                block.append(line)
            return block

        push = event_block("push")
        self.assertEqual(
            [
                match.group(1)
                for line in push
                if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):", line))
            ],
            ["branches", "paths"],
        )
        branches_start = push.index("    branches:") + 1
        self.assertEqual(push[branches_start], "      - main")

        pull_request = event_block("pull_request")
        self.assertEqual(
            [
                match.group(1)
                for line in pull_request
                if (match := re.fullmatch(r"    ([A-Za-z0-9_-]+):", line))
            ],
            ["paths"],
            "pull_request must not gain type or branch filters that can skip synchronize validation",
        )

        concurrency_start = lines.index("concurrency:") + 1
        jobs_start = lines.index("jobs:")
        self.assertEqual(
            [
                match.group(1)
                for line in lines[concurrency_start:jobs_start]
                if (match := re.fullmatch(r"  ([A-Za-z0-9_-]+):.*", line))
            ],
            ["group", "cancel-in-progress"],
        )

        env_start = lines.index("    env:") + 1
        env_keys = []
        for line in lines[env_start:]:
            match = re.fullmatch(r"      ([A-Za-z0-9_-]+):.*", line)
            if match:
                env_keys.append(match.group(1))
                continue
            break
        self.assertEqual(
            env_keys,
            [
                "LANG",
                "LC_ALL",
                "PYTHONHASHSEED",
                "PYTHONNOUSERSITE",
                "PYTHONDONTWRITEBYTECODE",
                "TZ",
            ],
            "CSS parser environment must not gain unreviewed interpreter controls",
        )
        expected_env_lines = [
            "      LANG: C.UTF-8",
            "      LC_ALL: C.UTF-8",
            '      PYTHONHASHSEED: "1"',
            '      PYTHONNOUSERSITE: "1"',
            '      PYTHONDONTWRITEBYTECODE: "1"',
            "      TZ: UTC",
        ]
        self.assertEqual(
            lines[env_start : env_start + len(expected_env_lines)],
            expected_env_lines,
            "CSS parser environment values must remain deterministic",
        )

    def test_workflow_step_and_nested_mapping_surfaces_are_exact(self):
        lines = self.workflow.splitlines()
        step_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith("      - name:")
        ]
        expected_names = [
            "Checkout exact tested revision",
            "Verify exact tested revision",
            "Verify Python runtime",
            "Validate tracked CSS surface",
            "Verify worktree remains clean",
        ]
        self.assertEqual(
            [lines[index].removeprefix("      - name: ") for index in step_starts],
            expected_names,
            "CSS surface workflow must not gain unreviewed steps",
        )

        expected_keys = {
            "Checkout exact tested revision": ["name", "uses", "with"],
            "Verify exact tested revision": ["name", "shell", "env", "run"],
            "Verify Python runtime": ["name", "shell", "run"],
            "Validate tracked CSS surface": ["name", "shell", "run"],
            "Verify worktree remains clean": ["name", "shell", "run"],
        }
        for position, start in enumerate(step_starts):
            end = step_starts[position + 1] if position + 1 < len(step_starts) else len(lines)
            step = lines[start:end]
            name = lines[start].removeprefix("      - name: ")
            keys = ["name"]
            for line in step[1:]:
                match = re.fullmatch(r"        ([A-Za-z0-9_-]+):.*", line)
                if match:
                    keys.append(match.group(1))
            self.assertEqual(keys, expected_keys[name])

        def step_named(name):
            start = lines.index(f"      - name: {name}")
            following = [
                index
                for index, line in enumerate(lines)
                if index > start and line.startswith("      - name:")
            ]
            end = min(following) if following else len(lines)
            return lines[start:end]

        checkout = step_named("Checkout exact tested revision")
        with_start = checkout.index("        with:") + 1
        checkout_keys = []
        for line in checkout[with_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                checkout_keys.append(match.group(1))
                continue
            break
        self.assertEqual(checkout_keys, ["ref", "persist-credentials"])

        verifier = step_named("Verify exact tested revision")
        env_start = verifier.index("        env:") + 1
        verifier_keys = []
        for line in verifier[env_start:]:
            match = re.fullmatch(r"          ([A-Za-z0-9_-]+):.*", line)
            if match:
                verifier_keys.append(match.group(1))
                continue
            break
        self.assertEqual(verifier_keys, ["EXPECTED_SHA"])



if __name__ == "__main__":
    unittest.main()
