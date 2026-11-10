"""Installed-command tests of build --browser --browser-profile, which reads a page with a profile that is kept."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from tests.browser_test_support import BrowserTestCase
from tests.cli_test_support import InstalledCliTestCase, RecordingServer
from tests.test_browser_build import HTML, INTERRUPT_AT_NAVIGATION_HOOK, PLAIN_PAGE, SHORT_TIMEOUT_HOOK

# What a person's session leaves in a profile folder, as far as these tests are concerned.
SESSION_FILE = "session.txt"
SESSION_TEXT = "a session that must stay"


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


class BrowserProfileTests(BrowserTestCase):
    """Build pages with --browser --browser-profile against the local server, and a folder that holds a session."""

    def new_root(self) -> Path:
        """Return a new folder with a profile folder that holds a session, and a folder for temporary files."""
        root = Path(tempfile.mkdtemp(prefix="site2md_test_"))
        self.addCleanup(self.remove_test_root, root)
        (root / "tmp").mkdir()
        (root / "profile").mkdir()
        (root / "profile" / SESSION_FILE).write_text(SESSION_TEXT, encoding="utf-8")
        (root / "out.md").write_text("previous", encoding="utf-8")
        return root

    @staticmethod
    def remove_test_root(root: Path) -> None:
        """Remove a folder that this test made, which is named site2md_test_ and a random string."""
        assert root.is_absolute()
        assert root.name.startswith("site2md_test_"), root
        shutil.rmtree(root, ignore_errors=True)

    def build(self, url: str, root: Path, *options: object, hook: str | None = None) -> subprocess.CompletedProcess[str]:
        """Run build --browser --browser-profile with the profile folder of a root, and its own temporary folder."""
        environment = {"TMPDIR": str(root / "tmp")}
        if hook is not None:
            environment.update(self.startup_hook_environment(root, hook))
        return self.run_site2md(
            "build", url, "--browser", "--browser-profile", root / "profile", "--output", root / "out.md",
            "--no-progress", *options,
            timeout=90,
            extra_environment=environment,
        )

    def assert_session_kept_and_browser_gone(self, root: Path) -> None:
        """Assert that the browser used the profile folder, that the session in it is whole, and that no browser is left."""
        profile = root / "profile"
        # A browser keeps its settings in its profile, so this file shows that it used this folder.
        self.assertTrue((profile / "Local State").is_file())
        self.assertEqual((profile / SESSION_FILE).read_text(encoding="utf-8"), SESSION_TEXT)
        self.assert_no_browser_left(root)

    def test_the_folder_is_the_browsers_profile_and_stays(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server:
            root = self.new_root()

            result = self.build(f"{server.origin}/page", root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("No script here.", (root / "out.md").read_text(encoding="utf-8"))
            self.assert_session_kept_and_browser_gone(root)

    def test_the_folder_stays_after_a_failed_build(self) -> None:
        with RecordingServer({"/page": (404, HTML, PLAIN_PAGE)}) as server:
            root = self.new_root()

            result = self.build(f"{server.origin}/page", root)

            self.assertEqual(result.stdout.strip(), "Error fetching remote page: Final response returned HTTP 404.")
            self.assertEqual((root / "out.md").read_text(encoding="utf-8"), "previous")
            self.assert_session_kept_and_browser_gone(root)

    def test_the_folder_stays_after_a_page_that_is_not_ready_in_time(self) -> None:
        release = threading.Event()
        self.addCleanup(release.set)

        def never_answers(handler: BaseHTTPRequestHandler) -> None:
            release.wait(30)

        # A request that never ends keeps the browser busy until the deadline, and then it is ended.
        with RecordingServer({"/slow": never_answers}) as server:
            root = self.new_root()

            result = self.build(f"{server.origin}/slow", root, hook=SHORT_TIMEOUT_HOOK)

            self.assertIn("timed out", result.stdout)
            self.assert_session_kept_and_browser_gone(root)

    def test_the_folder_stays_after_an_interruption(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server:
            root = self.new_root()

            result = self.build(f"{server.origin}/page", root, hook=INTERRUPT_AT_NAVIGATION_HOOK)

            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual((root / "out.md").read_text(encoding="utf-8"), "previous")
            self.assert_session_kept_and_browser_gone(root)
