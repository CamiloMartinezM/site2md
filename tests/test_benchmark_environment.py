"""Tests for the variables that every benchmarked child process runs with."""

from __future__ import annotations

import unittest
from pathlib import Path

from benchmarks.environment import child_variables
from benchmarks.paths import CACHE_DIRECTORY


class ChildVariablesTests(unittest.TestCase):
    """Check that a run writes only inside the cache."""

    def test_every_folder_that_a_child_may_write_to_is_inside_the_cache(self) -> None:
        variables = child_variables()
        # `uv tool run`, which formats the solutions, keeps its lock file in UV_TOOL_DIR.
        for name in ("UV_CACHE_DIR", "UV_TOOL_DIR", "TMP", "TEMP", "TMPDIR"):
            with self.subTest(name=name):
                self.assertIn(CACHE_DIRECTORY, Path(variables[name]).parents)


if __name__ == "__main__":
    unittest.main()
