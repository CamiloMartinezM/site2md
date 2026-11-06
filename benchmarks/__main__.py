"""Command line of the benchmark harness: run one tool, rebuild the reference, render the generated files."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from benchmarks.catalog import load_tool, tool_ids
from benchmarks.errors import HarnessError
from benchmarks.files import write_atomically
from benchmarks.paths import REFERENCE, REPOSITORY_ROOT, TOOLS_DIRECTORY
from benchmarks.render import render_files
from benchmarks.results import write_result
from benchmarks.runner import build_reference, run_tool


def _render() -> None:
    """Rebuild BENCHMARKS.md, the README's benchmark parts and the charts from the committed results."""
    updated = False
    for path, contents in render_files().items():
        if path.is_file() and path.read_text(encoding="utf-8") == contents:
            continue
        write_atomically(path, contents.encode("utf-8"))
        print(f"Updated {path.relative_to(REPOSITORY_ROOT)}.")
        updated = True
    if not updated:
        print("BENCHMARKS.md, the README and the charts are up to date.")


def _run(tool_id: str) -> None:
    """Measure one tool, write its results file, refresh the generated files and report the outcome."""
    if tool_id not in tool_ids():
        raise HarnessError(f"unknown tool '{tool_id}'; the tools are {', '.join(tool_ids())}")
    tool = load_tool(TOOLS_DIRECTORY / tool_id)
    result, difference = run_tool(tool)
    path = write_result(tool_id, result)
    page = result["page"]
    print(
        f"{tool.name} {result['version']}: {page['time']['mean'] * 1000:.0f} ms "
        f"+/- {page['time']['stddev'] * 1000:.0f} ms, {page['lines']['counted']} lines, "
        f"{result['install']['size_bytes'] / 1e6:.1f} MB in {len(result['install']['packages'])} packages."
    )
    print(f"Wrote {path.relative_to(REPOSITORY_ROOT)}.")
    _render()
    # The results are written first, so that the table can show "no" for a solution that fails the check.
    if difference is not None:
        raise HarnessError(f"the output does not match the reference: {difference}")
    print("The output matches the reference exactly.")


def _reference() -> None:
    """Rebuild the reference records from a freshly downloaded and pinned page copy."""
    count = build_reference()
    print(f"Wrote {count} records to {REFERENCE.relative_to(REPOSITORY_ROOT)}. Spot-check them before you commit.")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the harness command named in the arguments."""
    parser = argparse.ArgumentParser(prog="python -m benchmarks", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="measure one tool on the page task and write its results file")
    run.add_argument("tool", help="a folder name in benchmarks/tools")
    commands.add_parser("reference", help="download the page afresh, pin it and rebuild the reference records")
    commands.add_parser("render", help="rebuild BENCHMARKS.md, the README's benchmark parts and the charts from the results")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "run":
            _run(arguments.tool)
        elif arguments.command == "reference":
            _reference()
        else:
            _render()
    except HarnessError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
