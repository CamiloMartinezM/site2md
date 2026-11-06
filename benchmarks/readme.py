"""Render the parts of the README that come from the benchmark results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from benchmarks._types import ChartMeasure, ChartTheme, LinesResult, ToolResult
from benchmarks.catalog import Tool
from benchmarks.chart import choose_measure
from benchmarks.page import PAGE_URL
from benchmarks.paths import CHART_FILES, REPOSITORY_ROOT
from benchmarks.report import (
    local_only_note,
    ordered_tools,
    splice_generated,
    time_text,
)

_HEADERS = ("Tool", "Time", "Lines (page)", "Lines (crawl)", "Install size")
_PAGE_LINK = f"[Scrape This Site's countries page]({PAGE_URL})"
_CAPTIONS: Mapping[ChartMeasure, str] = {
    "time": f"Extracting the 250 countries from {_PAGE_LINK} as JSON, from a local copy.",
    "size": (
        "Disk space used by each tool's smallest install that can extract the countries from "
        f"{_PAGE_LINK} without a browser."
    ),
}
_ALTERNATIVE_TEXTS: Mapping[ChartMeasure, str] = {
    "time": "Bar chart of the time each tool takes to extract the countries.",
    "size": "Bar chart of the disk space each tool's smallest install uses.",
}
_MISMATCH_NOTE = "Its output doesn't match the reference, so the chart leaves it out."


def _chart_path(theme: ChartTheme) -> str:
    """Name a chart file as the README links to it."""
    return CHART_FILES[theme].relative_to(REPOSITORY_ROOT).as_posix()


def _notes(tool: Tool, column: str) -> list[str]:
    """List the notes that the tool's definition attaches to one column."""
    return [note.text for note in tool.footnotes if note.column == column]


def _local_only_notes(lines: LinesResult) -> list[str]:
    """Return the note that names the lines left out of a count, or nothing if none were left out."""
    return [local_only_note(lines["local_only"])] if lines["local_only"] else []


def _crawl_gap(tool: Tool) -> str:
    """Say why a tool has no crawl line count."""
    if "crawl" in tool.tasks:
        return f"{tool.name} has no crawl results yet."
    return f"{tool.name} has no crawler."


def render_chart_block(measure: ChartMeasure) -> str:
    """Render the picture that goes under the tagline, with the caption for the charted measure."""
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="{_chart_path("dark")}">\n'
        f'  <source media="(prefers-color-scheme: light)" srcset="{_chart_path("light")}">\n'
        f'  <img alt="{_ALTERNATIVE_TEXTS[measure]}" src="{_chart_path("light")}">\n'
        "</picture>\n\n"
        f"*{_CAPTIONS[measure]} [Details](BENCHMARKS.md).*\n"
    )


def render_table(tools: Sequence[Tool], results: Mapping[str, ToolResult]) -> str:
    """Render the README's table, one row per tool that has results, with a footnote for every gap."""
    notes: list[str] = []

    def mark(text: str, column_notes: Sequence[str]) -> str:
        """Append a footnote marker per note and remember the note."""
        for note in column_notes:
            notes.append(note)
            text += f" [^{len(notes)}]"
        return text

    lines = [f"| {' | '.join(_HEADERS)} |", f"|{'---|' * len(_HEADERS)}"]
    for tool in ordered_tools([tool for tool in tools if tool.id in results]):
        result = results[tool.id]
        page = result["page"]
        crawl = result.get("crawl")
        cells = (
            tool.name,
            mark(time_text(page["time"]), [*_notes(tool, "time"), *([] if page["matches"] else [_MISMATCH_NOTE])]),
            mark(str(page["lines"]["counted"]), [*_notes(tool, "lines"), *_local_only_notes(page["lines"])]),
            mark("–", [_crawl_gap(tool)])
            if crawl is None
            else mark(str(crawl["lines"]["counted"]), _local_only_notes(crawl["lines"])),
            mark(f"{result['install']['size_bytes'] / 1e6:.1f} MB", _notes(tool, "size")),
        )
        lines.append(f"| {' | '.join(cells)} |")
    table = "\n".join(lines) + "\n"
    if not notes:
        return table
    return table + "\n" + "".join(f"[^{number}]: {note}\n" for number, note in enumerate(notes, start=1))


def render_readme(document: str, tools: Sequence[Tool], results: Mapping[str, ToolResult]) -> str:
    """Return the README with its chart block and table rebuilt from the results."""
    chart = splice_generated(document, render_chart_block(choose_measure(results)), block="chart")
    return splice_generated(chart, render_table(tools, results), block="table")
