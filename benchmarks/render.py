"""Render every committed file that comes from the benchmark results."""

from __future__ import annotations

from pathlib import Path

from benchmarks.catalog import load_tool, tool_ids
from benchmarks.chart import choose_measure, render_chart
from benchmarks.errors import HarnessError
from benchmarks.paths import (
    BENCHMARKS_DOCUMENT,
    CHART_FILES,
    README_DOCUMENT,
    TOOLS_DIRECTORY,
)
from benchmarks.readme import render_readme
from benchmarks.report import render_document
from benchmarks.results import load_results


def render_files() -> dict[Path, str]:
    """Return the new text of BENCHMARKS.md, the README and both charts, built from the committed files."""
    tools = [load_tool(TOOLS_DIRECTORY / tool_id) for tool_id in tool_ids()]
    results = load_results()
    measure = choose_measure(results)
    documents = {
        BENCHMARKS_DOCUMENT: render_document,
        README_DOCUMENT: lambda document: render_readme(document, tools, results),
    }
    files: dict[Path, str] = {}
    for path, render in documents.items():
        try:
            files[path] = render(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise HarnessError(f"{path.name}: {error}") from error
    files.update({path: render_chart(tools, results, measure, theme) for theme, path in CHART_FILES.items()})
    return files
