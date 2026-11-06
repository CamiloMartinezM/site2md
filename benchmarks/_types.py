"""Custom types shared across the benchmark harness."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Literal, TypedDict

JsonValue = None | bool | int | float | str | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
SourceKind = Literal["python", "json", "toml"]
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


class ToolResult(TypedDict):
    """The content of one tool's committed results file."""

    version: str
    date: str
    environment: EnvironmentResult
    install: InstallResult
    page: PageResult
