"""Installed-command tests that build prints the text it was given as it is, brackets and all."""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

from tests.cli_test_support import (
    SKIP_PACING_HOOK,
    InstalledCliTestCase,
    RecordingServer,
    Route,
)

HTML = {"Content-Type": "text/html"}
PAGE = "<html><body><main><p>Hello</p></main></body></html>"
PROGRESS_BARS = ("Converting HTML to Markdown...", "Building remote page...")
# Rich wraps a message at 80 columns unless told otherwise, and these messages name long paths.
WIDE = {"COLUMNS": "500"}
ANSI_STYLE = re.compile(r"\x1b\[[0-9;]*m")


class BuildMessageTests(InstalledCliTestCase):
    """Check that a bracket, a backslash or an emoji code in a name or a URL comes out unchanged."""

    def build_lines(
        self,
        *arguments: object,
        returncode: int = 0,
        extra_environment: dict[str, str] | None = None,
    ) -> list[str]:
        """Build with and without the progress bar, and return the lines that both runs print."""
        environment = {**WIDE, **(extra_environment or {})}
        with_bar = self.run_site2md("build", *arguments, extra_environment=environment)
        without_bar = self.run_site2md(
            "build", *arguments, "--no-progress", extra_environment=environment
        )

        for result in (with_bar, without_bar):
            self.assertEqual(result.returncode, returncode, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        lines = [
            line
            for line in with_bar.stdout.splitlines()
            if not any(bar in line for bar in PROGRESS_BARS)
        ]
        self.assertEqual(without_bar.stdout.splitlines(), lines)
        return lines

    @staticmethod
    def write_page(folder: Path) -> Path:
        """Create the folder with one page in it, and return the folder."""
        folder.mkdir()
        (folder / "index.html").write_text(PAGE, encoding="utf-8")
        return folder

    @staticmethod
    def local_lines(pages: Path, output: Path) -> list[str]:
        """Return the lines of a local build of one page, as the issue words them."""
        return [
            f"Scanning {pages} for HTML files...",
            "Found 1 HTML files.",
            f"Merging 1 files into {output}...",
            f"Success! Markdown created at {output}",
        ]

    def test_local_build_names_a_folder_and_an_output_that_hold_a_bracketed_word(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = self.write_page(root / "pages[draft]")
            output = root / "notes[final].md"

            lines = self.build_lines(pages, "--output", output)

            self.assertEqual(lines, self.local_lines(pages, output))
            self.assertIn("Hello", output.read_text(encoding="utf-8"))

    def test_local_build_keeps_the_separator_before_a_folder_that_starts_with_a_bracket(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = self.write_page(root / "[x]")
            output = root / "b.md"

            lines = self.build_lines(pages, "--output", output)

            self.assertEqual(lines, self.local_lines(pages, output))

    def test_a_missing_input_is_named_as_it_was_given(self) -> None:
        # The names that Rich reads as a style, as the escape of a bracket, and as an emoji.
        for name in ("no[draft]dir", r"no\[draft]dir", "no:rocket:dir"):
            with self.subTest(name=name):
                lines = self.build_lines(name, returncode=1)

                self.assertEqual(lines, [f"Error: Input '{name}' does not exist."])

    def test_site_build_with_a_failing_link_that_closes_a_tag_prints_its_warning_and_exits_0(self) -> None:
        entry = b'<html><body><main><p>Entry</p><a href="/item[/x]">one</a></main></body></html>'
        routes: dict[str, Route] = {
            "/entry": (200, HTML, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "e.md"

            lines = self.build_lines(
                f"{server.origin}/entry",
                "--mode",
                "site",
                "--output",
                output,
                extra_environment=self.startup_hook_environment(root, SKIP_PACING_HOOK),
            )

            self.assertEqual(
                lines,
                [
                    f"Warning: Could not fetch {server.origin}/item[/x]: Final response returned HTTP 404.",
                    "Fetched 1; skipped 0; failed 1.",
                    f"Success! Markdown created at {output}",
                ],
            )
            self.assertIn("/item[/x]", server.requests)

    def test_an_output_error_from_the_operating_system_names_the_output_as_it_is(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = self.write_page(root / "pages")
            # A folder where the file should go makes the write fail, on every platform.
            output = root / "out[draft]"
            output.mkdir()

            lines = self.build_lines(pages, "--output", output, returncode=1)

            self.assertTrue(lines[-1].startswith("Error writing output:"), lines)
            self.assertIn("out[draft]", lines[-1])

    @unittest.skipIf(sys.platform == "win32", "A file name on Windows can't end with a backslash.")
    def test_a_backslash_at_the_end_of_a_name_is_not_doubled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = self.write_page(root / "pages")
            output = root / "notes\\"

            lines = self.build_lines(pages, "--output", output)

            self.assertEqual(lines, self.local_lines(pages, output))

    @unittest.skipIf(sys.platform == "win32", "Rich writes no ANSI codes to a pipe on Windows.")
    def test_styles_still_colour_the_messages_in_a_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = self.write_page(root / "pages[draft]")
            output = root / "notes[final].md"

            result = self.run_site2md(
                "build",
                pages,
                "--no-progress",
                "--output",
                output,
                extra_environment={**WIDE, "FORCE_COLOR": "1", "TERM": "xterm-256color"},
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("\x1b[1;32mScanning\x1b[0m", result.stdout)
            self.assertEqual(
                [ANSI_STYLE.sub("", line) for line in result.stdout.splitlines()],
                self.local_lines(pages, output),
            )
