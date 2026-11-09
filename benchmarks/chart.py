"""Render the README chart: two bars per tool, its install size and the time of the page task, as an SVG."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from xml.sax.saxutils import escape

from benchmarks._types import ChartTheme, ToolResult
from benchmarks.catalog import Tool
from benchmarks.report import measured_tools, size_text

# The tool the README is about: the chart sets its name and values in bold.
SUBJECT = "site2md"
# Blue for install size and orange for time. The dataviz skill's validator passes each pair, for colour-blind
# readers and for 3:1 contrast, on GitHub's page colours: light on #ffffff and dark on #0d1117.
_SIZE_COLOURS: Mapping[ChartTheme, str] = {"light": "#2A78D6", "dark": "#3987E5"}
_TIME_COLOURS: Mapping[ChartTheme, str] = {"light": "#EB6834", "dark": "#D95926"}
_TEXT_COLOURS: Mapping[ChartTheme, str] = {"light": "#333333", "dark": "#C9D1D9"}
_NOTE_COLOURS: Mapping[ChartTheme, str] = {"light": "#57606A", "dark": "#8B949E"}
_LEGEND_LABELS = ("Install size", "Time")
_NOTE = "Each measure has its own scale"
_FONT_FAMILY = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
_FONT_SIZE = 12
_PLOT_WIDTH = 400
_BAR_HEIGHT = 12
# The surface shows between the two bars of a tool, so that they read as two marks.
_BAR_GAP = 2
_PAIR_HEIGHT = 2 * _BAR_HEIGHT + _BAR_GAP
_ROW_HEIGHT = _PAIR_HEIGHT + 12
_LEGEND_HEIGHT = 24
_SWATCH = 10
_GAP = 8
# shortcut: label widths are estimated at 7.5 px a character, not measured; use a font library if a label clips.
_CHARACTER_WIDTH = 7.5


@dataclass(frozen=True)
class _Row:
    """One tool's pair of bars: its name, install size in bytes and mean time in seconds."""

    name: str
    size_bytes: int
    seconds: float
    stressed: bool


def _rows(tools: Sequence[Tool], results: Mapping[str, ToolResult]) -> list[_Row]:
    """List the rows, smallest install first: only tools whose output matches the reference have one."""
    rows = [
        _Row(
            tool.name,
            results[tool.id]["install"]["size_bytes"],
            results[tool.id]["page"]["time"]["mean"],
            tool.id == SUBJECT,
        )
        for tool in measured_tools(tools, results)
        if results[tool.id]["page"]["matches"]
    ]
    return sorted(rows, key=lambda row: row.size_bytes)


def _time_text(seconds: float) -> str:
    """Show a mean time in milliseconds below one second and in seconds above, as the README's table does."""
    return f"{seconds * 1000:.0f} ms" if seconds < 1 else f"{seconds:.2f} s"


def render_chart(tools: Sequence[Tool], results: Mapping[str, ToolResult], theme: ChartTheme) -> str:
    """Render the horizontal bar chart as an SVG, in the colours of one theme."""
    rows = _rows(tools, results)
    size_labels = [size_text(row.size_bytes) for row in rows]
    time_labels = [_time_text(row.seconds) for row in rows]
    # Each measure has its own unit, so each is scaled to its own largest value and nothing suggests a shared axis.
    longest_size = max((row.size_bytes for row in rows), default=1)
    longest_time = max((row.seconds for row in rows), default=1)
    left = max((len(row.name) for row in rows), default=0) * _CHARACTER_WIDTH + _GAP
    right = max((len(label) for label in [*size_labels, *time_labels]), default=0) * _CHARACTER_WIDTH + _GAP
    width = left + _PLOT_WIDTH + right
    height = _LEGEND_HEIGHT + len(rows) * _ROW_HEIGHT
    colours = (_SIZE_COLOURS[theme], _TIME_COLOURS[theme])
    legend = []
    legend_x = left
    for label, colour in zip(_LEGEND_LABELS, colours, strict=True):
        legend.append(
            f'<rect x="{legend_x:g}" y="6" width="{_SWATCH}" height="{_SWATCH}" fill="{colour}"/>'
            f'<text x="{legend_x + _SWATCH + 6:g}" y="15">{label}</text>'
        )
        legend_x += _SWATCH + 6 + len(label) * _CHARACTER_WIDTH + 16
    marks = [
        f'<g class="legend">{"".join(legend)}</g>',
        f'<text x="{width:g}" y="15" text-anchor="end" fill="{_NOTE_COLOURS[theme]}">{_NOTE}</text>',
    ]
    for index, (row, size_label, time_label) in enumerate(zip(rows, size_labels, time_labels, strict=True)):
        top = _LEGEND_HEIGHT + index * _ROW_HEIGHT + (_ROW_HEIGHT - _PAIR_HEIGHT) / 2
        weight = ' font-weight="bold"' if row.stressed else ""
        name_y = top + _PAIR_HEIGHT / 2 + 4
        pair = [f'<text x="{left - _GAP:g}" y="{name_y:g}" text-anchor="end"{weight}>{escape(row.name)}</text>']
        bars = (
            (row.size_bytes / longest_size, colours[0], size_label),
            (row.seconds / longest_time, colours[1], time_label),
        )
        for position, (share, colour, label) in enumerate(bars):
            bar_top = top + position * (_BAR_HEIGHT + _BAR_GAP)
            bar_width = share * _PLOT_WIDTH
            pair.append(
                f'<rect x="{left:g}" y="{bar_top:g}" width="{bar_width:.1f}" height="{_BAR_HEIGHT}" fill="{colour}"/>'
                f'<text x="{left + bar_width + _GAP:.1f}" y="{bar_top + _BAR_HEIGHT - 2:g}"{weight}>{label}</text>'
            )
        marks.append(f'<g class="row">{"".join(pair)}</g>')
    description = "; ".join(
        f"{row.name}: {size_label}, {time_label}"
        for row, size_label, time_label in zip(rows, size_labels, time_labels, strict=True)
    )
    opening = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" height="{height:g}" '
        f'viewBox="0 0 {width:g} {height:g}" role="img" font-family="{_FONT_FAMILY}" font-size="{_FONT_SIZE}" '
        f'fill="{_TEXT_COLOURS[theme]}">'
    )
    title = "Install size and time each tool takes to extract the countries"
    lines = [opening, f"<title>{title}</title>", f"<desc>{escape(description)}</desc>", *marks, "</svg>"]
    return "\n".join(lines) + "\n"
