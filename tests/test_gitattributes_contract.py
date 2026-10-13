import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ATTRIBUTES = ROOT / ".gitattributes"


def attributes_for(relative: str) -> dict[str, str]:
    output = subprocess.check_output(
        ["git", "check-attr", "-z", "text", "eol", "--", relative],
        cwd=ROOT,
    )
    fields = output.decode("utf-8", errors="strict").split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) % 3 != 0:
        raise ValueError("git check-attr returned malformed triplets")

    result: dict[str, str] = {}
    for index in range(0, len(fields), 3):
        path, attribute, value = fields[index:index + 3]
        if path != relative:
            raise ValueError(f"unexpected attribute path {path!r} for {relative!r}")
        result[attribute] = value
    return result


class GitAttributesContractTests(unittest.TestCase):
    def test_policy_file_is_exact_and_minimal(self):
        self.assertEqual(
            ATTRIBUTES.read_bytes(),
            b"* text=auto eol=lf\n*.bat text eol=crlf\n",
        )

    def test_repository_text_defaults_to_lf(self):
        for relative in (
            ".gitattributes",
            ".gitignore",
            "README.md",
            "gradlew",
            "gateway/src/server.mjs",
            "physical-validation.command",
        ):
            with self.subTest(relative=relative):
                attrs = attributes_for(relative)
                self.assertEqual(attrs["text"], "auto")
                self.assertEqual(attrs["eol"], "lf")

    def test_windows_batch_wrapper_keeps_crlf_checkout_semantics(self):
        attrs = attributes_for("gradlew.bat")
        self.assertEqual(attrs["text"], "set")
        self.assertEqual(attrs["eol"], "crlf")


if __name__ == "__main__":
    unittest.main()
