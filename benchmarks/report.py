"""Render the committed results into the generated part of BENCHMARKS.md."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from benchmarks._types import TimeResult, ToolResult
from benchmarks.catalog import Tool, load_tool, tool_ids
from benchmarks.page import read_pin
from benchmarks.paths import TOOLS_DIRECTORY
from benchmarks.results import load_results

START_MARKER = "<!-- benchmarks:generated:start -->"
END_MARKER = "<!-- benchmarks:generated:end -->"
# The order of the tools in #40; any other tool follows by name.
TOOL_ORDER = ("site2md", "scrapling", "crawl4ai", "markitdown", "pandoc")
HEADERS = ("Tool", "Version", "Output matches", "Time", "Lines", "Install size", "Packages")


def _time_text(time: TimeResult) -> str:
    """Show a mean and standard deviation in milliseconds below one second, in seconds above."""
    if time["mean"] < 1:
        return f"{time['mean'] * 1000:.0f} ms ± {time['stddev'] * 1000:.0f} ms"
    return f"{time['mean']:.2f} s ± {time['stddev']:.2f} s"


def _local_only_note(lines: Sequence[str]) -> str:
    """Name the lines that were not counted because only the local server needs them."""
    named = ", ".join(f"`{line}`" for line in lines)
    return f"Not counted, because they are needed only to serve the page from 127.0.0.1: {named}."


def _distinct(results: Mapping[str, ToolResult], read: Callable[[ToolResult], str]) -> str:
    """List each value that the results hold, in order."""
    return ", ".join(sorted({read(result) for result in results.values()}))


def _ordered(tools: Sequence[Tool]) -> list[Tool]:
    """Order tools as in #40, then any others by name."""
    return sorted(
        tools,
        key=lambda tool: (TOOL_ORDER.index(tool.id), "") if tool.id in TOOL_ORDER else (len(TOOL_ORDER), tool.id),
    )


def render_results(tools: Sequence[Tool], results: Mapping[str, ToolResult]) -> str:
    """Render the results table, one row per tool that has results, with numbered footnotes."""
    notes: list[str] = []

    def mark(text: str, column_notes: Sequence[str]) -> str:
        """Append a footnote marker per note and remember the note."""
        for note in column_notes:
            notes.append(note)
            text += f" [^{len(notes)}]"
        return text

    lines = [f"| {' | '.join(HEADERS)} |", f"|{'---|' * len(HEADERS)}"]
    for tool in _ordered([tool for tool in tools if tool.id in results]):
        result = results[tool.id]
        page = result["page"]
        by_column = {
            column: [note.text for note in tool.footnotes if note.column == column]
            for column in ("time", "lines", "size")
        }
        if page["lines"]["local_only"]:
            by_column["lines"].append(_local_only_note(page["lines"]["local_only"]))
        cells = (
            tool.name,
            result["version"],
            "yes" if page["matches"] else "no",
            mark(_time_text(page["time"]), by_column["time"]),
            mark(str(page["lines"]["counted"]), by_column["lines"]),
            mark(f"{result['install']['size_bytes'] / 1e6:.1f} MB", by_column["size"]),
            str(len(result["install"]["packages"])),
        )
        lines.append(f"| {' | '.join(cells)} |")
    table = "\n".join(lines) + "\n"
    if not notes:
        return table
    return table + "\n" + "".join(f"[^{number}]: {note}\n" for number, note in enumerate(notes, start=1))


def render_generated(
    tools: Sequence[Tool],
    results: Mapping[str, ToolResult],
    *,
    page_date: str,
    page_sha256: str,
) -> str:
    """Render everything in BENCHMARKS.md that comes from the committed results."""
    measured = _ordered([tool for tool in tools if tool.id in results])
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


def splice_generated(document: str, generated: str) -> str:
    """Replace the text between the generated-block markers, leaving the rest as it is."""
    start = document.find(START_MARKER)
    end = document.find(END_MARKER)
    if start == -1 or end < start:
        raise ValueError(f"the document needs a {START_MARKER} line followed by an {END_MARKER} line")
    return f"{document[: start + len(START_MARKER)]}\n{generated}{document[end:]}"


def render_document(document: str) -> str:
    """Return BENCHMARKS.md with its generated block rebuilt from the committed files."""
    tools = [load_tool(TOOLS_DIRECTORY / tool_id) for tool_id in tool_ids()]
    pin = read_pin()
    generated = render_generated(
        tools, load_results(), page_date=pin.downloaded, page_sha256=pin.sha256
    )
    return splice_generated(document, generated)
