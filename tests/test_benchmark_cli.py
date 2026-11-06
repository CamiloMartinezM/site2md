"""Tests for the benchmark harness command, run the way a user runs it."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


class BenchmarkCliTests(unittest.TestCase):
    """Check what the command does before it needs the network or any tool."""

    def run_harness(self, *arguments: str, path: str) -> subprocess.CompletedProcess[str]:
        """Run `python -m benchmarks` from the repository root with the given PATH."""
        environment = os.environ.copy()
        environment["PATH"] = path
        return subprocess.run(
            [sys.executable, "-m", "benchmarks", *arguments],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_run_stops_and_says_how_to_install_hyperfine_when_it_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as empty_path:
            completed = self.run_harness("run", "site2md", path=empty_path)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertIn("winget install sharkdp.hyperfine", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_run_names_the_tools_when_the_tool_is_unknown(self) -> None:
        completed = self.run_harness("run", "nonesuch", path=os.environ["PATH"])
        self.assertEqual(completed.returncode, 1)
        self.assertIn("unknown tool 'nonesuch'", completed.stderr)
        self.assertIn("site2md", completed.stderr)


if __name__ == "__main__":
    unittest.main()
