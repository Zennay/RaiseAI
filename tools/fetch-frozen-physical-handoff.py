#!/usr/bin/env python3
"""Fetch and safely unpack the exact frozen Raise AI physical handoff.

This tool deliberately accepts only the preserved GitHub Release asset that
backs the current physical V1 gate. It never rebuilds or substitutes the APK.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import tempfile
import unicodedata
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

REPOSITORY = "Zennay/RaiseAI"
RELEASE_TAG = "physical-handoff-v1.5.2-8f719bb"
RELEASE_ASSET_ID = 611084738
EXPECTED_ARCHIVE_SHA256 = (
    "867f2a75260c89d9d92416d407df5dc559a05d99d6f506006003b163ad3e51ce"
)
EXPECTED_SOURCE_REVISION = "8f719bb273f9b997848864f342598e7df5f090e5"
ASSET_API_URL = (
    f"https://api.github.com/repos/{REPOSITORY}/releases/assets/{RELEASE_ASSET_ID}"
)
REQUIRED_MEMBERS = {
    "BUILD-IDENTITY.txt",
    "RaiseAI-v1.5.2-debug.apk",
    "RaiseAI-v1.5.2-source.bundle",
    "start-physical-handoff.command",
}


class HandoffError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _validate_member_path(name: str) -> str:
    if "\\" in name:
        raise HandoffError(f"Unsafe archive member path: {name}")

    candidate = PurePosixPath(name)
    rendered = name[:-1] if name.endswith("/") else name
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
        or rendered != candidate.as_posix()
    ):
        raise HandoffError(f"Unsafe archive member path: {name}")
    return candidate.as_posix()


def extract_verified_archive(
    archive: Path,
    output_dir: Path,
    *,
    expected_sha256: str = EXPECTED_ARCHIVE_SHA256,
) -> None:
    actual = sha256_file(archive)
    if actual.lower() != expected_sha256.lower():
        raise HandoffError(
            "Frozen handoff archive SHA-256 mismatch: "
            f"expected {expected_sha256}, got {actual}"
        )

    if os.path.lexists(output_dir):
        raise HandoffError(f"Output already exists; refusing to overwrite: {output_dir}")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.",
            dir=str(output_dir.parent),
        )
    )

    try:
        with zipfile.ZipFile(archive) as package:
            infos = package.infolist()
            duplicate_names = sorted(
                name
                for name, count in Counter(info.filename for info in infos).items()
                if count > 1
            )
            if duplicate_names:
                raise HandoffError(
                    "Frozen handoff contains duplicate archive members: "
                    + ", ".join(duplicate_names)
                )

            names = set()
            portable_paths: dict[str, str] = {}
            for info in infos:
                canonical_path = _validate_member_path(info.filename)
                portable_key = unicodedata.normalize("NFC", canonical_path).casefold()
                previous = portable_paths.get(portable_key)
                if previous is not None:
                    raise HandoffError(
                        "Frozen handoff contains portable path collision: "
                        f"{previous} <> {info.filename}"
                    )
                portable_paths[portable_key] = info.filename

                if _member_is_symlink(info):
                    raise HandoffError(
                        f"Symlink entries are not allowed in frozen handoff: {info.filename}"
                    )
                if not info.is_dir():
                    names.add(info.filename.rstrip("/"))

            missing = sorted(REQUIRED_MEMBERS - names)
            if missing:
                raise HandoffError(
                    "Frozen handoff is missing required members: " + ", ".join(missing)
                )

            for info in infos:
                if info.is_dir():
                    continue
                target = stage / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

        launcher = stage / "start-physical-handoff.command"
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

        try:
            stage.rename(output_dir)
        except OSError as exc:
            if os.path.lexists(output_dir):
                raise HandoffError(
                    f"Output already exists; refusing to overwrite: {output_dir}"
                ) from exc
            raise HandoffError(
                f"Could not publish verified handoff atomically: {exc}"
            ) from exc
        stage = None
    except Exception:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        raise


def download_release_asset(destination: Path) -> None:
    headers = {
        "Accept": "application/octet-stream",
        "User-Agent": "RaiseAI-frozen-handoff-fetcher",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(ASSET_API_URL, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle)
    except Exception as exc:
        raise HandoffError(
            "Could not download the preserved GitHub Release asset "
            f"{RELEASE_ASSET_ID} from tag {RELEASE_TAG}: {exc}"
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download and verify the exact frozen Raise AI v1.5.2 physical handoff."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / "Downloads" / "raiseai-v1.5.2-frozen",
        help="Fresh directory to create for the verified extracted handoff.",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        help=(
            "Use an already-downloaded archive instead of GitHub. "
            "The canonical SHA-256 is still mandatory."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output.expanduser().absolute()

    if args.archive:
        archive = args.archive.expanduser().resolve()
        if not archive.is_file():
            raise HandoffError(f"Archive not found: {archive}")
        extract_verified_archive(archive, output_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="raiseai-frozen-handoff-") as tmp:
            archive = Path(tmp) / "frozen-physical-handoff.zip"
            download_release_asset(archive)
            extract_verified_archive(archive, output_dir)

    print("FROZEN HANDOFF FETCH PASS")
    print(f"  release tag:     {RELEASE_TAG}")
    print(f"  release asset:   {RELEASE_ASSET_ID}")
    print(f"  archive SHA-256: {EXPECTED_ARCHIVE_SHA256}")
    print(f"  source revision: {EXPECTED_SOURCE_REVISION}")
    print(f"  extracted to:    {output_dir}")
    print()
    print("Next:")
    print(f"  cd {output_dir}")
    print('  verify_root="$(mktemp -d)"')
    print('  RAISE_RESTORE_DIR="$verify_root/source" \\')
    print("    bash ./start-physical-handoff.command --verify-only")
    print("  verify_status=$?")
    print('  rm -rf "$verify_root"')
    print('  test "$verify_status" -eq 0')
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HandoffError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
