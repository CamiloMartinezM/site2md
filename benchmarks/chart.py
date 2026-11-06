"""Choose the README chart's measure and render the chart as an SVG."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from xml.sax.saxutils import escape

from benchmarks._types import ChartMeasure, ChartTheme, ToolResult
from benchmarks.catalog import Tool
from benchmarks.report import measured_tools

# The tool the README is about: the chart shows time only if this tool is the fastest.
SUBJECT = "site2md"
_BAR_COLOUR = "#0969DA"
_GRID_COLOUR = "#7F7F7F"
_TEXT_COLOURS: Mapping[ChartTheme, str] = {"light": "#333333", "dark": "#C9D1D9"}
_FONT_FAMILY = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
_FONT_SIZE = 12
_PLOT_WIDTH = 400
_ROW_HEIGHT = 22
_BAR_HEIGHT = 14
_AXIS_HEIGHT = 22
_GAP = 8
# shortcut: label widths are estimated at 7.5 px a character, not measured; use a font library if a label clips.
_CHARACTER_WIDTH = 7.5
_VALUE_FORMATS: Mapping[ChartMeasure, str] = {"time": "{:.2f}s", "size": "{:.1f} MB"}
_TICK_FORMATS: Mapping[ChartMeasure, str] = {"time": "{:g}s", "size": "{:g} MB"}
_TITLES: Mapping[ChartMeasure, str] = {
    "time": "Time each tool takes to extract the countries",
    "size": "Disk space each tool's smallest install uses",
}


@dataclass(frozen=True)
class _Row:
    """One bar: a tool's name, its value in seconds or megabytes, and whether the chart stresses it."""

    name: str
    value: float
    stressed: bool


def _value(measure: ChartMeasure, result: ToolResult) -> float:
    """Read the charted value of a result: mean seconds, or install megabytes."""
    return result["page"]["time"]["mean"] if measure == "time" else result["install"]["size_bytes"] / 1e6


def _rows(tools: Sequence[Tool], results: Mapping[str, ToolResult], measure: ChartMeasure) -> list[_Row]:
    """List the bars, smallest first: only tools whose output matches the reference have one."""
    rows = [
        _Row(tool.name, _value(measure, results[tool.id]), tool.id == SUBJECT)
        for tool in measured_tools(tools, results)
        if results[tool.id]["page"]["matches"]
    ]
    return sorted(rows, key=lambda row: row.value)


def _ticks(maximum: float) -> list[float]:
    """Return the axis values: 0, then multiples of a round step, up to the first one at or past the maximum."""
    raw_step = maximum / 4
    magnitude = 10 ** math.floor(math.log10(raw_step))
    step = next(factor * magnitude for factor in (1, 2, 5, 10) if factor * magnitude >= raw_step)
    return [step * index for index in range(math.ceil(maximum / step) + 1)]


def choose_measure(results: Mapping[str, ToolResult]) -> ChartMeasure:
    """Pick time if the subject has the lowest mean among the tools whose output matches, else install size."""
    matching = {tool_id: result["page"] for tool_id, result in results.items() if result["page"]["matches"]}
    if SUBJECT not in matching:
        return "size"
    fastest = min(page["time"]["mean"] for page in matching.values())
    return "time" if matching[SUBJECT]["time"]["mean"] <= fastest else "size"


def render_chart(
    tools: Sequence[Tool],
    results: Mapping[str, ToolResult],
    measure: ChartMeasure,
    theme: ChartTheme,
) -> str:
    """Render the horizontal bar chart as an SVG, in the colours of one theme."""
    rows = _rows(tools, results, measure)
    texts = [_VALUE_FORMATS[measure].format(row.value) for row in rows]
    ticks = _ticks(max((row.value for row in rows), default=1))
    left = max((len(row.name) for row in rows), default=0) * _CHARACTER_WIDTH + _GAP
    right = max((len(text) for text in texts), default=0) * _CHARACTER_WIDTH + _GAP
    scale = _PLOT_WIDTH / ticks[-1]
    width = left + _PLOT_WIDTH + right
    plot_height = len(rows) * _ROW_HEIGHT
    marks = [
        f'<line x1="{left + tick * scale:.1f}" y1="0" x2="{left + tick * scale:.1f}" y2="{plot_height}"/>'
        for tick in ticks
    ]
    marks[0] = f'<g stroke="{_GRID_COLOUR}" stroke-opacity="0.25">{marks[0]}'
    marks[-1] += "</g>"
    for tick in ticks:
        x = left + tick * scale
        marks.append(
            f'<text x="{x:.1f}" y="{plot_height + _AXIS_HEIGHT - 6}" text-anchor="middle">'
            f"{_TICK_FORMATS[measure].format(tick)}</text>"
        )
    for index, (row, text) in enumerate(zip(rows, texts, strict=True)):
        top = index * _ROW_HEIGHT + (_ROW_HEIGHT - _BAR_HEIGHT) / 2
        baseline = top + _BAR_HEIGHT - 2
        weight = ' font-weight="bold"' if row.stressed else ""
        bar_width = row.value * scale
        marks.append(
            f'<rect x="{left:g}" y="{top:g}" width="{bar_width:.1f}" height="{_BAR_HEIGHT}" fill="{_BAR_COLOUR}"/>'
            f'<text x="{left - _GAP:g}" y="{baseline:g}" text-anchor="end"{weight}>{escape(row.name)}</text>'
            f'<text x="{left + bar_width + _GAP:.1f}" y="{baseline:g}"{weight}>{text}</text>'
        )
    height = plot_height + _AXIS_HEIGHT
    description = ", ".join(f"{row.name} {text}" for row, text in zip(rows, texts, strict=True))
    opening = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" height="{height}" viewBox="0 0 {width:g} {height}" '
        f'role="img" font-family="{_FONT_FAMILY}" font-size="{_FONT_SIZE}" fill="{_TEXT_COLOURS[theme]}">'
    )
    parts = [opening, f"<title>{_TITLES[measure]}</title>", f"<desc>{escape(description)}</desc>", *marks, "</svg>"]
    return "\n".join(parts) + "\n"
