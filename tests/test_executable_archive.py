"""Tests for the release archives of the standalone executable."""

from __future__ import annotations

import contextlib
import io
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile
from importlib import metadata
from pathlib import Path

from executable.archive import archive_executable, main


def _write_onedir_folder(folder: Path, executable_name: str) -> None:
    """Lay out a stand-in for PyInstaller's onedir folder: an executable beside an _internal folder."""
    (folder / "_internal" / "site2md").mkdir(parents=True)
    (folder / executable_name).write_bytes(b"#!/bin/sh\nexit 0\n")
    (folder / executable_name).chmod(0o755)
    (folder / "_internal" / "base_library.zip").write_bytes(b"library")
    (folder / "_internal" / "site2md" / "extraction.json").write_text('{"schema": true}\n', encoding="utf-8")


class ArchiveExecutableTests(unittest.TestCase):
    """Archive a stand-in onedir folder and unpack the archive the way a user would."""

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.destination = self.root / "archives"
        self.unpacked = self.root / "unpacked"

    def archive(self, platform: str, executable_name: str) -> Path:
        """Archive a stand-in onedir folder for a platform and return the archive."""
        folder = self.root / "dist" / "site2md"
        _write_onedir_folder(folder, executable_name)
        return archive_executable(folder, self.destination, version="0.5.0", platform=platform)

    def test_the_windows_archive_is_a_zip_that_unpacks_to_one_folder_of_the_same_name(self) -> None:
        archive = self.archive("windows", "site2md.exe")

        with zipfile.ZipFile(archive) as zip_file:
            zip_file.extractall(self.unpacked)

        self.assertEqual(archive.name, "site2md-0.5.0-windows-x86_64.zip")
        self.assertEqual([path.name for path in self.unpacked.iterdir()], ["site2md-0.5.0-windows-x86_64"])
        folder = self.unpacked / "site2md-0.5.0-windows-x86_64"
        self.assertEqual(
            sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()),
            ["_internal/base_library.zip", "_internal/site2md/extraction.json", "site2md.exe"],
        )

    def test_the_linux_archive_is_a_tar_gz_that_unpacks_to_one_folder_of_the_same_name(self) -> None:
        archive = self.archive("linux", "site2md")

        with tarfile.open(archive) as tar_file:
            tar_file.extractall(self.unpacked, filter="data")

        self.assertEqual(archive.name, "site2md-0.5.0-linux-x86_64.tar.gz")
        self.assertEqual([path.name for path in self.unpacked.iterdir()], ["site2md-0.5.0-linux-x86_64"])
        folder = self.unpacked / "site2md-0.5.0-linux-x86_64"
        self.assertEqual(
            sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()),
            ["_internal/base_library.zip", "_internal/site2md/extraction.json", "site2md"],
        )

    @unittest.skipIf(sys.platform == "win32", "Windows file systems have no executable bit")
    def test_the_linux_archive_keeps_the_executable_bit(self) -> None:
        archive = self.archive("linux", "site2md")

        with tarfile.open(archive) as tar_file:
            tar_file.extractall(self.unpacked, filter="data")

        mode = (self.unpacked / "site2md-0.5.0-linux-x86_64" / "site2md").stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)

    def test_the_linux_archive_does_not_carry_the_builders_owner(self) -> None:
        archive = self.archive("linux", "site2md")

        with tarfile.open(archive) as tar_file:
            owners = {(member.uid, member.gid, member.uname, member.gname) for member in tar_file}

        self.assertEqual(owners, {(0, 0, "root", "root")})

    def test_a_platform_without_an_executable_is_rejected(self) -> None:
        folder = self.root / "dist" / "site2md"
        _write_onedir_folder(folder, "site2md")

        with self.assertRaisesRegex(ValueError, "macos"):
            archive_executable(folder, self.destination, version="0.5.0", platform="macos")

        self.assertFalse(self.destination.exists())


class ArchiveCommandTests(unittest.TestCase):
    """Run the script's command line on a stand-in onedir folder."""

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.folder = self.root / "dist" / "site2md"
        _write_onedir_folder(self.folder, "site2md")
        self.destination = self.root / "archives"

    def run_main(self, *arguments: str) -> tuple[int, str]:
        """Return the exit status and the standard error of one run."""
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            status = main([str(self.folder), str(self.destination), *arguments])
        return status, stderr.getvalue()

    def test_a_tag_that_names_the_installed_version_is_archived(self) -> None:
        status, _ = self.run_main("--tag", f"v{metadata.version('site2md')}")

        self.assertEqual(status, 0)
        self.assertEqual(len(list(self.destination.iterdir())), 1)

    def test_an_empty_tag_is_no_tag(self) -> None:
        # A manual run has no release, and the workflow passes the empty tag along.
        status, _ = self.run_main("--tag", "")

        self.assertEqual(status, 0)
        self.assertEqual(len(list(self.destination.iterdir())), 1)

    def test_a_tag_that_names_another_version_is_refused_before_anything_is_written(self) -> None:
        status, stderr = self.run_main("--tag", "v9.9.9")

        self.assertEqual(status, 1)
        self.assertIn("v9.9.9", stderr)
        self.assertFalse(self.destination.exists())

    def test_a_missing_folder_is_refused(self) -> None:
        self.folder = self.root / "dist" / "missing"

        status, stderr = self.run_main()

        self.assertEqual(status, 1)
        self.assertIn("missing", stderr)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
