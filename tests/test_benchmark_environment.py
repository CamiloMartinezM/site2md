"""Tests for the variables that every benchmarked child process runs with."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from benchmarks.environment import check_programs, child_variables, path_programs
from benchmarks.errors import HarnessError
from benchmarks.paths import CACHE_DIRECTORY


class ChildVariablesTests(unittest.TestCase):
    """Check that a run writes only inside the cache."""

    def test_every_folder_that_a_child_may_write_to_is_inside_the_cache(self) -> None:
        variables = child_variables()
        # `uv tool run`, which formats the solutions, keeps its lock file in UV_TOOL_DIR.
        for name in ("UV_CACHE_DIR", "UV_TOOL_DIR", "TMP", "TEMP", "TMPDIR"):
            with self.subTest(name=name):
                self.assertIn(CACHE_DIRECTORY, Path(variables[name]).parents)


class CheckProgramsTests(unittest.TestCase):
    """Check that a solution's programs come from the tool's own environment, never from the machine."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.own = Path(temporary.name) / "own"
        self.machine = Path(temporary.name) / "machine"
        self.own.mkdir()
        self.machine.mkdir()

    def install(self, folder: Path, name: str) -> None:
        """Put a program that the shell can find in a folder."""
        program = folder / (f"{name}.exe" if sys.platform == "win32" else name)
        program.write_bytes(b"")
        program.chmod(0o755)

    def path(self, *folders: Path) -> str:
        """Join folders into a PATH value."""
        return os.pathsep.join(str(folder) for folder in folders)

    def test_a_program_found_in_the_environment_passes(self) -> None:
        self.install(self.own, "tool")
        check_programs(["tool"], path=self.path(self.own, self.machine), inside=self.own)

    def test_a_program_that_resolves_to_the_machine_is_refused_and_named(self) -> None:
        # The machine's copy is first on PATH, as a misordered PATH would have it.
        self.install(self.own, "tool")
        self.install(self.machine, "tool")
        with self.assertRaisesRegex(HarnessError, "'tool'.*machine"):
            check_programs(["tool"], path=self.path(self.machine, self.own), inside=self.own)

    def test_a_program_that_the_environment_lacks_falls_back_to_the_machine_and_is_refused(self) -> None:
        self.install(self.machine, "tool")
        with self.assertRaisesRegex(HarnessError, "'tool'.*machine"):
            check_programs(["tool"], path=self.path(self.own, self.machine), inside=self.own)

    def test_a_program_that_is_nowhere_is_refused(self) -> None:
        with self.assertRaisesRegex(HarnessError, "'tool'.*not found"):
            check_programs(["tool"], path=self.path(self.own, self.machine), inside=self.own)

    def test_a_tool_folder_lists_its_programs_and_not_its_other_files(self) -> None:
        self.install(self.own, "tool")
        (self.own / "MANUAL.html").write_text("<p>manual</p>", encoding="utf-8")
        self.assertEqual(path_programs([self.own]), ["tool.exe" if sys.platform == "win32" else "tool"])

    def test_a_program_from_a_tool_folder_that_the_machine_shadows_is_refused(self) -> None:
        # pandoc's solution calls pandoc from inside a Python script, so no step names it.
        self.install(self.own, "tool")
        self.install(self.machine, "tool")
        with self.assertRaisesRegex(HarnessError, "'tool.*machine"):
            check_programs(path_programs([self.own]), path=self.path(self.machine, self.own), inside=self.own)


if __name__ == "__main__":
    unittest.main()
