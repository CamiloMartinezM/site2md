"""Custom types shared across the benchmark harness."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    from typing_extensions import NotRequired

JsonValue = None | bool | int | float | str | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
SourceKind = Literal["python", "json", "toml"]
ChartTheme = Literal["light", "dark"]
# The two tasks a tool can solve, and the table columns that a tool's footnote can explain.
TaskName = Literal["page", "crawl"]
FootnoteColumn = Literal["time", "lines", "size", "crawl", "gap"]
PythonFormatter = Callable[[str], str]
# What the fixture server records: the time (perf_counter seconds) and path of each request, in the order logged.
RequestLog = Sequence[tuple[float, str]]


class TimeResult(TypedDict):
    """Wall-clock seconds for one solution, as hyperfine measured them."""

    mean: float
    stddev: float
    median: float
    min: float
    max: float
    times: list[float]


class EnvironmentResult(TypedDict):
    """The software a result was measured with. It deliberately names no hardware or user."""

    os: str
    python: str
    hyperfine: str
    uv: str
    ruff: str


class InstallResult(TypedDict):
    """The installed packages of a tool's smallest working install, and their size on disk."""

    size_bytes: int
    packages: dict[str, str]


class LinesResult(TypedDict):
    """A solution's counted lines, and the lines left out because only the local server needs them."""

    counted: int
    local_only: list[str]


class PageResult(TypedDict):
    """A tool's results for the page task."""

    matches: bool
    time: TimeResult
    lines: LinesResult


class CrawlResult(TypedDict):
    """A tool's results for the crawl task, which runs once and isn't timed."""

    matches: bool
    # The pages that the server's request log shows beyond one fetch of each of the 20 expected pages.
    extra_pages: list[str]
    # Seconds between the two closest child-page requests, or None when there were fewer than two.
    shortest_gap: float | None
    lines: LinesResult


class ToolResult(TypedDict):
    """The content of one tool's committed results file."""

    version: str
    date: str
    environment: EnvironmentResult
    install: InstallResult
    page: PageResult
    # Absent for a tool without a crawler, and in results files from before the crawl task.
    crawl: NotRequired[CrawlResult]
