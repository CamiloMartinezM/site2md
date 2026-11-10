"""Installed-command tests of build --browser --browser-profile, which reads a page with a profile that is kept."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tests.cli_test_support import InstalledCliTestCase, RecordingServer
from tests.test_browser_build import HTML, PLAIN_PAGE


class BrowserProfileOptionRulesTests(InstalledCliTestCase):
    """The folders and combinations that --browser-profile doesn't allow fail before any request, and need no browser."""

    def test_browser_profile_is_rejected_without_browser(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile = root / "profile"
            profile.mkdir()
            output = root / "out.md"
            output.write_text("previous", encoding="utf-8")

            result = self.run_site2md(
                "build", f"{server.origin}/page", "--browser-profile", profile, "--output", output, "--no-progress"
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout.strip(), "Error: --browser-profile can only be used with --browser.")
            self.assertEqual(output.read_text(encoding="utf-8"), "previous")
            self.assertEqual(server.requests, [])

    def test_browser_profile_is_rejected_for_local_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = root / "pages"
            pages.mkdir()
            (pages / "index.html").write_text(PLAIN_PAGE.decode(), encoding="utf-8")
            profile = root / "profile"
            profile.mkdir()
            output = root / "out.md"

            result = self.run_site2md("build", pages, "--browser-profile", profile, "--output", output)

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout.strip(), "Error: Remote build options require an HTTP(S) URL.")
            self.assertFalse(output.exists())

    def test_a_folder_that_is_missing_or_is_a_file_fails_before_any_request(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            a_file = root / "profile.txt"
            a_file.write_text("not a folder", encoding="utf-8")
            output = root / "out.md"
            output.write_text("previous", encoding="utf-8")
            # A typo must not start a new profile, which would read the page as a stranger.
            for profile in (root / "no-such-folder", a_file):
                with self.subTest(profile=profile.name):
                    result = self.run_site2md(
                        "build", f"{server.origin}/page", "--browser", "--browser-profile", profile,
                        "--output", output, "--no-progress",
                    )

                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(
                        result.stdout.strip(),
                        f"Error: Browser profile folder '{profile}' does not exist or is not a folder.",
                    )
                    self.assertEqual(output.read_text(encoding="utf-8"), "previous")
            self.assertEqual(server.requests, [])
            self.assertFalse((root / "no-such-folder").exists())
