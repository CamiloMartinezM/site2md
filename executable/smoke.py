"""Smoke-test the standalone executable against the installed package on a synthetic fixture."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "smoke_fixtures"
SITE = FIXTURES / "site"
PROVIDER = FIXTURES / "provider"
BUILT_IN_ID = "site2md.scrapethissite.countries"
PROVIDER_ID = "smoke.headings"
TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class _Run:
    """The observable result of one command: its exit status, standard error and output."""

    returncode: int
    stderr: bytes
    output: bytes


def _run(
    command: Sequence[str],
    *arguments: object,
    output_file: Path | None = None,
    environment: dict[str, str] | None = None,
) -> _Run:
    """Run a command and capture its output, which is the standard output unless it writes a file."""
    completed = subprocess.run(
        [*command, *map(str, arguments)],
        check=False,
        capture_output=True,
        env={**os.environ, **(environment or {})},
        timeout=TIMEOUT_SECONDS,
    )
    output = completed.stdout
    if output_file is not None and completed.returncode == 0:
        output = output_file.read_bytes()
    return _Run(completed.returncode, completed.stderr, output)


def _failed(step: str, name: str, run: _Run) -> list[str]:
    """Return a problem when a command exited with an error."""
    if run.returncode == 0:
        return []
    stderr = run.stderr.decode("ascii", errors="backslashreplace").strip()
    return [f"{step}: the {name} exited {run.returncode}: {stderr}"]


def _compare(step: str, package: _Run, executable: _Run) -> list[str]:
    """Return what is wrong with a step: a failed command, or output that differs from the package's."""
    problems = _failed(step, "package", package) or _failed(step, "executable", executable)
    if not problems and package.output != executable.output:
        problems = [f"{step}: the executable's output differs from the package's"]
    return problems


def _listing_problems(listing: _Run) -> list[str]:
    """Return what is wrong with the executable's Extractor listing, which must show both Extractors."""
    problems = _failed("extractors", "executable", listing)
    if problems:
        return problems
    shown = listing.output.decode("utf-8", errors="replace")
    return [
        f"extractors: the executable's listing lacks {extractor_id}"
        for extractor_id in (BUILT_IN_ID, PROVIDER_ID)
        if extractor_id not in shown
    ]


def run_smoke(
    package: Sequence[str], executable: Sequence[str], *, providers: Path, work: Path
) -> list[str]:
    """Run the smoke steps with both commands and return the problems found, none on success."""
    package_markdown = work / "package.md"
    executable_markdown = work / "executable.md"
    folder = str(providers)
    problems = _compare(
        "build",
        _run(package, "build", SITE, "--output", package_markdown, output_file=package_markdown),
        _run(executable, "build", SITE, "--output", executable_markdown, output_file=executable_markdown),
    )
    problems += _compare(
        "extract with the built-in Extractor",
        _run(package, "extract", BUILT_IN_ID, package_markdown),
        _run(executable, "extract", BUILT_IN_ID, package_markdown),
    )
    # A package finds the folder through PYTHONPATH. Only the executable reads SITE2MD_PROVIDER_PATH.
    problems += _compare(
        "extract with an Extractor provider",
        _run(package, "extract", PROVIDER_ID, package_markdown, environment={"PYTHONPATH": folder}),
        _run(
            executable,
            "extract",
            PROVIDER_ID,
            package_markdown,
            environment={"SITE2MD_PROVIDER_PATH": folder},
        ),
    )
    problems += _listing_problems(
        _run(executable, "extractors", environment={"SITE2MD_PROVIDER_PATH": folder})
    )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Install the smoke provider with pip, smoke-test the built executable and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="the folder that executable/build.py wrote, dist/site2md")
    folder = parser.parse_args(argv).folder
    executable = folder / ("site2md.exe" if sys.platform == "win32" else "site2md")
    if not executable.is_file():
        print(f"Error: Executable '{executable}' does not exist. Build it first.", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as temp_dir:
        providers = Path(temp_dir) / "providers"
        work = Path(temp_dir) / "work"
        work.mkdir()
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--target", str(providers), str(PROVIDER)],
            check=True,
        )
        problems = run_smoke(
            [sys.executable, "-m", "site2md.main"], [str(executable)], providers=providers, work=work
        )

    for problem in problems:
        print(f"FAIL {problem}")
    if not problems:
        print(f"Smoke test passed: {executable} matches the package.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
