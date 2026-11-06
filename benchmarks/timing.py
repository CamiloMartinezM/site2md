"""Time a solution with hyperfine and keep only the numbers worth recording."""

from __future__ import annotations

from benchmarks._json import expect_list, expect_number, expect_object
from benchmarks._types import JsonValue, TimeResult


def summarize_hyperfine(export: JsonValue) -> TimeResult:
    """Return the wall-clock timings of hyperfine's export, without its command or platform."""
    data = expect_object(export, "hyperfine export")
    if data.get("schema_version") != 2:
        raise ValueError("hyperfine 2 or later is required: this export has an older format")
    result = expect_object(expect_list(data["results"], "results")[0], "result")
    measurements = [
        expect_object(measurement, "measurement")
        for measurement in expect_list(result["measurements"], "measurements")
    ]
    if any(measurement.get("exit_code") != 0 for measurement in measurements):
        raise ValueError("the solution exited with an error in at least one run")
    summary = expect_object(
        expect_object(result["summary"], "summary")["time_wall_clock"], "wall-clock summary"
    )
    return {
        "mean": expect_number(summary["mean"], "mean"),
        "stddev": expect_number(summary["stddev"], "stddev"),
        "median": expect_number(summary["median"], "median"),
        "min": expect_number(summary["min"], "min"),
        "max": expect_number(summary["max"], "max"),
        "times": [
            expect_number(
                expect_object(measurement["time_wall_clock"], "wall-clock time")["value"], "time"
            )
            for measurement in measurements
        ],
    }
