"""Time a solution with hyperfine and keep only the numbers worth recording."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path

from benchmarks._json import expect_list, expect_number, expect_object
from benchmarks._types import JsonValue, TimeResult
from benchmarks.errors import HarnessError


def _microseconds(value: JsonValue, where: str) -> float:
    """Return a number of seconds rounded to microseconds, which is finer than hyperfine measures."""
    return round(expect_number(value, where), 6)


def summarize_hyperfine(export: JsonValue) -> TimeResult:
    """Return the wall-clock timings of hyperfine's export, without its command or platform."""
    data = expect_object(export, "hyperfine export")
    if data.get("schema_version") != 2:
        raise HarnessError("hyperfine 2 or later is required: this export has an older format")
    result = expect_object(expect_list(data["results"], "results")[0], "result")
    measurements = [
        expect_object(measurement, "measurement")
        for measurement in expect_list(result["measurements"], "measurements")
    ]
    if any(measurement.get("exit_code") != 0 for measurement in measurements):
        raise HarnessError("the solution exited with an error in at least one run")
    summary = expect_object(
        expect_object(result["summary"], "summary")["time_wall_clock"], "wall-clock summary"
    )
    return {
        "mean": _microseconds(summary["mean"], "mean"),
        "stddev": _microseconds(summary["stddev"], "stddev"),
        "median": _microseconds(summary["median"], "median"),
        "min": _microseconds(summary["min"], "min"),
        "max": _microseconds(summary["max"], "max"),
        "times": [
            _microseconds(
                expect_object(measurement["time_wall_clock"], "wall-clock time")["value"], "time"
            )
            for measurement in measurements
        ],
    }


def run_hyperfine(
    hyperfine: str, command: str, *, cwd: Path, variables: Mapping[str, str], export: Path
) -> TimeResult:
    """Time a command line with three warmup runs and hyperfine's default number of runs."""
    try:
        # hyperfine 2 runs commands without a shell unless asked, and the solution chains steps with &&.
        completed = subprocess.run(
            [hyperfine, "--shell=default", "--warmup", "3", "--export-json", str(export), command],
            cwd=cwd,
            env=dict(variables),
            check=False,
        )
    except OSError as error:
        raise HarnessError(f"cannot run hyperfine: {error}") from error
    if completed.returncode != 0:
        raise HarnessError(
            f"hyperfine failed with exit status {completed.returncode}: the solution probably exited "
            "with an error, so it does not count as working"
        )
    return summarize_hyperfine(json.loads(export.read_text(encoding="utf-8")))
