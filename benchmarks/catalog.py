"""Load the benchmarked tools from `benchmarks/tools/<id>/tool.json` and count their solutions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from benchmarks._json import expect_boolean, expect_list, expect_object, expect_string
from benchmarks._types import (
    FootnoteColumn,
    JsonValue,
    PythonFormatter,
    SourceKind,
    TaskName,
)
from benchmarks.errors import HarnessError
from benchmarks.line_count import LineCount, count_lines
from benchmarks.paths import TOOLS_DIRECTORY

FOOTNOTE_COLUMNS: tuple[FootnoteColumn, ...] = get_args(FootnoteColumn)
# Every tool has a page solution. A tool without a crawl solution is shown as having no crawler.
TASKS: tuple[TaskName, ...] = get_args(TaskName)
_SUFFIX_KINDS: Mapping[str, SourceKind] = {
    ".py": "python",
    ".json": "json",
    ".toml": "toml",
}


@dataclass(frozen=True)
class Step:
    """One command of a solution, as a user types it."""

    run: str
    # A Python file that the command runs: its formatted lines count instead of the command.
    file: str | None = None


@dataclass(frozen=True)
class Solution:
    """A tool's solution to one task."""

    steps: tuple[Step, ...]
    # Other files that the solution needs, such as site2md's benchmark Extractor.
    files: tuple[str, ...] = ()
    # Where the last step writes the records; unset means its standard output.
    output_file: str | None = None


@dataclass(frozen=True)
class Footnote:
    """A note on one column of a tool's table row."""

    column: FootnoteColumn
    text: str


@dataclass(frozen=True)
class Tool:
    """A benchmarked tool: its pinned install, its solutions and its footnotes."""

    id: str
    directory: Path
    name: str
    version: str
    # One sentence for BENCHMARKS.md on how this tool solves the tasks.
    solution: str
    requirements: tuple[str, ...]
    tasks: Mapping[TaskName, Solution]
    # Commands, as argument lists, that run after the requirements and before the size is measured.
    install: tuple[tuple[str, ...], ...] = ()
    # Commands that run after the size is measured, such as installing site2md's benchmark Extractor.
    setup: tuple[tuple[str, ...], ...] = ()
    # Folders of the environment directory to put on PATH, besides the Python environment's own.
    path: tuple[str, ...] = ()
    env: Mapping[str, str] | None = None
    footnotes: tuple[Footnote, ...] = ()
    # False keeps the tool in the tables and leaves it out of the chart, as site2md's package is.
    in_chart: bool = True


def _strings(value: JsonValue, where: str) -> tuple[str, ...]:
    """Return a JSON array of strings."""
    return tuple(expect_string(item, f"{where} items") for item in expect_list(value, where))


def _commands(value: JsonValue, where: str) -> tuple[tuple[str, ...], ...]:
    """Return a JSON array of argument lists."""
    return tuple(_strings(item, f"{where} items") for item in expect_list(value, where))


def _check_keys(
    data: Mapping[str, JsonValue], *, required: Sequence[str], optional: Sequence[str], where: str
) -> None:
    """Reject missing and unknown keys, naming each."""
    for key in required:
        if key not in data:
            raise ValueError(f"{where}: missing key '{key}'")
    for key in data:
        if key not in (*required, *optional):
            raise ValueError(f"{where}: unknown key '{key}'")


def _step(value: JsonValue, where: str) -> Step:
    """Read one step of a solution."""
    data = expect_object(value, where)
    _check_keys(data, required=("run",), optional=("file",), where=where)
    file = data.get("file")
    return Step(
        run=expect_string(data["run"], f"{where}.run"),
        file=None if file is None else expect_string(file, f"{where}.file"),
    )


def _solution(value: JsonValue, directory: Path, where: str) -> Solution:
    """Read one solution and check that every file it names exists."""
    data = expect_object(value, where)
    _check_keys(data, required=("steps",), optional=("files", "output_file"), where=where)
    steps = tuple(
        _step(raw, f"{where}.steps[{index}]")
        for index, raw in enumerate(expect_list(data["steps"], f"{where}.steps"))
    )
    if not steps:
        raise ValueError(f"{where}: steps must not be empty")
    files = _strings(data.get("files", []), f"{where}.files")
    for name in (*(step.file for step in steps if step.file is not None), *files):
        if not (directory / name).is_file():
            raise ValueError(f"{where}: file '{name}' does not exist in {directory.name}")
    output_file = data.get("output_file")
    return Solution(
        steps, files, None if output_file is None else expect_string(output_file, f"{where}.output_file")
    )


