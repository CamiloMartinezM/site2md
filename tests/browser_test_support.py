"""Shared support for the tests that read pages with --browser."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from site2md.browser import find_browser
from site2md.downloader import RemoteFetchError
from tests.cli_test_support import InstalledCliTestCase, Route

# The folder of a test root that holds all the temporary files of the run under test.
TEMP_FOLDER = "tmp"
HTML = {"Content-Type": "text/html; charset=utf-8"}
PLAIN_PAGE = b"<html><body><main><h1>Plain</h1><p>No script here.</p></main></body></html>"
# Raises the interruption at the moment the build asks the browser to load the page.
INTERRUPT_AT_NAVIGATION_HOOK = """import json

dumps = json.dumps


def interrupted_dumps(value, *arguments, **options):
    if isinstance(value, dict) and value.get("method") == "Page.navigate":
        raise KeyboardInterrupt
    return dumps(value, *arguments, **options)


json.dumps = interrupted_dumps
"""
SHORT_TIMEOUT_HOOK = """from site2md import downloader

downloader.REQUEST_TIMEOUT_SECONDS = 3
"""
# Reads the command line of every process, so that a test can tell whether a browser is left.
_WINDOWS_PROCESS_QUERY = (
    "Get-CimInstance Win32_Process | Where-Object "
    "{ $_.CommandLine -and $_.CommandLine.Contains($env:SITE2MD_PROCESS_FOLDER) } "
    "| ForEach-Object { $_.ProcessId }"
)


def _processes_naming(folder: Path) -> list[str]:
    """Return the ids of the processes whose command line names the folder."""
    if sys.platform == "win32":
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_PROCESS_QUERY],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "SITE2MD_PROCESS_FOLDER": str(folder)},
        )
        return result.stdout.split()
    found = []
    for command_file in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            command_line = command_file.read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:  # the process ended while we looked
            continue
        if str(folder) in command_line and command_file.parent.name != str(os.getpid()):
            found.append(command_file.parent.name)
    return found


def _remove_test_root(root: Path) -> None:
    """Remove a folder that a test made, which is named site2md_test_ and a random string."""
    assert root.is_absolute()
    assert root.name.startswith("site2md_test_"), root
    shutil.rmtree(root, ignore_errors=True)


class BrowserTestCase(InstalledCliTestCase):
    """Run the installed command with --browser, or skip where no browser is installed."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        try:
            find_browser()
        except RemoteFetchError as error:
            if os.environ.get("CI") == "true":
                # A runner without a browser must fail, or the checks would pass without running.
                raise RuntimeError(f"CI has no browser: {error}") from error
            raise unittest.SkipTest(str(error)) from error

    def assert_failed_without_replacing_output(
        self, result: subprocess.CompletedProcess[str], output: Path
    ) -> None:
        """Assert a failed build left the previous destination as it was, and reported one line without a traceback."""
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_text(encoding="utf-8"), "previous")
        self.assertNotIn("Traceback", result.stderr)

    def new_test_root(self) -> Path:
        """Return a new folder for a test, with a folder for the temporary files of its runs, removed at the end."""
        root = Path(tempfile.mkdtemp(prefix="site2md_test_"))
        self.addCleanup(_remove_test_root, root)
        (root / TEMP_FOLDER).mkdir()
        return root

    def never_answers(self) -> Route:
        """Return a route that doesn't answer until the test ends."""
        release = threading.Event()
        self.addCleanup(release.set)

        def route(handler: BaseHTTPRequestHandler) -> None:
            release.wait(30)

        return route

    @staticmethod
    def temp_environment(root: Path) -> dict[str, str]:
        """Return the variables that point every temporary file of a run to the temporary folder of a test root."""
        folder = str(root / TEMP_FOLDER)
        return {"TMPDIR": folder, "TMP": folder, "TEMP": folder}

    def assert_no_browser_left(self, root: Path, *, kept: Sequence[str] = ()) -> None:
        """Assert that no browser runs from a folder under root, and that the run left only `kept` in its temp folder."""
        # The processes of a browser end a moment after it does.
        deadline = time.monotonic() + 10
        running = _processes_naming(root)
        while running and time.monotonic() < deadline:
            time.sleep(0.2)
            running = _processes_naming(root)
        self.assertEqual(running, [], "browser processes are left")
        # Everything counts, not only the run's own folders: a browser also leaves files of its own.
        left = sorted(path.name for path in (root / TEMP_FOLDER).iterdir())
        self.assertEqual(left, sorted(kept), "files of the run are left")
