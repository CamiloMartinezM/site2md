"""Render the committed results into the generated part of BENCHMARKS.md, and share the table pieces with the README."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence

from benchmarks._types import FootnoteColumn, LinesResult, TimeResult, ToolResult
from benchmarks.catalog import Tool

# The order of the tools in #40; any other tool follows by name.
TOOL_ORDER = ("site2md", "scrapling", "crawl4ai", "markitdown", "pandoc")
HEADERS = (
    "Tool",
    "Version",
    "Output matches",
    "Time",
    "Lines",
    "Install size",
    "Packages",
    "Crawl output matches",
    "Extra pages",
    "Shortest gap",
    "Crawl lines",
)
NO_CRAWLER = "no crawler"


class Footnotes:
    """Numbers a table's notes in the order its cells first cite them, and lists each note once."""

    def __init__(self) -> None:
        self._notes: list[str] = []

    def mark(self, text: str, notes: Iterable[str]) -> str:
        """Append a marker to a cell's text for each note, however many cells share the note."""
        for note in notes:
            if note not in self._notes:
                self._notes.append(note)
            text += f" [^{self._notes.index(note) + 1}]"
        return text

    def render(self) -> str:
        """Return the footnote lines that go under the table, or nothing if no cell cited a note."""
        return "".join(f"[^{number}]: {note}\n" for number, note in enumerate(self._notes, start=1))


def _distinct(results: Mapping[str, ToolResult], read: Callable[[ToolResult], str]) -> str:
    """List each value that the results hold, in order."""
    return ", ".join(sorted({read(result) for result in results.values()}))


def _results_row(tool: Tool, result: ToolResult, footnotes: Footnotes) -> list[str]:
    """Build one row of the results table, with the footnote markers of its cells."""
    page = result["page"]
    cells = [
        tool.name,
        result["version"],
        "yes" if page["matches"] else "no",
        footnotes.mark(time_text(page["time"]), column_notes(tool, "time")),
        footnotes.mark(
            str(page["lines"]["counted"]), [*column_notes(tool, "lines"), *local_only_notes(page["lines"])]
        ),
        footnotes.mark(size_text(result["install"]["size_bytes"]), column_notes(tool, "size")),
        str(len(result["install"]["packages"])),
    ]
    crawl = result.get("crawl")
    if crawl is None:
        return [*cells, *[NO_CRAWLER] * 4]
    return [
        *cells,
        footnotes.mark("yes" if crawl["matches"] else "no", column_notes(tool, "crawl")),
        str(len(crawl["extra_pages"])),
        footnotes.mark(gap_text(crawl["shortest_gap"]), column_notes(tool, "gap")),
        footnotes.mark(str(crawl["lines"]["counted"]), local_only_notes(crawl["lines"])),
    ]


def time_text(time: TimeResult) -> str:
    """Show a mean and standard deviation in milliseconds below one second, in seconds above."""
    if time["mean"] < 1:
        return f"{time['mean'] * 1000:.0f} ms ± {time['stddev'] * 1000:.0f} ms"
    return f"{time['mean']:.2f} s ± {time['stddev']:.2f} s"


def size_text(size_bytes: int) -> str:
    """Show an install size in megabytes."""
    return f"{size_bytes / 1e6:.1f} MB"


def gap_text(gap: float | None) -> str:
    """Show the shortest gap between child-page requests in seconds, to the millisecond."""
    return "n/a" if gap is None else f"{gap:.3f} s"


def column_notes(tool: Tool, column: FootnoteColumn) -> list[str]:
    """List the notes that a tool's definition attaches to one column."""
    return [note.text for note in tool.footnotes if note.column == column]


def local_only_notes(lines: LinesResult) -> list[str]:
    """Return the note that names the lines left out of a count, or nothing if none were left out."""
    if not lines["local_only"]:
        return []
    named = ", ".join(f"`{line}`" for line in lines["local_only"])
    return [
        (
            f"Not counted: {named}. The harness passes the local server's 127.0.0.1 URL on the command line, "
            "and this code only reads it. A solution for the live site writes the URL inline."
        )
    ]


def measured_tools(tools: Sequence[Tool], results: Mapping[str, ToolResult]) -> list[Tool]:
    """Return the tools that have results, in the order of #40 and then any others by name."""
    return sorted(
        (tool for tool in tools if tool.id in results),
        key=lambda tool: (TOOL_ORDER.index(tool.id), "") if tool.id in TOOL_ORDER else (len(TOOL_ORDER), tool.id),
    )


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]], footnotes: Footnotes) -> str:
    """Render a Markdown table, with the notes that its cells cite listed under it."""
    lines = [
        f"| {' | '.join(headers)} |",
        f"|{'---|' * len(headers)}",
        *(f"| {' | '.join(row)} |" for row in rows),
    ]
    table = "\n".join(lines) + "\n"
    notes = footnotes.render()
    return f"{table}\n{notes}" if notes else table


def render_results(tools: Sequence[Tool], results: Mapping[str, ToolResult]) -> str:
    """Render the results table, one row per tool that has results, with numbered footnotes."""
    footnotes = Footnotes()
    rows = [_results_row(tool, results[tool.id], footnotes) for tool in measured_tools(tools, results)]
    return markdown_table(HEADERS, rows, footnotes)


def render_generated(
    tools: Sequence[Tool],
    results: Mapping[str, ToolResult],
    *,
    page_date: str,
    page_sha256: str,
) -> str:
    """Render everything in BENCHMARKS.md that comes from the committed results."""
    measured = measured_tools(tools, results)
    versions = [
        f"| {tool.name} | {results[tool.id]['version']} | {results[tool.id]['date']} "
        f"| [{tool.id}.json](benchmarks/results/{tool.id}.json) |\n"
        for tool in measured
    ]
    solutions = "".join(f"- **{tool.name}**: {tool.solution}\n" for tool in measured)
    return (
        "### Page copy\n\n"
        f"The page copy was downloaded on {page_date}. Its SHA-256 is `{page_sha256}`.\n\n"
        "### Machine and software\n\n"
        f"- OS: {_distinct(results, lambda result: result['environment']['os'])}\n"
        f"- Python in the tool environments: {_distinct(results, lambda result: result['environment']['python'])}\n"
        f"- hyperfine: {_distinct(results, lambda result: result['environment']['hyperfine'])}\n"
        f"- uv: {_distinct(results, lambda result: result['environment']['uv'])}\n"
        f"- ruff, which formats the Python before its lines are counted: "
        f"{_distinct(results, lambda result: result['environment']['ruff'])}\n\n"
        "### Times, lines and install size\n\n"
        f"{render_results(tools, results)}\n"
        "### Solutions\n\n"
        f"{solutions}\n"
        "### Versions and raw results\n\n"
        "| Tool | Version | Date | Raw results |\n"
        "|---|---|---|---|\n"
        f"{''.join(versions)}"
    )


def splice_generated(document: str, generated: str, *, block: str = "generated") -> str:
    """Replace the text between a block's markers, leaving the rest as it is."""
    start_marker = f"<!-- benchmarks:{block}:start -->"
    end_marker = f"<!-- benchmarks:{block}:end -->"
    start = document.find(start_marker)
    end = document.find(end_marker)
    if start == -1 or end < start:
        raise ValueError(f"the document needs a {start_marker} line followed by an {end_marker} line")
    return f"{document[: start + len(start_marker)]}\n{generated}{document[end:]}"
