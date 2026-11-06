"""Custom types shared across the benchmark harness."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    # typing.NotRequired needs Python 3.11, and the harness runs on 3.10.
    from typing_extensions import NotRequired

JsonValue = None | bool | int | float | str | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
SourceKind = Literal["python", "json", "toml"]
ChartMeasure = Literal["time", "size"]
ChartTheme = Literal["light", "dark"]
PythonFormatter = Callable[[str], str]


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
    """A tool's results for the crawl task."""

    matches: bool
    lines: LinesResult


class ToolResult(TypedDict):
    """The content of one tool's committed results file."""

    version: str
    date: str
    environment: EnvironmentResult
    install: InstallResult
    page: PageResult
    # A tool without a crawl solution has no crawl results.
    crawl: NotRequired[CrawlResult]