def _footnote(value: JsonValue, where: str) -> Footnote:
    """Read one footnote and check the column it names."""
    data = expect_object(value, where)
    _check_keys(data, required=("column", "text"), optional=(), where=where)
    named = expect_string(data["column"], f"{where}.column")
    column = next((candidate for candidate in FOOTNOTE_COLUMNS if candidate == named), None)
    if column is None:
        raise ValueError(f"{where}: column '{named}' is not one of {FOOTNOTE_COLUMNS}")
    return Footnote(column, expect_string(data["text"], f"{where}.text"))


def _count_file(path: Path, format_python: PythonFormatter) -> LineCount:
    """Count one file by the rules for its type, naming the file when it can't be counted."""
    kind = _SUFFIX_KINDS.get(path.suffix)
    if kind is None:
        raise HarnessError(f"{path.name}: there are no line-counting rules for '{path.suffix}' files")
    try:
        return count_lines(path.read_text(encoding="utf-8"), kind, format_python=format_python)
    except ValueError as error:
        raise HarnessError(f"{path.name}: {error}") from error


def _read_tool(directory: Path) -> Tool:
    """Read one tool folder's `tool.json`, raising an error that names what is wrong with it."""
    where = f"{directory.name}/tool.json"
    try:
        loaded = json.loads((directory / "tool.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{where} cannot be read: {error}") from error
    data = expect_object(loaded, where)
    _check_keys(
        data,
        required=("name", "version", "solution", "requirements", "page"),
        optional=("crawl", "install", "setup", "path", "env", "footnotes", "in_chart"),
        where=where,
    )
    version = expect_string(data["version"], f"{where}.version")
    environment = data.get("env")
    return Tool(
        id=directory.name,
        directory=directory,
        name=expect_string(data["name"], f"{where}.name"),
        version=version,
        solution=expect_string(data["solution"], f"{where}.solution"),
        requirements=tuple(
            requirement.format(version=version)
            for requirement in _strings(data["requirements"], f"{where}.requirements")
        ),
        tasks={task: _solution(data[task], directory, f"{where}.{task}") for task in TASKS if task in data},
        install=_commands(data.get("install", []), f"{where}.install"),
        setup=_commands(data.get("setup", []), f"{where}.setup"),
        path=_strings(data.get("path", []), f"{where}.path"),
        env=(
            None
            if environment is None
            else {
                key: expect_string(item, f"{where}.env.{key}")
                for key, item in expect_object(environment, f"{where}.env").items()
            }
        ),
        footnotes=tuple(
            _footnote(raw, f"{where}.footnotes[{index}]")
            for index, raw in enumerate(expect_list(data.get("footnotes", []), f"{where}.footnotes"))
        ),
        in_chart=expect_boolean(data.get("in_chart", True), f"{where}.in_chart"),
    )


def tool_ids() -> tuple[str, ...]:
    """Return the ids of the tool folders, in name order."""
    return tuple(
        sorted(path.name for path in TOOLS_DIRECTORY.iterdir() if (path / "tool.json").is_file())
    )


def load_tool(directory: Path) -> Tool:
    """Load and validate one tool folder's `tool.json`, reporting a malformed one as a harness error."""
    try:
        return _read_tool(directory)
    except (ValueError, TypeError) as error:
        # ValueError: a bad value or key. TypeError: a value of the wrong JSON type, from the expect_* helpers.
        raise HarnessError(str(error)) from error


def count_solution(tool: Tool, task: TaskName, *, format_python: PythonFormatter) -> LineCount:
    """Count a solution: one line per command, plus the lines of every file it needs."""
    solution = tool.tasks[task]
    parts = [
        LineCount(1, ()) if step.file is None else _count_file(tool.directory / step.file, format_python)
        for step in solution.steps
    ]
    parts.extend(_count_file(tool.directory / name, format_python) for name in solution.files)
    return LineCount(
        sum(part.counted for part in parts),
        tuple(line for part in parts for line in part.local_only),
    )
