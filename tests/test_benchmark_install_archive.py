"""Tests for the script that installs a tool from a release archive, such as pandoc or site2md's executable."""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from benchmarks.paths import TOOLS_DIRECTORY
from benchmarks.server import FixtureServer

INSTALL_ARCHIVE = TOOLS_DIRECTORY / "install_archive.py"
ARCHIVE_PATH = "/releases/tool-1.0.zip"


class InstallArchiveTests(unittest.TestCase):
    """Check that an archive is unpacked only when its SHA-256 is the pinned one."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.destination = Path(temporary.name) / "environment"

    def run_script(self, url: str, sha256: str) -> subprocess.CompletedProcess[str]:
        """Run the script on a URL with a pinned checksum."""
        return subprocess.run(
            [sys.executable, str(INSTALL_ARCHIVE), url, sha256, str(self.destination)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def install(self, archive: bytes, sha256: str) -> subprocess.CompletedProcess[str]:
        """Serve an archive on 127.0.0.1 and run the script against it."""
        with FixtureServer({ARCHIVE_PATH: archive}) as server:
            return self.run_script(server.origin + ARCHIVE_PATH, sha256)

    def test_an_archive_with_the_pinned_checksum_is_unpacked(self) -> None:
        archive = _zip_of({"tool-1.0/tool.exe": b"binary", "tool-1.0/LICENSE": b"terms"})
        completed = self.install(archive, hashlib.sha256(archive).hexdigest())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual((self.destination / "tool-1.0" / "tool.exe").read_bytes(), b"binary")
        self.assertEqual((self.destination / "tool-1.0" / "LICENSE").read_bytes(), b"terms")

    def test_an_archive_with_another_checksum_is_refused_and_nothing_is_unpacked(self) -> None:
        archive = _zip_of({"tool-1.0/tool.exe": b"binary"})
        pinned = "0" * 64
        completed = self.install(archive, pinned)
        self.assertEqual(completed.returncode, 1)
        # The message names both hashes, so a changed release can be told from a corrupt download.
        self.assertIn(pinned, completed.stderr)
        self.assertIn(hashlib.sha256(archive).hexdigest(), completed.stderr)
        self.assertFalse(self.destination.exists())

    def test_a_download_that_fails_is_reported_in_one_line(self) -> None:
        with FixtureServer({}) as server:
            completed = self.run_script(server.origin + ARCHIVE_PATH, "0" * 64)
        self.assertEqual(completed.returncode, 1)
        self.assertIn(ARCHIVE_PATH, completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertFalse(self.destination.exists())


def _zip_of(files: dict[str, bytes]) -> bytes:
    """Return a zip archive that holds the given files."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
