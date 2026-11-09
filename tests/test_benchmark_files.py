"""Tests for the harness's atomic file writes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from benchmarks.files import write_atomically


class WriteAtomicallyTests(unittest.TestCase):
    """Check what a write leaves in the destination folder."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def test_the_folder_is_created_and_the_contents_are_written(self) -> None:
        destination = self.folder / "new" / "out.json"
        write_atomically(destination, b"[]\n")
        self.assertEqual(destination.read_bytes(), b"[]\n")

    def test_an_existing_file_is_replaced_and_no_temporary_file_stays(self) -> None:
        destination = self.folder / "out.json"
        destination.write_bytes(b"old")
        write_atomically(destination, b"new")
        self.assertEqual(destination.read_bytes(), b"new")
        self.assertEqual(list(self.folder.iterdir()), [destination])

    def test_a_failed_write_removes_its_temporary_file(self) -> None:
        # A folder in the destination's place makes the final replace fail on every platform.
        destination = self.folder / "out.json"
        destination.mkdir()
        with self.assertRaises(OSError):
            write_atomically(destination, b"new")
        self.assertEqual(list(self.folder.iterdir()), [destination])


if __name__ == "__main__":
    unittest.main()
