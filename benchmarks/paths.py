"""Locations of the benchmark's committed files and its git-ignored cache."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from benchmarks._types import ChartTheme

BENCHMARKS_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = BENCHMARKS_DIRECTORY.parent
BENCHMARKS_DOCUMENT = REPOSITORY_ROOT / "BENCHMARKS.md"
README_DOCUMENT = REPOSITORY_ROOT / "README.md"
# The README shows the chart that matches the reader's theme.
CHART_FILES: Mapping[ChartTheme, Path] = {
    "light": REPOSITORY_ROOT / "docs" / "benchmark-light.svg",
    "dark": REPOSITORY_ROOT / "docs" / "benchmark-dark.svg",
}
TOOLS_DIRECTORY = BENCHMARKS_DIRECTORY / "tools"
EXPECTED_DIRECTORY = BENCHMARKS_DIRECTORY / "expected"
REFERENCE = EXPECTED_DIRECTORY / "countries.json"
PAGE_PIN = EXPECTED_DIRECTORY / "page.json"
RESULTS_DIRECTORY = BENCHMARKS_DIRECTORY / "results"
# Every file that a run writes goes below here, so a checkout never touches another one's files.
CACHE_DIRECTORY = BENCHMARKS_DIRECTORY / ".cache"
