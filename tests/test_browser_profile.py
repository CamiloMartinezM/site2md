"""Installed-command tests of build --browser --browser-profile, which reads a page with a profile that is kept."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from site2md.browser import find_browser
from tests.browser_test_support import (
    HTML,
    INTERRUPT_AT_NAVIGATION_HOOK,
    PLAIN_PAGE,
    SHORT_TIMEOUT_HOOK,
    BrowserTestCase,
)
from tests.cli_test_support import InstalledCliTestCase, RecordingServer, Route, respond

# What a person's session leaves in a profile folder, as far as these tests are concerned.
SESSION_FILE = "session.txt"
SESSION_TEXT = "a session that must stay"
COOKIE = "session=abc"


def remember(handler: BaseHTTPRequestHandler) -> None:
    """Answer with a page and a cookie that lasts an hour, as a site does after a sign-in."""
    headers = {**HTML, "Set-Cookie": f"{COOKIE}; Max-Age=3600; Path=/"}
    respond(handler, (200, headers, b"<html><body><main><h1>Signed in</h1></main></body></html>"))


def members(handler: BaseHTTPRequestHandler) -> None:
    """Answer visitors with the cookie with a page, and send the others to the sign-in page."""
    if COOKIE in handler.headers.get("Cookie", ""):
        body = b"<html><body><main><h1>Members</h1><p>Only for signed-in visitors.</p></main></body></html>"
        respond(handler, (200, HTML, body))
    else:
        respond(handler, (302, {"Location": "/sign-in"}, b""))


def sign_in_routes() -> dict[str, Route]:
    """Return the routes of a site that keeps a page for the visitors who have signed in."""
    return {
        "/remember": remember,
        "/members": members,
        "/sign-in": (200, HTML, b"<html><body><main><h1>Sign in</h1></main></body></html>"),
    }


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
            # A typo must not start a new profile, and a name with brackets must reach the line as it is.
            for profile in (root / "no-such-folder", a_file, root / "no[x]-such-folder"):
                # build binds a plain command line itself, and leaves --name=value to cyclopts.
                for option in (["--browser-profile", str(profile)], [f"--browser-profile={profile}"]):
                    with self.subTest(profile=profile.name, option=option[0]):
                        result = self.run_site2md(
                            "build", f"{server.origin}/page", "--browser", *option, "--output", output, "--no-progress"
                        )

                        self.assertEqual(result.returncode, 1)
                        self.assertEqual(
                            result.stdout.strip(),
                            f"Error: Browser profile folder '{profile}' does not exist or is not a folder.",
                        )
                        self.assertEqual(output.read_text(encoding="utf-8"), "previous")
            self.assertEqual(server.requests, [])
            self.assertFalse((root / "no-such-folder").exists())

    def test_the_help_describes_the_option(self) -> None:
        result = self.run_site2md("build", "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        text = " ".join(result.stdout.split())
        self.assertIn("--browser-profile", text)
        self.assertIn("--browser-profile needs --browser", text)
        # The person signs in with their own browser, in a folder that isn't their everyday one, and the table wraps cells.
        self.assertIn("--user-data-dir", text)
        self.assertIn("everyday", text)


class BrowserProfileTests(BrowserTestCase):
    """Build pages with --browser --browser-profile against the local server, and a folder that holds a session."""

    def new_root(self) -> Path:
        """Return a new folder with a profile folder that holds a session, and a folder for temporary files."""
        root = self.new_test_root()
        (root / "profile").mkdir()
        (root / "profile" / SESSION_FILE).write_text(SESSION_TEXT, encoding="utf-8")
        (root / "out.md").write_text("previous", encoding="utf-8")
        return root

    def build(self, url: str, root: Path, *options: object, hook: str | None = None) -> subprocess.CompletedProcess[str]:
        """Run build --browser --browser-profile with the profile folder of a root, and its own temporary folder."""
        environment = self.temp_environment(root)
        if hook is not None:
            environment.update(self.startup_hook_environment(root, hook))
        return self.run_site2md(
            "build", url, "--browser", "--browser-profile", root / "profile", "--output", root / "out.md",
            "--no-progress", *options,
            timeout=90,
            extra_environment=environment,
        )

    def assert_session_kept_and_browser_gone(self, root: Path, *, kept: Sequence[str] = ()) -> None:
        """Assert that the browser used the profile folder, that the session in it is whole, and that no browser is left."""
        profile = root / "profile"
        # A browser keeps its settings in its profile, so this file shows that it used this folder.
        self.assertTrue((profile / "Local State").is_file())
        self.assertEqual((profile / SESSION_FILE).read_text(encoding="utf-8"), SESSION_TEXT)
        self.assert_no_browser_left(root, kept=kept)

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
        # A request that never ends keeps the browser busy until the deadline, and then it is ended.
        with RecordingServer({"/slow": self.never_answers()}) as server:
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

    def test_keep_temp_keeps_nothing_from_the_folder(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server:
            root = self.new_root()

            result = self.build(f"{server.origin}/page", root, "--keep-temp")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            workspace = self.retained_workspace(result.stdout)
            # The workspace holds the page, its Markdown, the document and the index, and nothing from the folder.
            self.assertEqual(sorted(path.name for path in workspace.rglob("*")), ["converted.md", "document.md", "index.json", "page.html"])
            for path in workspace.iterdir():
                content = path.read_bytes()
                self.assertNotIn(SESSION_TEXT.encode(), content, path.name)
                self.assertNotIn(str(root / "profile").encode(), content, path.name)
            # The browser's own temporary files are gone, and only the workspace is left.
            self.assert_session_kept_and_browser_gone(root, kept=[workspace.name])

    def test_a_later_build_has_the_session_that_an_earlier_one_left(self) -> None:
        routes = sign_in_routes()
        with RecordingServer(routes) as server:
            root = self.new_root()
            output = root / "out.md"

            # Without the cookie, the members' page sends the browser to the sign-in page.
            first = self.build(f"{server.origin}/members", root)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertIn("# Sign in", output.read_text(encoding="utf-8"))
            self.assertIn(f"<!-- Source: {server.origin}/sign-in -->", output.read_text(encoding="utf-8"))

            visit = self.build(f"{server.origin}/remember", root)
            self.assertEqual(visit.returncode, 0, visit.stdout + visit.stderr)

            # A new browser on the same folder has the cookie that the earlier one kept.
            later = self.build(f"{server.origin}/members", root)
            self.assertEqual(later.returncode, 0, later.stdout + later.stderr)
            markdown = output.read_text(encoding="utf-8")
            self.assertIn("Only for signed-in visitors.", markdown)
            self.assertIn(f"<!-- Source: {server.origin}/members -->", markdown)
            self.assert_session_kept_and_browser_gone(root)

    def test_a_session_that_a_browser_left_after_a_visit_by_hand_is_used(self) -> None:
        routes = sign_in_routes()
        with RecordingServer(routes) as server:
            root = self.new_root()
            # The person starts the same browser with the folder, visits the site and closes the browser.
            subprocess.run(
                [
                    find_browser(), "--headless", "--no-first-run", "--no-default-browser-check",
                    "--edge-skip-compat-layer-relaunch", f"--user-data-dir={root / 'profile'}",
                    "--dump-dom", f"{server.origin}/remember",
                ],
                check=True,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=60,
            )

            result = self.build(f"{server.origin}/members", root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Only for signed-in visitors.", (root / "out.md").read_text(encoding="utf-8"))
            self.assert_session_kept_and_browser_gone(root)

    def hold_folder(self, profile: Path) -> subprocess.Popen[bytes]:
        """Start another browser on the profile folder, and return it once it has the folder open."""
        holder = subprocess.Popen(
            [
                find_browser(), "--headless", "--no-first-run", "--no-default-browser-check",
                "--edge-skip-compat-layer-relaunch", f"--user-data-dir={profile}",
                # The browser writes this file into its profile when it is up, which is after it took the folder.
                "--remote-debugging-port=0", "about:blank",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        deadline = time.monotonic() + 30
        while not (profile / "DevToolsActivePort").exists():
            self.assertLess(time.monotonic(), deadline, "the other browser did not start")
            self.assertIsNone(holder.poll(), "the other browser stopped")
            time.sleep(0.1)
        return holder

    def test_a_folder_that_another_browser_has_open_fails_with_one_line(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server:
            root = self.new_root()
            profile = root / "profile"
            holder = self.hold_folder(profile)

            result = self.build(f"{server.origin}/page", root)

            holder.kill()
            holder.wait()
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(result.stdout.strip().splitlines()), 1, result.stdout)
            self.assertTrue(
                result.stdout.startswith("Error fetching remote page: The browser stopped before the page was read"),
                result.stdout,
            )
            self.assertIn(f"Another browser may have the folder '{profile}' open.", result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual((root / "out.md").read_text(encoding="utf-8"), "previous")
            self.assertEqual(server.requests, [])
            self.assert_session_kept_and_browser_gone(root)

    def test_a_browser_that_stops_at_once_says_nothing_of_a_folder_without_the_option(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            # Python stops at once on the browser's first option, and says that it doesn't know it.
            result = self.run_site2md(
                "build", f"{server.origin}/page", "--browser", "--output", output, "--no-progress",
                timeout=90,
                extra_environment={"SITE2MD_BROWSER": sys.executable},
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("The browser stopped before the page was read: ", result.stdout)
            self.assertNotIn("Another browser", result.stdout)

    def test_the_session_is_kept_when_the_page_is_read_with_wait_for(self) -> None:
        routes = sign_in_routes()
        with RecordingServer(routes) as server:
            root = self.new_root()
            self.assertEqual(self.build(f"{server.origin}/remember", root).returncode, 0)

            result = self.build(f"{server.origin}/members", root, "--wait-for", "main h1")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Only for signed-in visitors.", (root / "out.md").read_text(encoding="utf-8"))
            self.assert_session_kept_and_browser_gone(root)
