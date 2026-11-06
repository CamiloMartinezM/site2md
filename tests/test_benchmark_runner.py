"""Tests for how the runner turns a solution into one command line for hyperfine."""

from __future__ import annotations

import unittest

from benchmarks.catalog import Solution, Step
from benchmarks.errors import HarnessError
from benchmarks.runner import build_command


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


if __name__ == "__main__":
    unittest.main()
