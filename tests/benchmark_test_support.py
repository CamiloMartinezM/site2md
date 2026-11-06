"""Build the tools and results that the chart and README tests render."""

from __future__ import annotations

from pathlib import Path

from benchmarks._types import ToolResult
from benchmarks.catalog import Footnote, Solution, Step, Tool


def _country_block(number: int) -> str:
    """Write one country block as the page copy does."""
    return f"""
                    <div class="col-md-4 country">
                        <h3 class="country-name">
                            <i class="flag-icon flag-icon-xx"></i>
                            Country {number}
                        </h3>
                        <div class="country-info">
                            <strong>Capital:</strong> <span class="country-capital">Capital {number}</span><br>
                            <strong>Population:</strong> <span class="country-population">{number}00</span><br>
                            <strong>Area (km<sup>2</sup>):</strong> <span class="country-area">{number}.5</span><br>
                        </div>
                    </div><!--.col-->
"""


def make_page(count: int = 43) -> str:
    """Return a page copy with a menu, an attribution link and `count` countries, as the real page has them."""
    return f"""<!doctype html>
<html><head><title>Countries</title><link href="/static/css/styles.css" rel="stylesheet"></head>
<body>
<nav id="site-nav"><ul>
<li><a href="/" class="nav-link hidden-sm">
    <img src="/static/images/icon.png"> Scrape This Site
</a></li>
<li><a href="/pages/" class="nav-link">Sandbox</a></li>
<li><a href="/faq/">FAQ</a></li>
</ul></nav>
<div id="page">
<section id="countries">
<div class="container">
<h1>Countries <small>{count} items</small></h1>
<p>There are <a href="/lessons/">4 video lessons</a>. Data via
<a href="http://peric.github.io/GetCountries/" class="data-attribution">peric</a></p>
<div class="row">
{"".join(_country_block(number) for number in range(1, count + 1))}
</div>
</div>
</section>
</div>
<footer>Footer</footer>
</body></html>
"""


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
