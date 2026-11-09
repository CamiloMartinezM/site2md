"""Render the parts of the README that come from the benchmark results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from benchmarks._types import ChartTheme, CrawlResult, ToolResult
from benchmarks.catalog import Tool
from benchmarks.page import PAGE_URL
from benchmarks.paths import CHART_FILES, REPOSITORY_ROOT
from benchmarks.report import (
    Footnotes,
    column_notes,
    local_only_notes,
    markdown_table,
    measured_tools,
    size_text,
    splice_generated,
    time_text,
)

_HEADERS = ("Tool", "Time", "Lines (page)", "Lines (crawl)", "Install size")
_PAGE_LINK = f"[Scrape This Site's countries page]({PAGE_URL})"
_CAPTION = (
    f"Install size and time to extract the 250 countries from a local copy of {_PAGE_LINK} as JSON, "
    "for each tool as its project ships it, without a browser."
)
_ALTERNATIVE_TEXT = "Bar chart of each tool's install size and the time it takes to extract the countries."
_MISMATCH_NOTE = "Its output doesn't match the reference, so the chart leaves it out."
_CRAWL_MISMATCH_NOTE = "Its crawl output doesn't match the reference, or the crawl exited with an error."


def _chart_path(theme: ChartTheme) -> str:
    """Name a chart file as the README links to it."""
    return CHART_FILES[theme].relative_to(REPOSITORY_ROOT).as_posix()


def _crawl_cell(tool: Tool, crawl: CrawlResult | None, footnotes: Footnotes) -> str:
    """Show the crawl's line count, or the reason there is none, with the notes that explain it."""
    if crawl is None:
        return footnotes.mark("–", ["No crawl results yet." if "crawl" in tool.tasks else "No crawler."])
    return footnotes.mark(
        str(crawl["lines"]["counted"]),
        [
            *column_notes(tool, "crawl"),
            *([] if crawl["matches"] else [_CRAWL_MISMATCH_NOTE]),
            *local_only_notes(crawl["lines"]),
        ],
    )


def _table_row(tool: Tool, result: ToolResult, footnotes: Footnotes) -> list[str]:
    """Build one row of the README's table, with the footnote markers of its cells."""
    page = result["page"]
    return [
        tool.name,
        footnotes.mark(
            time_text(page["time"]),
            [*column_notes(tool, "time"), *([] if page["matches"] else [_MISMATCH_NOTE])],
        ),
        footnotes.mark(
            str(page["lines"]["counted"]), [*column_notes(tool, "lines"), *local_only_notes(page["lines"])]
        ),
        _crawl_cell(tool, result.get("crawl"), footnotes),
        footnotes.mark(size_text(result["install"]["size_bytes"]), column_notes(tool, "size")),
    ]


def render_chart_block() -> str:
    """Render the picture that goes under the tagline, with its caption."""
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="{_chart_path("dark")}">\n'
        f'  <source media="(prefers-color-scheme: light)" srcset="{_chart_path("light")}">\n'
        f'  <img alt="{_ALTERNATIVE_TEXT}" src="{_chart_path("light")}">\n'
        "</picture>\n\n"
        f"*{_CAPTION} [Details](BENCHMARKS.md).*\n"
    )


def render_table(tools: Sequence[Tool], results: Mapping[str, ToolResult]) -> str:
    """Render the README's table, one row per tool that has results, with a footnote for every gap."""
    footnotes = Footnotes()
    rows = [_table_row(tool, results[tool.id], footnotes) for tool in measured_tools(tools, results)]
    return markdown_table(_HEADERS, rows, footnotes)


def render_readme(document: str, tools: Sequence[Tool], results: Mapping[str, ToolResult]) -> str:
    """Return the README with its chart block and table rebuilt from the results."""
    chart = splice_generated(document, render_chart_block(), block="chart")
    return splice_generated(chart, render_table(tools, results), block="table")
