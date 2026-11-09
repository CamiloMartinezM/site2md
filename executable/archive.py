"""Archive the standalone executable's onedir folder as a release download."""

from __future__ import annotations

import argparse
import sys
import tarfile
import zipfile
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path

# Only x86_64 runners build the executable, and macOS has no build (ADR 0004).
ARCHITECTURE = "x86_64"
# Linux gets a tar.gz because a zip loses the executable bit.
ARCHIVE_EXTENSIONS = {"windows": "zip", "linux": "tar.gz"}
PLATFORM_NAMES = {"win32": "windows", "linux": "linux"}


def _without_owner(member: tarfile.TarInfo) -> tarfile.TarInfo:
    """Replace the builder's user and group, which extracting as root would otherwise recreate."""
    member.uid = member.gid = 0
    member.uname = member.gname = "root"
    return member


def archive_executable(folder: Path, destination: Path, *, version: str, platform: str) -> Path:
    """Write the folder as `site2md-<version>-<platform>-x86_64` in an archive that unpacks to one folder of that name."""
    extension = ARCHIVE_EXTENSIONS.get(platform)
    if extension is None:
        raise ValueError(f"The executable has no build for '{platform}'.")

    name = f"site2md-{version}-{platform}-{ARCHITECTURE}"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"{name}.{extension}"
    if extension == "zip":
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.write(folder, name)
            for path in sorted(folder.rglob("*")):
                zip_file.write(path, f"{name}/{path.relative_to(folder).as_posix()}")
    else:
        with tarfile.open(archive, "w:gz") as tar_file:
            tar_file.add(folder, arcname=name, filter=_without_owner)
    return archive


def main(argv: Sequence[str] | None = None) -> int:
    """Archive the built folder for this platform and the installed site2md version, then return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="the folder that executable/build.py wrote, dist/site2md")
    parser.add_argument("destination", type=Path, help="the folder that receives the archive")
    parser.add_argument("--tag", help="the release tag, which must name the version that was built; empty for none")
    arguments = parser.parse_args(argv)
    if not arguments.folder.is_dir():
        print(f"Error: Folder '{arguments.folder}' does not exist. Build it first.", file=sys.stderr)
        return 1
    built_version = metadata.version("site2md")
    if arguments.tag and arguments.tag != f"v{built_version}":
        print(f"Error: Tag '{arguments.tag}' does not name the built version {built_version}.", file=sys.stderr)
        return 1

    archive = archive_executable(
        arguments.folder,
        arguments.destination,
        version=built_version,
        platform=PLATFORM_NAMES.get(sys.platform, sys.platform),
    )
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
