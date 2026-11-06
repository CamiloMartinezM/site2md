"""Build the tools and results that the chart and README tests render."""

from __future__ import annotations

from pathlib import Path

from benchmarks._types import ToolResult
from benchmarks.catalog import Footnote, Solution, Step, Tool


def make_tool(
    tool_id: str, *footnotes: Footnote, name: str | None = None, has_crawl_solution: bool = False
) -> Tool:
    """Return a tool that has only the fields the renderers read."""
    return Tool(
        id=tool_id,
        directory=Path(),
        name=name or tool_id,
        version="1",
        solution=f"The solution of {tool_id}.",
        requirements=(),
        tasks={"crawl": Solution(steps=(Step(run="crawl"),))} if has_crawl_solution else {},
        footnotes=footnotes,
    )


def make_result(
    *,
    mean: float = 0.661,
    size_bytes: int = 11_500_000,
    lines: int = 54,
    local_only: tuple[str, ...] = (),
    matches: bool = True,
    crawl_lines: int | None = None,
    crawl_local_only: tuple[str, ...] = (),
) -> ToolResult:
    """Return a results file's content with the values a test cares about."""
    result: ToolResult = {
        "version": "1.0",
        "date": "2026-11-06",
        "environment": {
            "os": "Windows 11",
            "python": "3.12.14",
            "hyperfine": "2.0.0",
            "uv": "0.12.21",
            "ruff": "0.17.4",
        },
        "install": {"size_bytes": size_bytes, "packages": {"package": "1.0"}},
        "page": {
            "matches": matches,
            "time": {
                "mean": mean,
                "stddev": 0.01,
                "median": mean,
                "min": mean,
                "max": mean,
                "times": [mean],
            },
            "lines": {"counted": lines, "local_only": list(local_only)},
        },
    }
    if crawl_lines is not None:
        result["crawl"] = {
            "matches": True,
            "extra_pages": [],
            "shortest_gap": 1.0,
            "lines": {"counted": crawl_lines, "local_only": list(crawl_local_only)},
        }
    return result
