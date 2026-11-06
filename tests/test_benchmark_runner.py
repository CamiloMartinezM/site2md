"""Tests for how the runner turns a solution into one command line for hyperfine."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from benchmarks.catalog import Solution, Step, Tool
from benchmarks.environment import Environment
from benchmarks.errors import HarnessError
from benchmarks.paths import CACHE_DIRECTORY
from benchmarks.runner import build_command, run_crawl
from tests.benchmark_test_support import make_page


class BuildCommandTests(unittest.TestCase):
    """Check the command line that hyperfine times."""

    def test_steps_run_in_order_and_stop_at_the_first_failure(self) -> None:
        solution = Solution((Step("first {url}"), Step("second")))
        self.assertEqual(
            build_command(solution, "http://127.0.0.1:1/p/"),
            "first http://127.0.0.1:1/p/ && second > output.json",
        )

    def test_the_last_steps_standard_output_becomes_the_output_file(self) -> None:
        command = build_command(Solution((Step("only"),)), "http://127.0.0.1:1/")
        self.assertTrue(command.endswith(" > output.json"))

    def test_a_solution_that_names_its_output_file_is_left_alone(self) -> None:
        solution = Solution((Step("python solution.py {url}"),), output_file="records.json")
        self.assertEqual(
            build_command(solution, "http://127.0.0.1:1/"),
            "python solution.py http://127.0.0.1:1/",
        )

    def test_an_unknown_placeholder_is_named(self) -> None:
        with self.assertRaisesRegex(HarnessError, "port"):
            build_command(Solution((Step("serve {port}"),)), "http://127.0.0.1:1/")


class RunCrawlTests(unittest.TestCase):
    """Check what the crawl task records for solutions that work and for solutions that don't."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.page = self.folder / "simple.html"
        self.page.write_text(make_page(), encoding="utf-8")
        # run_crawl works in a folder named after the tool, inside the cache.
        self.addCleanup(shutil.rmtree, CACHE_DIRECTORY / "work" / "stub-crawl", ignore_errors=True)

    def crawl(self, code: str, *, output_file: str | None = None) -> tuple[bool, list[str], str | None]:
        """Run a one-step crawl solution that runs a Python program, and return what the task recorded."""
        script = self.folder / "solution.py"
        script.write_text(code, encoding="utf-8")
        step = Step(f'"{sys.executable}" "{script}" {{url}}')
        tool = Tool(
            id="stub",
            directory=Path(),
            name="Stub",
            version="1",
            solution="",
            requirements=(),
            tasks={"crawl": Solution((step,), output_file=output_file)},
        )
        python = Path(sys.executable)
        environment = Environment(Path(), python, python.parent, "", dict(os.environ))
        result, difference = run_crawl(tool, environment, self.page, [], lambda source: source)
        return result["matches"], result["extra_pages"], difference

    def test_a_crawl_that_writes_the_reference_records_matches(self) -> None:
        matches, extra, difference = self.crawl("print('[]')\n")
        self.assertEqual((matches, extra, difference), (True, [], None))

    def test_a_crawl_that_exits_with_an_error_is_recorded_as_not_working_with_what_it_fetched(self) -> None:
        # The program fetches a decoy page of the generated site, then exits with status 3.
        code = (
            "import sys, urllib.request\n"
            "urllib.request.urlopen(sys.argv[1] + 'level-3/page-1.html')\n"
            "sys.exit(3)\n"
        )
        matches, extra, difference = self.crawl(code)
        self.assertFalse(matches)
        self.assertEqual(extra, ["/level-3/page-1.html"])
        self.assertIn("exited with status 3", difference or "")

    def test_a_crawl_that_exits_cleanly_but_writes_no_output_file_is_recorded_as_not_working(self) -> None:
        matches, _, difference = self.crawl("pass\n", output_file="records.json")
        self.assertFalse(matches)
        self.assertIn("wrote no records.json", difference or "")


if __name__ == "__main__":
    unittest.main()
