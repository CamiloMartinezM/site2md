"""Tests for turning hyperfine's export into the numbers a results file records."""

from __future__ import annotations

import json
import unittest
from collections.abc import Sequence

from benchmarks._types import JsonValue
from benchmarks.timing import summarize_hyperfine

PRIVATE_COMMAND = r"C:\Users\someone\work\.cache\venv\Scripts\site2md.exe build http://127.0.0.1:51234/"


class SummarizeHyperfineTests(unittest.TestCase):
    """Check that only wall-clock timings survive, and nothing that identifies the machine."""

    def test_the_wall_clock_summary_and_each_run_are_kept(self) -> None:
        self.assertEqual(
            summarize_hyperfine(_export()),
            {
                "mean": 0.625,
                "stddev": 0.125,
                "median": 0.625,
                "min": 0.5,
                "max": 0.75,
                "times": [0.5, 0.75, 0.625],
            },
        )

    def test_timings_are_rounded_to_microseconds(self) -> None:
        summary = summarize_hyperfine(_export(seconds=(1.6933781399999999,)))
        self.assertEqual(summary["times"], [1.693378])

    def test_nothing_that_identifies_the_machine_is_kept(self) -> None:
        recorded = json.dumps(summarize_hyperfine(_export()))
        for private in ("someone", "C:", "127.0.0.1", "Windows_NT", "x86_64", "2026-11-06T15"):
            self.assertNotIn(private, recorded)

    def test_a_failed_run_is_rejected(self) -> None:
        results: list[JsonValue] = [{"measurements": [_measurement(0.5), _measurement(0.5, exit_code=1)], "summary": {}}]
        with self.assertRaisesRegex(ValueError, "exit"):
            summarize_hyperfine(_export(results=results))

    def test_an_export_from_hyperfine_one_is_rejected_with_its_version_requirement(self) -> None:
        with self.assertRaisesRegex(ValueError, "hyperfine 2"):
            summarize_hyperfine({"results": [{"command": "x", "mean": 1.0, "times": [1.0]}]})


def _measurement(seconds: float, exit_code: int = 0) -> dict[str, JsonValue]:
    """Return one run as hyperfine 2 exports it."""
    value: dict[str, JsonValue] = {"value": seconds, "unit": "second"}
    return {
        "time_wall_clock": value,
        "time_cpu": value,
        "time_user": value,
        "time_system": {"value": 0.0, "unit": "second"},
        "exit_code": exit_code,
    }


def _export(
    seconds: Sequence[float] = (0.5, 0.75, 0.625), **overrides: JsonValue
) -> dict[str, JsonValue]:
    """Return a hand-written hyperfine 2 export of runs, with private details in it."""
    result: dict[str, JsonValue] = {
        "command": PRIVATE_COMMAND,
        "measurements": [_measurement(value) for value in seconds],
        "summary": {
            "time_wall_clock": {
                "unit": "second",
                "count": 3,
                "mean": 0.625,
                "stddev": 0.125,
                "median": 0.625,
                "min": 0.5,
                "max": 0.75,
            },
            "time_cpu": {"unit": "second", "count": 3, "mean": 9.0, "stddev": 9.0, "median": 9.0, "min": 9.0, "max": 9.0},
        },
    }
    export: dict[str, JsonValue] = {
        "schema_version": 2,
        "metadata": {
            "hyperfine_version": "2.0.0",
            "start_time": "2026-11-06T15:57:44Z",
            "platform": {"os": "Windows_NT", "architecture": "x86_64"},
        },
        "primary_metric": "time_wall_clock",
        "results": [result],
    }
    export.update(overrides)
    return export


if __name__ == "__main__":
    unittest.main()
