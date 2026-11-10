"""Shared support for the tests that read pages with --browser."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from site2md.browser import find_browser
from site2md.downloader import RemoteFetchError
from tests.cli_test_support import InstalledCliTestCase

# Starts the name of every folder that a --browser run makes for its browser.
BROWSER_FOLDER_PREFIX = "site2md_browser_"
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

    def assert_no_browser_left(self, temp_root: Path) -> None:
        """Assert that no browser runs from a folder under temp_root, and that no folder of a run is left."""
        # The processes of a browser end a moment after it does.
        deadline = time.monotonic() + 10
        running = _processes_naming(temp_root)
        while running and time.monotonic() < deadline:
            time.sleep(0.2)
            running = _processes_naming(temp_root)
        self.assertEqual(running, [], "browser processes are left")
        left = [path.name for path in temp_root.iterdir() if path.name.startswith("site2md_")]
        self.assertEqual(left, [], "folders of the run are left")
