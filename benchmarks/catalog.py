"""Load the benchmarked tools from `benchmarks/tools/<id>/tool.json` and count their solutions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from benchmarks._types import JsonValue, PythonFormatter, SourceKind
from benchmarks.line_count import LineCount, count_lines

TOOLS_DIRECTORY = Path(__file__).resolve().parent / "tools"
# The table columns that a footnote can explain.
FOOTNOTE_COLUMNS = ("time", "lines", "size")
TASKS = ("page",)
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
    # A command needed only because the page is served from 127.0.0.1: named, not counted.
    local_only: bool = False


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

    column: str
    text: str


@dataclass(frozen=True)
class Tool:
    """A benchmarked tool: its pinned install, its solutions and its footnotes."""

    id: str
    directory: Path
    name: str
    version: str
    requirements: tuple[str, ...]
    tasks: Mapping[str, Solution]
    # Commands, as argument lists, that run after the requirements and before the size is measured.
    install: tuple[tuple[str, ...], ...] = ()
    # Commands that run after the size is measured, such as installing site2md's benchmark Extractor.
    setup: tuple[tuple[str, ...], ...] = ()
    # Folders of the environment directory to put on PATH, besides the Python environment's own.
    path: tuple[str, ...] = ()
    env: Mapping[str, str] | None = None
    footnotes: tuple[Footnote, ...] = ()


def _object(value: JsonValue, where: str) -> Mapping[str, JsonValue]:
    """Return a JSON object, or raise an error that names where it was expected."""
    if not isinstance(value, Mapping):
        raise TypeError(f"{where} must be an object")
    return value


def _list(value: JsonValue, where: str) -> Sequence[JsonValue]:
    """Return a JSON array, or raise an error that names where it was expected."""
    if not isinstance(value, list):
        raise TypeError(f"{where} must be a list")
    return value


def _string(value: JsonValue, where: str) -> str:
    """Return a JSON string, or raise an error that names where it was expected."""
    if not isinstance(value, str):
        raise TypeError(f"{where} must be a string")
    return value


def _strings(value: JsonValue, where: str) -> tuple[str, ...]:
    """Return a JSON array of strings."""
    return tuple(_string(item, f"{where} items") for item in _list(value, where))


def _commands(value: JsonValue, where: str) -> tuple[tuple[str, ...], ...]:
    """Return a JSON array of argument lists."""
    return tuple(_strings(item, f"{where} items") for item in _list(value, where))


def _keys(
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
    data = _object(value, where)
    _keys(data, required=("run",), optional=("file", "local_only"), where=where)
    file = data.get("file")
    step = Step(
        run=_string(data["run"], f"{where}.run"),
        file=None if file is None else _string(file, f"{where}.file"),
        local_only=data.get("local_only") is True,
    )
    if step.file is not None and step.local_only:
        raise ValueError(f"{where}: local_only applies to commands, not to files")
    return step


def _solution(value: JsonValue, directory: Path, where: str) -> Solution:
    """Read one solution and check that every file it names exists."""
    data = _object(value, where)
    _keys(data, required=("steps",), optional=("files", "output_file"), where=where)
    steps = tuple(
        _step(raw, f"{where}.steps[{index}]")
        for index, raw in enumerate(_list(data["steps"], f"{where}.steps"))
    )
    if not steps:
        raise ValueError(f"{where}: steps must not be empty")
    files = _strings(data.get("files", []), f"{where}.files")
    for name in (*(step.file for step in steps if step.file is not None), *files):
        if not (directory / name).is_file():
            raise ValueError(f"{where}: file '{name}' does not exist in {directory.name}")
    output_file = data.get("output_file")
    return Solution(
        steps, files, None if output_file is None else _string(output_file, f"{where}.output_file")
    )


def _footnote(value: JsonValue, where: str) -> Footnote:
    """Read one footnote and check the column it names."""
    data = _object(value, where)
    _keys(data, required=("column", "text"), optional=(), where=where)
    column = _string(data["column"], f"{where}.column")
    if column not in FOOTNOTE_COLUMNS:
        raise ValueError(f"{where}: column '{column}' is not one of {FOOTNOTE_COLUMNS}")
    return Footnote(column, _string(data["text"], f"{where}.text"))


def _count_file(path: Path, format_python: PythonFormatter) -> LineCount:
    """Count one file by the rules for its type."""
    kind = _SUFFIX_KINDS.get(path.suffix)
    if kind is None:
        raise ValueError(f"{path.name}: there are no line-counting rules for '{path.suffix}' files")
    return count_lines(path.read_text(encoding="utf-8"), kind, format_python=format_python)


def tool_ids() -> tuple[str, ...]:
    """Return the ids of the tool folders, in name order."""
    return tuple(
        sorted(path.name for path in TOOLS_DIRECTORY.iterdir() if (path / "tool.json").is_file())
    )


def load_tool(directory: Path) -> Tool:
    """Load and validate one tool folder's `tool.json`."""
    where = f"{directory.name}/tool.json"
    try:
        loaded = json.loads((directory / "tool.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{where} cannot be read: {error}") from error
    data = _object(loaded, where)
    _keys(
        data,
        required=("name", "version", "requirements", *TASKS),
        optional=("install", "setup", "path", "env", "footnotes"),
        where=where,
    )
    version = _string(data["version"], f"{where}.version")
    environment = data.get("env")
    return Tool(
        id=directory.name,
        directory=directory,
        name=_string(data["name"], f"{where}.name"),
        version=version,
        requirements=tuple(
            requirement.format(version=version)
            for requirement in _strings(data["requirements"], f"{where}.requirements")
        ),
        tasks={task: _solution(data[task], directory, f"{where}.{task}") for task in TASKS},
        install=_commands(data.get("install", []), f"{where}.install"),
        setup=_commands(data.get("setup", []), f"{where}.setup"),
        path=_strings(data.get("path", []), f"{where}.path"),
        env=(
            None
            if environment is None
            else {
                key: _string(item, f"{where}.env.{key}")
                for key, item in _object(environment, f"{where}.env").items()
            }
        ),
        footnotes=tuple(
            _footnote(raw, f"{where}.footnotes[{index}]")
            for index, raw in enumerate(_list(data.get("footnotes", []), f"{where}.footnotes"))
        ),
    )


def count_solution(tool: Tool, task: str, *, format_python: PythonFormatter) -> LineCount:
    """Count a solution: one line per command, plus the lines of every file it needs."""
    solution = tool.tasks[task]
    parts = [
        _count_file(tool.directory / step.file, format_python)
        if step.file is not None
        else LineCount(0, (step.run,))
        if step.local_only
        else LineCount(1, ())
        for step in solution.steps
    ]
    parts.extend(_count_file(tool.directory / name, format_python) for name in solution.files)
    return LineCount(
        sum(part.counted for part in parts),
        tuple(line for part in parts for line in part.local_only),
    )
