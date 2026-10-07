import json
import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXTENSION_ROOT = ROOT / "app" / "src" / "main" / "assets" / "raiseai_wear"
MANIFEST_PATH = EXTENSION_ROOT / "manifest.json"
CHATGPT_ACTIVITY = (
    ROOT
    / "app"
    / "src"
    / "main"
    / "java"
    / "nl"
    / "zennay"
    / "raiseai"
    / "ChatGptActivity.kt"
)
EXPECTED_ASSETS = {
    "css": {"wear.css"},
    "js": {"wear.js"},
}
EXPECTED_MATCHES = {
    "https://chatgpt.com/*",
    "https://*.chatgpt.com/*",
    "https://chat.openai.com/*",
    "https://*.chat.openai.com/*",
}
EXPECTED_PERMISSIONS = {
    "nativeMessaging",
    "nativeMessagingFromContent",
    "geckoViewAddons",
}
EXPECTED_CONTENT_SCRIPT_KEYS = {"matches", "css", "js", "run_at"}
ABSOLUTE_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", flags=re.IGNORECASE)


def extract_private_kotlin_string_constant(source, name):
    pattern = re.compile(
        rf'(?m)^\s*private const val {re.escape(name)} = "([^"\n]+)"\s*
    if not isinstance(value, str) or not value:
        raise ValueError(f"{kind} asset reference must be a non-empty string")
    if "\\" in value:
        raise ValueError(f"{kind} asset reference must use POSIX separators")
    if value.startswith("/") or value.startswith("//") or ABSOLUTE_SCHEME.match(value):
        raise ValueError(f"{kind} asset reference must be extension-relative")

    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError(f"{kind} asset reference must be canonical and traversal-free")

    path = pathlib.PurePosixPath(value)
    expected_suffix = f".{kind}"
    if path.suffix.lower() != expected_suffix:
        raise ValueError(f"{kind} asset reference must end in {expected_suffix}")
    return path


class WearExtensionAssetContractTests(unittest.TestCase):
    def test_content_script_assets_are_local_regular_tracked_files(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        scripts = manifest.get("content_scripts")
        self.assertIsInstance(scripts, list)
        self.assertTrue(scripts, "Wear extension must declare at least one content script")

        discovered = {"css": set(), "js": set()}
        for index, script in enumerate(scripts):
            with self.subTest(content_script=index):
                self.assertIsInstance(script, dict)
                for kind in ("css", "js"):
                    values = script.get(kind, [])
                    self.assertIsInstance(values, list)
                    self.assertTrue(
                        all(isinstance(value, str) for value in values),
                        f"content_scripts[{index}].{kind} must contain only strings",
                    )
                    self.assertEqual(
                        len(values),
                        len(set(values)),
                        f"content_scripts[{index}].{kind} must not contain duplicates",
                    )
                    for value in values:
                        relative = validate_asset_reference(value, kind=kind)
                        discovered[kind].add(relative.as_posix())

                        asset = EXTENSION_ROOT
                        for part in relative.parts:
                            asset = asset / part
                            self.assertFalse(
                                asset.is_symlink(),
                                f"{value} must not traverse symlink indirection",
                            )

                        self.assertTrue(asset.is_file(), f"{value} must exist as a regular file")
                        repo_relative = asset.relative_to(ROOT).as_posix()
                        tracked = subprocess.run(
                            ["git", "ls-files", "--error-unmatch", "--", repo_relative],
                            cwd=ROOT,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            check=False,
                        )
                        self.assertEqual(
                            tracked.returncode,
                            0,
                            f"{value} must be tracked by git",
                        )

        for kind, expected in EXPECTED_ASSETS.items():
            self.assertTrue(
                expected.issubset(discovered[kind]),
                f"critical {kind} assets missing from manifest: "
                f"{sorted(expected - discovered[kind])}",
            )

    def test_manifest_keeps_exact_injection_and_native_permission_scope(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        permissions = manifest.get("permissions")
        self.assertIsInstance(permissions, list)
        self.assertTrue(all(isinstance(value, str) for value in permissions))
        self.assertEqual(len(permissions), len(set(permissions)))
        self.assertEqual(set(permissions), EXPECTED_PERMISSIONS)

        scripts = manifest.get("content_scripts")
        self.assertIsInstance(scripts, list)
        self.assertEqual(
            len(scripts),
            1,
            "content-script count changes require explicit scope review",
        )
        script = scripts[0]
        self.assertIsInstance(script, dict)
        self.assertEqual(
            set(script),
            EXPECTED_CONTENT_SCRIPT_KEYS,
            "content-script execution controls must stay explicit and reviewable",
        )

        matches = script.get("matches")
        self.assertIsInstance(matches, list)
        self.assertTrue(all(isinstance(value, str) for value in matches))
        self.assertEqual(len(matches), len(set(matches)))
        self.assertEqual(set(matches), EXPECTED_MATCHES)
        self.assertEqual(script.get("run_at"), "document_idle")

    def test_android_extension_identity_and_asset_uri_match_packaged_manifest(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        activity = CHATGPT_ACTIVITY.read_text(encoding="utf-8")

        gecko = manifest.get("browser_specific_settings", {}).get("gecko", {})
        manifest_id = gecko.get("id")
        self.assertIsInstance(manifest_id, str)
        self.assertTrue(manifest_id)
        self.assertFalse(any(char.isspace() for char in manifest_id))

        android_id = extract_private_kotlin_string_constant(activity, "EXTENSION_ID")
        self.assertEqual(
            android_id,
            manifest_id,
            "Android ensureBuiltIn() identity must match the bundled Gecko manifest id",
        )

        android_uri = extract_private_kotlin_string_constant(activity, "EXTENSION_URI")
        asset_root = EXTENSION_ROOT.relative_to(
            ROOT / "app" / "src" / "main" / "assets"
        ).as_posix()
        self.assertEqual(
            android_uri,
            f"resource://android/assets/{asset_root}/",
            "Android extension URI must resolve to the actual packaged asset directory",
        )

    def test_kotlin_constant_extractor_rejects_missing_or_duplicate_identity(self):
        with self.assertRaisesRegex(ValueError, "exactly once"):
            extract_private_kotlin_string_constant("", "EXTENSION_ID")
        with self.assertRaisesRegex(ValueError, "exactly once"):
            extract_private_kotlin_string_constant(
                'private const val EXTENSION_ID = "one"\n'
                'private const val EXTENSION_ID = "two"\n',
                "EXTENSION_ID",
            )

    def test_asset_reference_validator_rejects_ambiguous_or_external_paths(self):
        cases = (
            ("", "js"),
            ("../wear.js", "js"),
            ("./wear.js", "js"),
            ("/wear.js", "js"),
            ("nested//wear.js", "js"),
            ("nested\\wear.js", "js"),
            ("https://example.invalid/wear.js", "js"),
            ("moz-extension:wear.js", "js"),
            ("wear.css", "js"),
            ("wear.js", "css"),
        )
        for value, kind in cases:
            with self.subTest(value=value, kind=kind):
                with self.assertRaises(ValueError):
                    validate_asset_reference(value, kind=kind)

    def test_asset_reference_validator_accepts_canonical_relative_assets(self):
        self.assertEqual(
            validate_asset_reference("wear.js", kind="js"),
            pathlib.PurePosixPath("wear.js"),
        )
        self.assertEqual(
            validate_asset_reference("nested/wear.css", kind="css"),
            pathlib.PurePosixPath("nested/wear.css"),
        )


if __name__ == "__main__":
    unittest.main()

    )
    matches = pattern.findall(source)
    if len(matches) != 1:
        raise ValueError(
            f"{name} must be declared exactly once as a private const string"
        )
    return matches[0]


def validate_asset_reference(value, *, kind):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{kind} asset reference must be a non-empty string")
    if "\\" in value:
        raise ValueError(f"{kind} asset reference must use POSIX separators")
    if value.startswith("/") or value.startswith("//") or ABSOLUTE_SCHEME.match(value):
        raise ValueError(f"{kind} asset reference must be extension-relative")

    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError(f"{kind} asset reference must be canonical and traversal-free")

    path = pathlib.PurePosixPath(value)
    expected_suffix = f".{kind}"
    if path.suffix.lower() != expected_suffix:
        raise ValueError(f"{kind} asset reference must end in {expected_suffix}")
    return path


class WearExtensionAssetContractTests(unittest.TestCase):
    def test_content_script_assets_are_local_regular_tracked_files(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        scripts = manifest.get("content_scripts")
        self.assertIsInstance(scripts, list)
        self.assertTrue(scripts, "Wear extension must declare at least one content script")

        discovered = {"css": set(), "js": set()}
        for index, script in enumerate(scripts):
            with self.subTest(content_script=index):
                self.assertIsInstance(script, dict)
                for kind in ("css", "js"):
                    values = script.get(kind, [])
                    self.assertIsInstance(values, list)
                    self.assertTrue(
                        all(isinstance(value, str) for value in values),
                        f"content_scripts[{index}].{kind} must contain only strings",
                    )
                    self.assertEqual(
                        len(values),
                        len(set(values)),
                        f"content_scripts[{index}].{kind} must not contain duplicates",
                    )
                    for value in values:
                        relative = validate_asset_reference(value, kind=kind)
                        discovered[kind].add(relative.as_posix())

                        asset = EXTENSION_ROOT
                        for part in relative.parts:
                            asset = asset / part
                            self.assertFalse(
                                asset.is_symlink(),
                                f"{value} must not traverse symlink indirection",
                            )

                        self.assertTrue(asset.is_file(), f"{value} must exist as a regular file")
                        repo_relative = asset.relative_to(ROOT).as_posix()
                        tracked = subprocess.run(
                            ["git", "ls-files", "--error-unmatch", "--", repo_relative],
                            cwd=ROOT,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            check=False,
                        )
                        self.assertEqual(
                            tracked.returncode,
                            0,
                            f"{value} must be tracked by git",
                        )

        for kind, expected in EXPECTED_ASSETS.items():
            self.assertTrue(
                expected.issubset(discovered[kind]),
                f"critical {kind} assets missing from manifest: "
                f"{sorted(expected - discovered[kind])}",
            )

    def test_manifest_keeps_exact_injection_and_native_permission_scope(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        permissions = manifest.get("permissions")
        self.assertIsInstance(permissions, list)
        self.assertTrue(all(isinstance(value, str) for value in permissions))
        self.assertEqual(len(permissions), len(set(permissions)))
        self.assertEqual(set(permissions), EXPECTED_PERMISSIONS)

        scripts = manifest.get("content_scripts")
        self.assertIsInstance(scripts, list)
        self.assertEqual(
            len(scripts),
            1,
            "content-script count changes require explicit scope review",
        )
        script = scripts[0]
        self.assertIsInstance(script, dict)
        self.assertEqual(
            set(script),
            EXPECTED_CONTENT_SCRIPT_KEYS,
            "content-script execution controls must stay explicit and reviewable",
        )

        matches = script.get("matches")
        self.assertIsInstance(matches, list)
        self.assertTrue(all(isinstance(value, str) for value in matches))
        self.assertEqual(len(matches), len(set(matches)))
        self.assertEqual(set(matches), EXPECTED_MATCHES)
        self.assertEqual(script.get("run_at"), "document_idle")

    def test_asset_reference_validator_rejects_ambiguous_or_external_paths(self):
        cases = (
            ("", "js"),
            ("../wear.js", "js"),
            ("./wear.js", "js"),
            ("/wear.js", "js"),
            ("nested//wear.js", "js"),
            ("nested\\wear.js", "js"),
            ("https://example.invalid/wear.js", "js"),
            ("moz-extension:wear.js", "js"),
            ("wear.css", "js"),
            ("wear.js", "css"),
        )
        for value, kind in cases:
            with self.subTest(value=value, kind=kind):
                with self.assertRaises(ValueError):
                    validate_asset_reference(value, kind=kind)

    def test_asset_reference_validator_accepts_canonical_relative_assets(self):
        self.assertEqual(
            validate_asset_reference("wear.js", kind="js"),
            pathlib.PurePosixPath("wear.js"),
        )
        self.assertEqual(
            validate_asset_reference("nested/wear.css", kind="css"),
            pathlib.PurePosixPath("nested/wear.css"),
        )


if __name__ == "__main__":
    unittest.main()
