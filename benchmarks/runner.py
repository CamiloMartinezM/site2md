"""Run one tool's page task end to end, and rebuild the reference from site2md's built-in Extractor."""

from __future__ import annotations

import datetime
import json
import platform
import shutil
import subprocess
import sys

from benchmarks._json import expect_list, expect_object
from benchmarks._types import JsonValue, ToolResult
from benchmarks.catalog import Solution, Tool, count_solution, load_tool
from benchmarks.compare import first_difference
from benchmarks.environment import (
    HYPERFINE_HINT,
    UV_HINT,
    find_program,
    fresh_directory,
    install_tool,
    run_command,
)
from benchmarks.errors import HarnessError
from benchmarks.files import write_atomically
from benchmarks.line_count import RUFF_VERSION, format_with_ruff
from benchmarks.page import PAGE_PATH, ensure_page, refresh_page
from benchmarks.paths import CACHE_DIRECTORY, REFERENCE, TOOLS_DIRECTORY
from benchmarks.server import FixtureServer
from benchmarks.timing import run_hyperfine

# Where the last step's standard output goes, unless the solution names its own output file.
OUTPUT_FILE = "output.json"
REFERENCE_TOOL = "site2md"
BUILT_IN_EXTRACTOR = "site2md.scrapethissite.countries"


def _program_version(program: str) -> str:
    """Return the version that `<program> --version` prints as its second word."""
    completed = subprocess.run([program, "--version"], capture_output=True, text=True, encoding="utf-8", check=True)
    return completed.stdout.split()[1]


def _load_reference() -> JsonValue:
    """Return the committed reference records."""
    try:
        reference: JsonValue = json.loads(REFERENCE.read_text(encoding="utf-8"))
    except OSError as error:
        raise HarnessError(f"there is no reference ({error}): run `python -m benchmarks reference` first") from error
    return reference


def build_command(solution: Solution, url: str) -> str:
    """Join a solution's steps into the one command line that is timed, with `{url}` filled in."""
    try:
        commands = [step.run.format_map({"url": url}) for step in solution.steps]
    except KeyError as error:
        raise HarnessError(f"unknown placeholder {error} in a step; only {{url}} is available") from error
    if solution.output_file is None:
        commands[-1] += f" > {OUTPUT_FILE}"
    return " && ".join(commands)


def run_tool(tool: Tool) -> tuple[ToolResult, str | None]:
    """Run the page task for one tool, and return its results and the first difference, if any."""
    hyperfine = find_program("hyperfine", HYPERFINE_HINT)
    uv = find_program("uv", UV_HINT)
    page, downloaded = ensure_page()
    print(f"Page copy: {'downloaded' if downloaded else 'reused from the cache'}.")
    reference = _load_reference()
    print(f"Installing {tool.name} {tool.version}...")
    environment, install = install_tool(tool)
    solution = tool.tasks["page"]
    work = fresh_directory(CACHE_DIRECTORY / "work" / tool.id)
    for step in solution.steps:
        if step.file is not None:
            shutil.copy(tool.directory / step.file, work)
    print("Timing the page task...")
    with FixtureServer({PAGE_PATH: page.read_bytes()}) as server:
        time = run_hyperfine(
            hyperfine,
            build_command(solution, server.origin + PAGE_PATH),
            cwd=work,
            variables=environment.variables,
            export=work / "hyperfine.json",
        )
    output = work / (solution.output_file or OUTPUT_FILE)
    if not output.is_file():
        raise HarnessError(f"the solution wrote no {output.name}")
    difference = first_difference(output.read_text(encoding="utf-8"), reference)
    ruff = ("uv", "tool", "run", "--no-config", "--from", f"ruff=={RUFF_VERSION}", "ruff")
    lines = count_solution(
        tool,
        "page",
        format_python=lambda source: format_with_ruff(source, command=ruff, env=environment.variables),
    )
    result: ToolResult = {
        "version": tool.version,
        "date": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "environment": {
            "os": f"{platform.system()} {platform.release()}",
            "python": environment.python_version,
            "hyperfine": _program_version(hyperfine),
            "uv": _program_version(uv),
            "ruff": RUFF_VERSION,
        },
        "install": install,
        "page": {
            "matches": difference is None,
            "time": time,
            "lines": {"counted": lines.counted, "local_only": list(lines.local_only)},
        },
    }
    return result, difference


def build_reference() -> int:
    """Download the page afresh, pin it, and rebuild the reference records with the built-in Extractor."""
    find_program("uv", UV_HINT)
    page = refresh_page()
    print("Page copy: downloaded and pinned.")
    environment, _ = install_tool(load_tool(TOOLS_DIRECTORY / REFERENCE_TOOL))
    work = fresh_directory(CACHE_DIRECTORY / "work" / "reference")
    site2md = str(environment.scripts / ("site2md.exe" if sys.platform == "win32" else "site2md"))
    with FixtureServer({PAGE_PATH: page.read_bytes()}) as server:
        for command in (
            [site2md, "build", server.origin + PAGE_PATH, "--output", "page.md"],
            [site2md, "extract", BUILT_IN_EXTRACTOR, "page.md", "--output", "result.json"],
        ):
            run_command(command, variables=environment.variables, cwd=work)
    result = expect_object(json.loads((work / "result.json").read_text(encoding="utf-8")), "extraction result")
    records = [expect_object(record, "record")["value"] for record in expect_list(result["records"], "records")]
    # One record per line keeps the committed file readable and its diffs small.
    lines = ",\n".join(f"  {json.dumps(record, ensure_ascii=False)}" for record in records)
    write_atomically(REFERENCE, f"[\n{lines}\n]\n".encode())
    return len(records)
