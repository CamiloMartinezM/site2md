"""Installed-command tests of the build progress bar and its --no-progress option."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tests.cli_test_support import (
    SKIP_PACING_HOOK,
    InstalledCliTestCase,
    RecordingServer,
    Route,
)

LOCAL_BAR = "Converting HTML to Markdown..."
REMOTE_BAR = "Building remote page..."
HTML = {"Content-Type": "text/html"}


class BuildProgressTests(InstalledCliTestCase):
    """Check that --no-progress hides the progress bar and changes nothing else."""

    @staticmethod
    def written(output: Path) -> bytes | None:
        """Return the bytes of the output file, or None when the build left none."""
        return output.read_bytes() if output.is_file() else None

    def assert_option_only_hides_the_bar(
        self,
        bar: str,
        message: str,
        *arguments: object,
        output: Path,
        returncode: int = 0,
        extra_environment: dict[str, str] | None = None,
    ) -> None:
        """Build with and without --no-progress, then compare the two runs.

        `bar` is the progress bar's description, and `message` is a line that both runs print.
        """
        default = self.run_site2md(
            "build", *arguments, "--output", output, extra_environment=extra_environment
        )
        default_output = self.written(output)
        output.unlink(missing_ok=True)
        quiet = self.run_site2md(
            "build",
            *arguments,
            "--no-progress",
            "--output",
            output,
            extra_environment=extra_environment,
        )

        self.assertEqual(default.returncode, returncode, default.stdout + default.stderr)
        self.assertEqual(quiet.returncode, returncode, quiet.stdout + quiet.stderr)
        self.assertIn(bar, default.stdout)
        self.assertNotIn(bar, quiet.stdout)
        self.assertIn(message, quiet.stdout)
        self.assertEqual(
            quiet.stdout.splitlines(),
            [line for line in default.stdout.splitlines() if bar not in line],
        )
        self.assertEqual(quiet.stderr, default.stderr)
        self.assertEqual(self.written(output), default_output)

    def test_local_build_hides_only_the_progress_bar(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = root / "pages"
            pages.mkdir()
            (pages / "index.html").write_text(
                "<html><body><main><p>Hello</p></main></body></html>", encoding="utf-8"
            )

            self.assert_option_only_hides_the_bar(
                LOCAL_BAR, "Found 1 HTML files.", pages, output=root / "out.md"
            )
            self.assertIn("Hello", (root / "out.md").read_text(encoding="utf-8"))

    def test_page_mode_hides_only_the_progress_bar(self) -> None:
        routes: dict[str, Route] = {
            "/page": (200, HTML, b"<html><body><main><p>Hello</p></main></body></html>")
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            self.assert_option_only_hides_the_bar(
                REMOTE_BAR,
                "Fetched 1; skipped 0; failed 0.",
                f"{server.origin}/page",
                output=output,
            )
            self.assertIn("Hello", output.read_text(encoding="utf-8"))

    def test_follow_mode_hides_only_the_progress_bar(self) -> None:
        entry = b'<html><body><main><a class="detail" href="/child">Child</a></main></body></html>'
        routes: dict[str, Route] = {
            "/entry": (200, HTML, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/child": (200, HTML, b"<html><body><main><p>child text</p></main></body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "out.md"

            self.assert_option_only_hides_the_bar(
                REMOTE_BAR,
                "Fetched 2; skipped 0; failed 0.",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a.detail",
                output=output,
                extra_environment=self.startup_hook_environment(root, SKIP_PACING_HOOK),
            )
            self.assertIn("child text", output.read_text(encoding="utf-8"))

    def test_site_mode_hides_only_the_progress_bar(self) -> None:
        entry = b'<html><body><main><a href="/child">Child</a></main></body></html>'
        routes: dict[str, Route] = {
            "/entry": (200, HTML, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/child": (200, HTML, b"<html><body><main><p>child text</p></main></body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "out.md"

            self.assert_option_only_hides_the_bar(
                REMOTE_BAR,
                "Fetched 2; skipped 0; failed 0.",
                f"{server.origin}/entry",
                "--mode",
                "site",
                output=output,
                extra_environment=self.startup_hook_environment(root, SKIP_PACING_HOOK),
            )
            self.assertIn("child text", output.read_text(encoding="utf-8"))

    def test_failed_remote_build_reports_the_same_error_without_the_bar(self) -> None:
        with RecordingServer({}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            self.assert_option_only_hides_the_bar(
                REMOTE_BAR,
                "Error fetching remote page:",
                f"{server.origin}/missing",
                output=output,
                returncode=1,
            )
            self.assertFalse(output.exists())
