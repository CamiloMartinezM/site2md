"""Run one tool's page task end to end, and rebuild the reference from site2md's built-in Extractor."""

from __future__ import annotations

import datetime
import json
import platform
import shutil
import subprocess
from pathlib import Path

from benchmarks._json import expect_list, expect_object
from benchmarks._types import CrawlResult, JsonValue, PythonFormatter, ToolResult
from benchmarks.catalog import Solution, Tool, count_solution, load_tool
from benchmarks.compare import first_difference, unordered_difference
from benchmarks.crawl import START_PATH, build_site, extra_pages, shortest_gap
from benchmarks.environment import (
    HYPERFINE_HINT,
    UV_HINT,
    Environment,
    check_programs,
    find_program,
    fresh_directory,
    install_tool,
    run_command,
    run_shell_command,
    venv_program,
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


def _prepare_work(tool: Tool, solution: Solution, name: str) -> Path:
    """Return an empty work folder that holds a copy of each Python file the solution runs."""
    work = fresh_directory(CACHE_DIRECTORY / "work" / name)
    for step in solution.steps:
        if step.file is not None:
            shutil.copy(tool.directory / step.file, work)
    return work


def _read_output(work: Path, solution: Solution) -> str:
    """Return what the solution's last step wrote, which is the records."""
    output = work / (solution.output_file or OUTPUT_FILE)
    if not output.is_file():
        raise HarnessError(f"the solution wrote no {output.name}")
    return output.read_text(encoding="utf-8")


def _crawl_difference(status: int, work: Path, solution: Solution, reference: JsonValue) -> str | None:
    """Return why a crawl doesn't count as working, or None when its output matches the reference."""
    if status != 0:
        return f"the solution exited with status {status}, so it does not count as working"
    try:
        output = _read_output(work, solution)
    except HarnessError as error:
        return str(error)
    return unordered_difference(output, reference)


def build_command(solution: Solution, url: str) -> str:
    """Join a solution's steps into the one command line that is timed, with `{url}` filled in."""
    try:
        commands = [step.run.format_map({"url": url}) for step in solution.steps]
    except KeyError as error:
        raise HarnessError(f"unknown placeholder {error} in a step; only {{url}} is available") from error
    if solution.output_file is None:
        commands[-1] += f" > {OUTPUT_FILE}"
    return " && ".join(commands)


def run_crawl(
    tool: Tool, environment: Environment, page: Path, reference: JsonValue, format_python: PythonFormatter
) -> tuple[CrawlResult, str | None]:
    """Run the crawl task once, untimed, and check its output and the server's request log."""
    solution = tool.tasks["crawl"]
    site = build_site(page.read_text(encoding="utf-8"))
    work = _prepare_work(tool, solution, f"{tool.id}-crawl")
    with FixtureServer(site.pages) as server:
        status = run_shell_command(
            build_command(solution, server.origin + START_PATH), variables=environment.variables, cwd=work
        )
    difference = _crawl_difference(status, work, solution, reference)
    lines = count_solution(tool, "crawl", format_python=format_python)
    gap = shortest_gap(server.requests)
    result: CrawlResult = {
        "matches": difference is None,
        "extra_pages": extra_pages(server.requests, site.expected),
        # Microseconds, like the times: finer than the server's clock.
        "shortest_gap": None if gap is None else round(gap, 6),
        "lines": {"counted": lines.counted, "local_only": list(lines.local_only)},
    }
    return result, difference


def run_tool(tool: Tool) -> tuple[ToolResult, list[str]]:
    """Run the tool's tasks, and return its results and the first difference from the reference in each task."""
    hyperfine = find_program("hyperfine", HYPERFINE_HINT)
    uv = find_program("uv", UV_HINT)
    page, downloaded = ensure_page()
    print(f"Page copy: {'downloaded' if downloaded else 'reused from the cache'}.")
    reference = _load_reference()
    print(f"Installing {tool.name} {tool.version}...")
    environment, install = install_tool(tool)
    # The published numbers must come from the pinned install, so no step may fall back to the machine's program.
    check_programs(
        (program for task in tool.tasks.values() for step in task.steps for program in step.run.split()[:1]),
        path=environment.variables["PATH"],
        inside=CACHE_DIRECTORY,
    )
    solution = tool.tasks["page"]
    work = _prepare_work(tool, solution, tool.id)
    print("Timing the page task...")
    with FixtureServer({PAGE_PATH: page.read_bytes()}) as server:
        time = run_hyperfine(
            hyperfine,
            build_command(solution, server.origin + PAGE_PATH),
            cwd=work,
            variables=environment.variables,
            export=work / "hyperfine.json",
        )
    page_difference = first_difference(_read_output(work, solution), reference)
    ruff = ("uv", "tool", "run", "--no-config", "--from", f"ruff=={RUFF_VERSION}", "ruff")

    def format_python(source: str) -> str:
        return format_with_ruff(source, command=ruff, env=environment.variables)

    lines = count_solution(tool, "page", format_python=format_python)
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
            "matches": page_difference is None,
            "time": time,
            "lines": {"counted": lines.counted, "local_only": list(lines.local_only)},
        },
    }
    differences = [] if page_difference is None else [f"page task: {page_difference}"]
    if "crawl" in tool.tasks:
        print("Running the crawl task once. It isn't timed, and it waits as long as the tool's own delays.")
        result["crawl"], crawl_difference = run_crawl(tool, environment, page, reference, format_python)
        if crawl_difference is not None:
            differences.append(f"crawl task: {crawl_difference}")
    return result, differences


def build_reference() -> int:
    """Download the page afresh, pin it, and rebuild the reference records with the built-in Extractor."""
    find_program("uv", UV_HINT)
    page = refresh_page()
    print("Page copy: downloaded and pinned.")
    environment, _ = install_tool(load_tool(TOOLS_DIRECTORY / REFERENCE_TOOL))
    work = fresh_directory(CACHE_DIRECTORY / "work" / "reference")
    site2md = str(venv_program(environment.venv, "site2md"))
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
