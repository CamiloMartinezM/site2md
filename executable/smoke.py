"""Smoke-test the standalone executable against the installed package on a synthetic fixture."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from site2md.browser import find_browser
from site2md.downloader import RemoteFetchError

FIXTURES = Path(__file__).resolve().parent / "smoke_fixtures"
SITE = FIXTURES / "site"
PROVIDER = FIXTURES / "provider"
BROWSER_PAGE = FIXTURES / "browser_page.html"
BROWSER_PAGE_TEXT = b"Built by the script"
BUILT_IN_ID = "site2md.scrapethissite.countries"
PROVIDER_ID = "smoke.headings"
TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class _Run:
    """The observable result of one command: its exit status, standard error and output."""

    returncode: int
    stderr: bytes
    output: bytes


@contextmanager
def _serve(page: bytes) -> Iterator[str]:
    """Serve a page on a free local port, and yield the address of the page."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            found = self.path == "/page"
            self.send_response(200 if found else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page) if found else 0))
            self.end_headers()
            if found:
                self.wfile.write(page)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/page"
    finally:
        server.shutdown()
        server.server_close()


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


def _browser_problems(package: Sequence[str], executable: Sequence[str], *, work: Path) -> list[str]:
    """Build a page with --browser with both commands, which is the step that shows a module missing from the bundle."""
    try:
        find_browser()
    except RemoteFetchError as error:
        if os.environ.get("CI") == "true":
            # A runner without a browser must fail, or the step would be skipped for good.
            return [f"build with --browser: {error}"]
        print(f"SKIP build with --browser: {error}")
        return []
    package_markdown = work / "browser-package.md"
    executable_markdown = work / "browser-executable.md"
    with _serve(BROWSER_PAGE.read_bytes()) as url:
        arguments = ("build", url, "--browser", "--no-progress", "--output")
        package_run = _run(package, *arguments, package_markdown, output_file=package_markdown)
        executable_run = _run(executable, *arguments, executable_markdown, output_file=executable_markdown)
    problems = _compare("build with --browser", package_run, executable_run)
    # Both would be equal if neither ran the page's script.
    if not problems and BROWSER_PAGE_TEXT not in package_run.output:
        problems = ["build with --browser: the page's script did not run"]
    return problems


def run_smoke(
    package: Sequence[str],
    executable: Sequence[str],
    *,
    providers: Path,
    work: Path,
    with_browser: bool = False,
) -> list[str]:
    """Run the smoke steps with both commands and return the problems found, none on success.

    With a browser, one more step builds a page that a script fills in, and a machine without a browser skips it.
    """
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
    if with_browser:
        problems += _browser_problems(package, executable, work=work)
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
            [sys.executable, "-m", "site2md.main"],
            [str(executable)],
            providers=providers,
            work=work,
            with_browser=True,
        )

    for problem in problems:
        print(f"FAIL {problem}")
    if not problems:
        print(f"Smoke test passed: {executable} matches the package.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
