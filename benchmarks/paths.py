"""Locations of the benchmark's committed files and its git-ignored cache."""

from __future__ import annotations

from pathlib import Path

BENCHMARKS_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = BENCHMARKS_DIRECTORY.parent
BENCHMARKS_DOCUMENT = REPOSITORY_ROOT / "BENCHMARKS.md"
TOOLS_DIRECTORY = BENCHMARKS_DIRECTORY / "tools"
EXPECTED_DIRECTORY = BENCHMARKS_DIRECTORY / "expected"
REFERENCE = EXPECTED_DIRECTORY / "countries.json"
PAGE_PIN = EXPECTED_DIRECTORY / "page.json"
RESULTS_DIRECTORY = BENCHMARKS_DIRECTORY / "results"
# Every file that a run writes goes below here, so a checkout never touches another one's files.
CACHE_DIRECTORY = BENCHMARKS_DIRECTORY / ".cache"
