"""Installed-command tests of build --browser, which reads a page from an installed Chromium-based browser."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from tests.browser_test_support import (
    HTML,
    INTERRUPT_AT_NAVIGATION_HOOK,
    PLAIN_PAGE,
    SHORT_TIMEOUT_HOOK,
    TEMP_FOLDER,
    BrowserTestCase,
)
from tests.cli_test_support import (
    RECORD_MODULES_HOOK,
    InstalledCliTestCase,
    RecordingServer,
    Route,
)

CERTIFICATE = Path(__file__).resolve().parent / "fixtures" / "tls" / "loopback.pem"
# A table that a script fills in from a data address, two seconds after the page has loaded.
FILMS_PAGE = b"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Films</title></head>
<body>
<main>
<h1>Films</h1>
<p><a href="/lessons/">Lessons</a></p>
<table>
<thead><tr><th>Title</th><th>Awards</th></tr></thead>
<tbody id="rows"></tbody>
</table>
</main>
<script>
setTimeout(function () {
  fetch("/films.json").then(function (response) { return response.json(); }).then(function (films) {
    document.getElementById("rows").innerHTML = films.map(function (film) {
      return "<tr><td>" + film.title + "</td><td>" + film.awards + "</td></tr>";
    }).join("");
  });
}, 2000);
</script>
</body>
</html>"""
FILMS_JSON = json.dumps(
    [{"title": f"Film {number:02d}", "awards": number % 3} for number in range(1, 17)]
).encode()
# The test's server has a self-signed certificate, which the browser has to accept to be asked.
ACCEPT_TEST_CERTIFICATE_HOOK = """from site2md import browser

browser.BROWSER_SWITCHES += ("--ignore-certificate-errors",)
"""
# Holds the browser open for a few seconds more, which is long enough for it to save a download if it may.
DELAY_CLOSE_HOOK = """import json
import time

dumps = json.dumps


def delayed_dumps(value, *arguments, **options):
    if isinstance(value, dict) and value.get("method") == "Browser.close":
        time.sleep(3)
    return dumps(value, *arguments, **options)


json.dumps = delayed_dumps
"""
# The browser's first answer comes four seconds late, as from a browser that starts slowly on a busy runner.
SLOW_START_HOOK = """import json
import time

dumps = json.dumps


def slow_dumps(value, *arguments, **options):
    if isinstance(value, dict) and value.get("method") == "Target.getTargets":
        time.sleep(4)
    return dumps(value, *arguments, **options)


json.dumps = slow_dumps
"""
# Room for a test's slow start on top of the browser's own, which takes seconds on a CI runner.
TWENTY_SECOND_TIMEOUT_HOOK = SHORT_TIMEOUT_HOOK.replace("= 3", "= 20")
# Makes the removal of the browser's folder fail, as it does where a process still holds a file in it.
KEEP_BROWSER_FOLDER_HOOK = """import shutil

rmtree = shutil.rmtree


def stuck_rmtree(path, *arguments, **options):
    if "site2md_browser_" in str(path):
        if options.get("ignore_errors"):
            return
        raise PermissionError(13, "Access is denied", str(path))
    return rmtree(path, *arguments, **options)


shutil.rmtree = stuck_rmtree
"""


def script_page(script: str) -> bytes:
    """Return a page whose body is empty until the script makes its content."""
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
        f'<body><main id="content"></main><script>{script}</script></body></html>'
    ).encode()


def unused_port() -> int:
    """Return a port that nothing listens on."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class BrowserBuildTests(BrowserTestCase):
    """Build pages with --browser against the local server, with pages whose scripts make the content."""

    def build(
        self, url: str, output: Path, *options: object, extra_environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run build --browser for a URL and return the result."""
        return self.run_site2md(
            "build", url, "--browser", "--output", output, "--no-progress", *options,
            timeout=90,
            extra_environment=extra_environment,
        )

    def test_converts_the_page_as_the_browser_shows_it(self) -> None:
        routes: dict[str, Route] = {
            "/films": (200, HTML, FILMS_PAGE),
            "/films.json": (200, {"Content-Type": "application/json"}, FILMS_JSON),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "films.md"

            result = self.build(f"{server.origin}/films", output)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            markdown = output.read_text(encoding="utf-8")
            self.assertIn(f"<!-- Source: {server.origin}/films -->", markdown)
            self.assertIn(f"[Lessons]({server.origin}/lessons/)", markdown)
            self.assertIn("| Film 01 | 1 |", markdown)
            self.assertIn("| Film 16 | 1 |", markdown)
            self.assertEqual(markdown.count("| Film "), 16)
            # The browser asks for the page, for what the page asks for and for its icon.
            self.assertEqual(sorted(set(server.requests)), ["/favicon.ico", "/films", "/films.json"])

    def test_both_command_line_paths_give_the_same_result(self) -> None:
        # build binds a plain command line itself, and leaves --name=value to cyclopts.
        routes: dict[str, Route] = {"/page": (200, HTML, script_page('document.body.append("Built");'))}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            separate = Path(temp_dir) / "separate.md"
            joined = Path(temp_dir) / "joined.md"

            plain = self.run_site2md("build", f"{server.origin}/page", "--browser", "--output", separate)
            through_cyclopts = self.run_site2md("build", f"{server.origin}/page", "--browser", f"--output={joined}")

            self.assertEqual(plain.returncode, 0, plain.stdout + plain.stderr)
            self.assertEqual(through_cyclopts.returncode, 0, through_cyclopts.stdout + through_cyclopts.stderr)
            self.assertEqual(separate.read_bytes(), joined.read_bytes())
            self.assertIn("Built", separate.read_text(encoding="utf-8"))
            self.assertEqual(plain.stdout.replace("separate.md", "joined.md"), through_cyclopts.stdout)

    def test_a_browser_build_loads_the_browser_module(self) -> None:
        # The counterpart of the start-up test that a build without --browser never loads it.
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log = root / "modules.json"
            environment = self.startup_hook_environment(root, RECORD_MODULES_HOOK)
            environment["SITE2MD_MODULE_LOG"] = str(log)

            result = self.build(f"{server.origin}/page", root / "out.md", extra_environment=environment)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("site2md.browser", json.loads(log.read_text(encoding="utf-8")))

    def test_a_build_without_browser_still_reads_the_page_as_the_server_sends_it(self) -> None:
        routes: dict[str, Route] = {
            "/films": (200, HTML, FILMS_PAGE),
            "/films.json": (200, {"Content-Type": "application/json"}, FILMS_JSON),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "films.md"

            result = self.run_site2md("build", f"{server.origin}/films", "--output", output, "--no-progress")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(server.requests, ["/films"])
            self.assertEqual(server.user_agents, ["site2md/0.6.0"])
            self.assertNotIn("| Film ", output.read_text(encoding="utf-8"))

    def test_the_user_agent_is_the_browsers_own_followed_by_the_site2md_version(self) -> None:
        routes: dict[str, Route] = {
            "/page": (200, HTML, script_page('fetch("/data");')),
            "/data": (200, {"Content-Type": "application/json"}, b"{}"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            result = self.build(f"{server.origin}/page", Path(temp_dir) / "out.md")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # The page and what the page asks for both say who asks.
            self.assertGreaterEqual(len(server.user_agents), 2)
            for user_agent in server.user_agents:
                assert user_agent is not None
                self.assertTrue(user_agent.startswith("Mozilla/5.0 ("), user_agent)
                self.assertIn("Chrome/", user_agent)
                self.assertTrue(user_agent.endswith(" site2md/0.6.0"), user_agent)

    def test_a_frame_of_another_site_asks_with_the_same_user_agent(self) -> None:
        routes: dict[str, Route] = {"/from-frame": (200, {"Content-Type": "text/plain"}, b"ok")}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            # localhost is another site than 127.0.0.1, so the browser runs the frame in a process of its own.
            other = server.origin.replace("127.0.0.1", "localhost")
            routes["/page"] = (
                200,
                HTML,
                (
                    f'<html><body><iframe src="{other}/frame"></iframe><script>'
                    'window.addEventListener("message", function () {'
                    ' document.body.insertAdjacentHTML("beforeend", "<p class=done>Done</p>"); });'
                    "</script></body></html>"
                ).encode(),
            )
            frame = b'<script>fetch("/from-frame").then(function () { parent.postMessage("done", "*"); });</script>'
            routes["/frame"] = (200, HTML, b"<html><body>" + frame + b"</body></html>")

            result = self.build(f"{server.origin}/page", Path(temp_dir) / "out.md", "--wait-for", "p.done")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("/from-frame", server.requests)
            for path, user_agent in zip(server.requests, server.user_agents):
                assert user_agent is not None
                self.assertTrue(user_agent.endswith(" site2md/0.6.0"), f"{path}: {user_agent}")

    def test_the_page_is_read_after_ten_seconds_of_the_pages_own_time(self) -> None:
        page = script_page(
            """
            function add(text) { document.getElementById("content").innerHTML += "<p>" + text + "</p>"; }
            setTimeout(function () { add("at nine seconds"); }, 9000);
            setTimeout(function () { add("at twelve seconds"); }, 12000);
            """
        )
        with RecordingServer({"/page": (200, HTML, page)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.build(f"{server.origin}/page", output)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            markdown = output.read_text(encoding="utf-8")
            self.assertIn("at nine seconds", markdown)
            self.assertNotIn("at twelve seconds", markdown)

    def test_wait_for_reads_a_page_that_keeps_a_request_open(self) -> None:
        # The page's own time stands still while the request is open, so only a selector can end the wait.
        page = script_page(
            """
            fetch("/hang");
            setTimeout(function () {
              document.getElementById("content").innerHTML = "<p class='film'>Spotlight</p>";
            }, 1500);
            """
        )
        routes: dict[str, Route] = {"/open": (200, HTML, page), "/hang": self.never_answers()}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.build(f"{server.origin}/open", output, "--wait-for", "p.film")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Spotlight", output.read_text(encoding="utf-8"))

    def test_wait_for_reads_the_page_as_soon_as_an_element_matches(self) -> None:
        page = script_page(
            """
            var content = document.getElementById("content");
            content.innerHTML = "<p class='ready'>Ready at once</p>";
            setTimeout(function () { content.innerHTML += "<p>Added at four seconds</p>"; }, 4000);
            """
        )
        with RecordingServer({"/page": (200, HTML, page)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.build(f"{server.origin}/page", output, "--wait-for", "p.ready")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            markdown = output.read_text(encoding="utf-8")
            self.assertIn("Ready at once", markdown)
            # The page runs in real time, so what it adds later isn't there yet.
            self.assertNotIn("Added at four seconds", markdown)

    def test_wait_for_reads_a_page_that_opens_a_dialog(self) -> None:
        page = script_page(
            """
            alert("hello");
            setTimeout(function () {
              document.getElementById("content").innerHTML = "<p class='film'>After the dialog</p>";
            }, 300);
            """
        )
        with RecordingServer({"/page": (200, HTML, page)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.build(f"{server.origin}/page", output, "--wait-for", "p.film")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("After the dialog", output.read_text(encoding="utf-8"))

    def test_wait_for_follows_a_redirect_that_the_pages_own_script_makes(self) -> None:
        moved = script_page('setTimeout(function () { location.replace("/final"); }, 300);')
        final = script_page(
            """
            setTimeout(function () {
              document.getElementById("content").innerHTML = "<p class='film'>Final text</p>";
            }, 500);
            """
        )
        routes: dict[str, Route] = {"/start": (200, HTML, moved), "/final": (200, HTML, final)}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.build(f"{server.origin}/start", output, "--wait-for", "p.film")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            markdown = output.read_text(encoding="utf-8")
            self.assertIn("Final text", markdown)
            self.assertIn(f"<!-- Source: {server.origin}/final -->", markdown)

    def test_a_page_that_moves_to_another_site_is_read_where_it_ends(self) -> None:
        routes: dict[str, Route] = {}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            # localhost is another site than 127.0.0.1, so the browser reads the new page in a new process.
            other = server.origin.replace("127.0.0.1", "localhost")
            routes["/script"] = (200, HTML, script_page(f'setTimeout(function () {{ location.replace("{other}/final"); }}, 300);'))
            routes["/refresh"] = (
                200,
                HTML,
                f'<html><head><meta http-equiv="refresh" content="0;url={other}/final"></head><body>x</body></html>'.encode(),
            )
            # The new page's own timers run fast as well.
            routes["/final"] = (
                200,
                HTML,
                script_page('setTimeout(function () { document.getElementById("content").innerHTML = "<p>Final text</p>"; }, 2000);'),
            )
            for path in ("/script", "/refresh"):
                with self.subTest(path=path):
                    output = Path(temp_dir) / f"{path.strip('/')}.md"

                    result = self.build(f"{server.origin}{path}", output)

                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    markdown = output.read_text(encoding="utf-8")
                    self.assertIn("Final text", markdown)
                    self.assertIn(f"<!-- Source: {other}/final -->", markdown)

    def test_wait_for_gives_the_same_result_whichever_way_the_command_line_is_read(self) -> None:
        # build binds a plain command line itself, and leaves --name=value to cyclopts.
        page = script_page(
            """setTimeout(function () { document.body.insertAdjacentHTML("beforeend", "<p class='built'>Built</p>"); }, 300);"""
        )
        with RecordingServer({"/page": (200, HTML, page)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            separate = Path(temp_dir) / "separate.md"
            joined = Path(temp_dir) / "joined.md"
            url = f"{server.origin}/page"

            plain = self.run_site2md("build", url, "--browser", "--wait-for", "p.built", "--output", separate, "--no-progress")
            through_cyclopts = self.run_site2md(
                "build", url, "--browser", "--wait-for=p.built", "--output", joined, "--no-progress"
            )

            self.assertEqual(plain.returncode, 0, plain.stdout + plain.stderr)
            self.assertEqual(through_cyclopts.returncode, 0, through_cyclopts.stdout + through_cyclopts.stderr)
            self.assertEqual(separate.read_bytes(), joined.read_bytes())
            self.assertIn("Built", separate.read_text(encoding="utf-8"))

    def test_the_address_that_the_browser_ends_on_is_the_source(self) -> None:
        page = b'<html><body><main><a href="child.html">Child</a></main></body></html>'
        routes: dict[str, Route] = {
            "/start": (302, {"Location": "/final/page.html"}, b""),
            "/final/page.html": (200, HTML, page),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.build(f"{server.origin}/start", output)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            markdown = output.read_text(encoding="utf-8")
            self.assertIn(f"<!-- Source: {server.origin}/final/page.html -->", markdown)
            self.assertIn(f"[Child]({server.origin}/final/child.html)", markdown)

    def test_a_fragment_stays_in_the_source(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.build(f"{server.origin}/page#2015", output)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(f"<!-- Source: {server.origin}/page#2015 -->", output.read_text(encoding="utf-8"))

    def test_a_page_in_another_encoding_comes_out_with_the_right_characters(self) -> None:
        pages: dict[str, Route] = {
            # The header names the encoding.
            "/header": (
                200,
                {"Content-Type": "text/html; charset=iso-8859-1"},
                b"<html><body><main><p>caf\xe9</p></main></body></html>",
            ),
            # Only the markup names it. The browser reads the euro sign of windows-1252 as well.
            "/meta": (
                200,
                {"Content-Type": "text/html"},
                b'<html><head><meta charset="windows-1252"></head><body><main><p>caf\xe9 \x80</p></main></body></html>',
            ),
            # The header and the markup disagree, and the header wins.
            "/disagree": (
                200,
                {"Content-Type": "text/html; charset=utf-8"},
                '<html><head><meta charset="windows-1252"></head><body><main><p>café €</p></main></body></html>'.encode(),
            ),
        }
        expected = {"/header": "café", "/meta": "café €", "/disagree": "café €"}
        with RecordingServer(pages) as server, tempfile.TemporaryDirectory() as temp_dir:
            for path, text in expected.items():
                with self.subTest(path=path):
                    output = Path(temp_dir) / f"{path.strip('/')}.md"

                    result = self.build(f"{server.origin}{path}", output)

                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(f"\n{text}\n", output.read_text(encoding="utf-8"))

    def test_a_page_that_opens_a_dialog_is_still_read(self) -> None:
        page = script_page(
            """
            alert("hello");
            document.getElementById("content").innerHTML = "<p>after the dialog</p>";
            """
        )
        with RecordingServer({"/page": (200, HTML, page)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.build(f"{server.origin}/page", output)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("after the dialog", output.read_text(encoding="utf-8"))

    def test_the_browser_asks_for_what_the_page_needs_and_nothing_is_blocked(self) -> None:
        page = script_page(
            """
            var image = new Image();
            image.src = "/picture.png";
            document.getElementById("content").appendChild(image);
            var script = document.createElement("script");
            script.src = "/more.js";
            document.body.appendChild(script);
            """
        )
        routes: dict[str, Route] = {
            "/page": (200, HTML, page),
            "/picture.png": (200, {"Content-Type": "image/png"}, b"not really a picture"),
            "/more.js": (
                200,
                {"Content-Type": "text/javascript"},
                b'document.getElementById("content").insertAdjacentHTML("beforeend", "<p>from another script</p>");',
            ),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.build(f"{server.origin}/page", output)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("from another script", output.read_text(encoding="utf-8"))
            self.assertLessEqual({"/page", "/picture.png", "/more.js"}, set(server.requests))

    def test_keep_temp_keeps_the_page_as_the_browser_showed_it_and_never_the_profile(self) -> None:
        page = script_page('document.getElementById("content").innerHTML = "<p>Kept text</p>";')
        with RecordingServer({"/page": (200, HTML, page)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            (temp_root / TEMP_FOLDER).mkdir()

            result = self.build(
                f"{server.origin}/page",
                temp_root / "out.md",
                "--keep-temp",
                extra_environment=self.temp_environment(temp_root),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            workspace = self.retained_workspace(result.stdout)
            kept = (workspace / "page.html").read_text(encoding="utf-8")
            self.assertIn("<p>Kept text</p>", kept)
            self.assertTrue(kept.startswith("<!DOCTYPE html>"))
            self.assert_no_browser_left(temp_root, kept=[workspace.name])


class BrowserOptionRulesTests(InstalledCliTestCase):
    """The combinations that --browser doesn't allow fail before any request, and need no browser."""

    def test_browser_is_rejected_in_follow_and_site_mode(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"
            output.write_text("previous", encoding="utf-8")
            for mode in ("follow", "site"):
                with self.subTest(mode=mode):
                    result = self.run_site2md(
                        "build", f"{server.origin}/page", "--browser", "--mode", mode, "--output", output, "--no-progress"
                    )

                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout.strip(), "Error: --browser can only be used with --mode page.")
                    self.assertEqual(output.read_text(encoding="utf-8"), "previous")
            self.assertEqual(server.requests, [])

    def test_browser_is_rejected_for_local_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pages = Path(temp_dir) / "pages"
            pages.mkdir()
            (pages / "index.html").write_text(PLAIN_PAGE.decode(), encoding="utf-8")
            output = Path(temp_dir) / "out.md"

            result = self.run_site2md("build", pages, "--browser", "--output", output)

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout.strip(), "Error: Remote build options require an HTTP(S) URL.")
            self.assertFalse(output.exists())

    def test_wait_for_is_rejected_without_browser(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"
            output.write_text("previous", encoding="utf-8")
            for mode in ("page", "follow", "site"):
                with self.subTest(mode=mode):
                    result = self.run_site2md(
                        "build", f"{server.origin}/page", "--wait-for", "main", "--mode", mode, "--output", output,
                        "--no-progress",
                    )

                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout.strip(), "Error: --wait-for can only be used with --browser.")
                    self.assertEqual(output.read_text(encoding="utf-8"), "previous")
            self.assertEqual(server.requests, [])

    def test_wait_for_is_rejected_for_local_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pages = Path(temp_dir) / "pages"
            pages.mkdir()
            (pages / "index.html").write_text(PLAIN_PAGE.decode(), encoding="utf-8")
            output = Path(temp_dir) / "out.md"

            result = self.run_site2md("build", pages, "--wait-for", "main", "--output", output)

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout.strip(), "Error: Remote build options require an HTTP(S) URL.")
            self.assertFalse(output.exists())

    def test_the_help_describes_the_option(self) -> None:
        result = self.run_site2md("build", "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        # The table wraps each cell, so the borders are dropped to read a phrase across the lines.
        text = " ".join(word for word in result.stdout.split() if word not in {"|", "│"})
        self.assertIn("--browser", text)
        self.assertIn("SITE2MD_BROWSER", text)
        # What the browser loads, what stays as in a plain fetch, and what it doesn't do.
        self.assertIn("loads everything the page asks for, from other hosts too", text)
        self.assertIn("nothing is blocked or checked against robots.txt", text)
        self.assertIn("As in a plain fetch, only a 2xx HTML page is converted", text)
        self.assertIn("It doesn't hide the automation", text)

    def test_the_help_describes_wait_for_and_the_rule_that_it_needs_the_browser(self) -> None:
        result = self.run_site2md("build", "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        text = " ".join(result.stdout.split())
        self.assertIn("--wait-for", text)
        # Only its description says how long the wait lasts.
        self.assertIn("seconds", text)
        self.assertIn("--wait-for needs --browser", text)


class BrowserBuildFailureTests(BrowserTestCase):
    """Each failure that a plain fetch reports is reported the same way, and leaves the output as it was."""

    def build_failing(
        self, url: str, temp_root: Path, *options: object, extra_environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run build --browser over an existing output file and assert that it failed and left the file alone."""
        output = temp_root / "out.md"
        output.write_text("previous", encoding="utf-8")
        result = self.run_site2md(
            "build", url, "--browser", "--output", output, "--no-progress", *options,
            timeout=90,
            extra_environment=extra_environment,
        )
        self.assert_failed_without_replacing_output(result, output)
        return result

    def test_a_response_that_a_plain_fetch_rejects_fails_with_the_same_line(self) -> None:
        routes: dict[str, Route] = {
            "/missing": (404, HTML, PLAIN_PAGE),
            "/broken": (500, HTML, PLAIN_PAGE),
            "/data": (200, {"Content-Type": "application/json"}, b'{"films": 2}'),
            "/untyped": (200, {}, PLAIN_PAGE),
            "/empty": (200, HTML, b""),
        }
        expected = {
            "/missing": "Final response returned HTTP 404.",
            "/broken": "Final response returned HTTP 500.",
            "/data": "Final response must be text/html or application/xhtml+xml (got application/json).",
            "/untyped": "Final response must be text/html or application/xhtml+xml (got text/plain).",
            "/empty": "Final HTML response body is empty.",
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            for path, message in expected.items():
                with self.subTest(path=path):
                    result = self.build_failing(f"{server.origin}{path}", Path(temp_dir))

                    self.assertEqual(result.stdout.strip(), f"Error fetching remote page: {message}")

    def test_an_empty_page_is_reported_as_empty_and_not_waited_for_when_a_selector_is_given(self) -> None:
        with RecordingServer({"/empty": (200, HTML, b"")}) as server, tempfile.TemporaryDirectory() as temp_dir:
            # With the old behaviour the build waits the 30 seconds for an element that can't be there.
            started = time.monotonic()

            result = self.build_failing(f"{server.origin}/empty", Path(temp_dir), "--wait-for", "main")

            self.assertEqual(result.stdout.strip(), "Error fetching remote page: Final HTML response body is empty.")
            self.assertLess(time.monotonic() - started, 20)

    def test_a_content_length_that_is_not_a_number_fails_as_it_does_under_a_plain_fetch(self) -> None:
        def malformed(handler: BaseHTTPRequestHandler) -> None:
            # The browser and the plain fetch both read on until the server closes the connection.
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.send_header("Content-Length", "abc")
            handler.end_headers()
            handler.wfile.write(PLAIN_PAGE)
            handler.close_connection = True

        with RecordingServer({"/page": malformed}) as server, tempfile.TemporaryDirectory() as temp_dir:
            expected = "Error fetching remote page: Response Content-Length is malformed."
            output = Path(temp_dir) / "plain.md"
            output.write_text("previous", encoding="utf-8")
            # The control: a build without the browser fails with this line.
            plain = self.run_site2md("build", f"{server.origin}/page", "--output", output, "--no-progress")
            self.assertEqual(plain.stdout.strip(), expected)

            result = self.build_failing(f"{server.origin}/page", Path(temp_dir))

            self.assertEqual(result.stdout.strip(), expected)

    def test_a_page_that_the_server_does_not_answer_fails_with_the_browsers_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.build_failing(f"http://127.0.0.1:{unused_port()}/page", Path(temp_dir))

            self.assertEqual(
                result.stdout.strip(),
                "Error fetching remote page: Malformed or unavailable response: net::ERR_CONNECTION_REFUSED",
            )

    def test_a_navigation_that_the_pages_script_starts_and_that_fails_fails_the_build(self) -> None:
        page = script_page(
            f'setTimeout(function () {{ location.replace("http://127.0.0.1:{unused_port()}/gone"); }}, 300);'
        )
        with RecordingServer({"/start": (200, HTML, page)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            # With a selector, the build must not wait for it on the browser's error page.
            for options in ((), ("--wait-for", "p.never")):
                with self.subTest(options=options):
                    result = self.build_failing(f"{server.origin}/start", Path(temp_dir), *options)

                    self.assertEqual(
                        result.stdout.strip(),
                        "Error fetching remote page: Malformed or unavailable response: net::ERR_CONNECTION_REFUSED",
                    )

    def test_a_page_sent_as_a_download_fails_and_no_file_is_written(self) -> None:
        name = "site2md-browser-test-download.html"
        headers = {"Content-Type": "text/html", "Content-Disposition": f'attachment; filename="{name}"'}
        with RecordingServer({"/page": (200, headers, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            # On Windows the folder for downloads is the user's, whatever the environment says.
            downloads = Path.home() / "Downloads" if sys.platform == "win32" else temp_root / "Downloads"
            self.addCleanup((downloads / name).unlink, missing_ok=True)
            environment = self.startup_hook_environment(temp_root, DELAY_CLOSE_HOOK)
            environment["HOME"] = str(temp_root)

            result = self.build_failing(f"{server.origin}/page", temp_root, extra_environment=environment)

            self.assertEqual(
                result.stdout.strip(),
                "Error fetching remote page: Final response is a download, which the browser refuses, not a page.",
            )
            self.assertFalse((downloads / name).exists())

    def test_a_page_over_the_size_limit_fails_as_it_does_under_a_plain_fetch(self) -> None:
        def stream(handler: BaseHTTPRequestHandler) -> None:
            # No Content-Length, as for a page that a server makes as it goes.
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.end_headers()
            handler.wfile.write(b"<html><body><p>" + b"x" * (2 * 1024 * 1024) + b"</p></body></html>")

        large_dom = script_page('document.getElementById("content").textContent = "x".repeat(2 * 1024 * 1024);')
        routes: dict[str, Route] = {
            "/declared": (200, HTML, b"<html><body><p>" + b"x" * (2 * 1024 * 1024) + b"</p></body></html>"),
            "/streamed": stream,
            "/script": (200, HTML, large_dom),
        }
        expected = {
            "/declared": "Response declares 2097185 bytes, exceeding the 1 MiB limit.",
            "/streamed": "Response exceeded the 1 MiB limit while streaming.",
            # A small page that builds a large one is read as the browser shows it.
            "/script": "Response exceeded the 1 MiB limit while streaming.",
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            for path, message in expected.items():
                with self.subTest(path=path):
                    result = self.build_failing(f"{server.origin}{path}", Path(temp_dir), "--max-page-size-mib", "1")

                    self.assertEqual(result.stdout.strip(), f"Error fetching remote page: {message}")

    def test_a_page_that_is_not_ready_in_time_fails_as_a_slow_response_does(self) -> None:
        never_answers = self.never_answers()
        # Its own time stands still while this request is open, so only the wall clock ends the wait.
        keeps_a_request_open = script_page('fetch("/hang");')
        routes: dict[str, Route] = {
            "/slow": never_answers,
            "/open": (200, HTML, keeps_a_request_open),
            "/hang": never_answers,
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            hook_environment = self.startup_hook_environment(Path(temp_dir), SHORT_TIMEOUT_HOOK)
            for path in ("/slow", "/open"):
                with self.subTest(path=path):
                    result = self.build_failing(
                        f"{server.origin}{path}", Path(temp_dir), extra_environment=hook_environment
                    )

                    self.assertEqual(
                        result.stdout.strip(),
                        "Error fetching remote page: Malformed or unavailable response: timed out",
                    )

    def test_a_selector_that_never_matches_fails_at_the_timeout_and_names_the_selector(self) -> None:
        page = script_page('document.getElementById("content").innerHTML = "<p>Here</p>";')
        with RecordingServer({"/page": (200, HTML, page)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            # The timeout runs from the start of the browser, so a slow start must leave time for the wait.
            hook_environment = self.startup_hook_environment(Path(temp_dir), SLOW_START_HOOK + TWENTY_SECOND_TIMEOUT_HOOK)

            result = self.build_failing(
                f"{server.origin}/page", Path(temp_dir), "--wait-for", "li[data-never]", extra_environment=hook_environment
            )

            self.assertEqual(
                result.stdout.strip(),
                "Error fetching remote page: No element matched the --wait-for selector 'li[data-never]' within 20 seconds.",
            )

    def test_an_invalid_selector_fails_before_any_request_to_the_site(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            # Brackets and backslashes must reach the line as they are written.
            for selector in ("li[", "!!!", "a >", "p[bold] >", r"a\:b >"):
                with self.subTest(selector=selector):
                    result = self.build_failing(f"{server.origin}/page", Path(temp_dir), "--wait-for", selector)

                    self.assertEqual(result.stdout.strip(), f"Error: Invalid wait-for selector: '{selector}'")
            self.assertEqual(server.requests, [])

    def test_an_invalid_selector_is_kept_in_the_index_as_invalid_and_not_as_a_failed_fetch(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            url = f"{server.origin}/page"

            result = self.build_failing(url, Path(temp_dir), "--wait-for", "li[", "--keep-temp")

            self.assertEqual(result.stdout.splitlines()[0], "Error: Invalid wait-for selector: 'li['")
            index = json.loads((self.retained_workspace(result.stdout) / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(
                index["pages"],
                [{"requested_url": url, "html": "page.html", "status": "invalid", "detail": "Invalid wait-for selector: 'li['"}],
            )

    def test_an_https_to_http_redirect_is_refused_before_the_http_request_leaves(self) -> None:
        with RecordingServer({"/late": (200, HTML, PLAIN_PAGE)}) as plain_server:
            routes: dict[str, Route] = {"/start": (302, {"Location": f"{plain_server.origin}/late"}, b"")}
            with RecordingServer(routes, certificate=CERTIFICATE) as secure_server, tempfile.TemporaryDirectory() as temp_dir:
                hook_environment = self.startup_hook_environment(Path(temp_dir), ACCEPT_TEST_CERTIFICATE_HOOK)

                result = self.build_failing(
                    f"{secure_server.origin}/start", Path(temp_dir), extra_environment=hook_environment
                )

                self.assertEqual(
                    result.stdout.strip(),
                    "Error fetching remote page: Refusing HTTPS-to-HTTP redirect downgrade.",
                )
                self.assertEqual(secure_server.requests, ["/start"])
                self.assertEqual(plain_server.requests, [])

    def test_an_https_to_http_move_that_the_page_makes_is_refused_before_the_http_request_leaves(self) -> None:
        with RecordingServer({"/late": (200, HTML, PLAIN_PAGE)}) as plain_server:
            routes: dict[str, Route] = {
                "/script": (
                    200,
                    HTML,
                    script_page(f'setTimeout(function () {{ location.href = "{plain_server.origin}/late"; }}, 300);'),
                ),
                "/refresh": (
                    200,
                    HTML,
                    f'<html><head><meta http-equiv="refresh" content="0;url={plain_server.origin}/late"></head>'
                    "<body>x</body></html>".encode(),
                ),
            }
            with RecordingServer(routes, certificate=CERTIFICATE) as secure_server, tempfile.TemporaryDirectory() as temp_dir:
                hook_environment = self.startup_hook_environment(Path(temp_dir), ACCEPT_TEST_CERTIFICATE_HOOK)
                for path in ("/script", "/refresh"):
                    # With a selector, the build must not go on waiting for it either.
                    for options in ((), ("--wait-for", "p.never")):
                        with self.subTest(path=path, options=options):
                            result = self.build_failing(
                                f"{secure_server.origin}{path}", Path(temp_dir), *options, extra_environment=hook_environment
                            )

                            self.assertEqual(
                                result.stdout.strip(),
                                "Error fetching remote page: Refusing HTTPS-to-HTTP redirect downgrade.",
                            )
                            self.assertEqual(plain_server.requests, [])

    def test_an_https_page_is_read_when_the_browser_accepts_the_certificate(self) -> None:
        # The control for the refusal above: it fails for the redirect, not for the certificate.
        routes: dict[str, Route] = {"/page": (200, HTML, PLAIN_PAGE)}
        with RecordingServer(routes, certificate=CERTIFICATE) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            hook_environment = self.startup_hook_environment(temp_root, ACCEPT_TEST_CERTIFICATE_HOOK)
            output = temp_root / "out.md"

            result = self.run_site2md(
                "build", f"{server.origin}/page", "--browser", "--output", output, "--no-progress",
                timeout=90,
                extra_environment=hook_environment,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(f"<!-- Source: {server.origin}/page -->", output.read_text(encoding="utf-8"))

    def test_a_missing_browser_fails_with_one_line_that_names_the_variable(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)

            result = self.build_failing(
                f"{server.origin}/page",
                temp_root,
                extra_environment={"SITE2MD_BROWSER": str(temp_root / "no-such-browser")},
            )

            self.assertIn("SITE2MD_BROWSER", result.stdout)
            self.assertEqual(len(result.stdout.strip().splitlines()), 1)
            self.assertEqual(server.requests, [])

    def test_a_browser_that_does_not_start_fails_with_one_line_that_gives_its_reason(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            (temp_root / TEMP_FOLDER).mkdir()

            # Python stops at once on the browser's first option, and says that it doesn't know it.
            result = self.build_failing(
                f"{server.origin}/page",
                temp_root,
                extra_environment={**self.temp_environment(temp_root), "SITE2MD_BROWSER": sys.executable},
            )

            self.assertEqual(len(result.stdout.strip().splitlines()), 1)
            self.assertTrue(
                result.stdout.startswith("Error fetching remote page: The browser stopped before the page was read: "),
                result.stdout,
            )
            self.assertIn("--headless", result.stdout)
            self.assertEqual(server.requests, [])
            self.assert_no_browser_left(temp_root)


class BrowserCleanupTests(BrowserTestCase):
    """No browser process and no folder of the run is left, however the run ends."""

    def run_in_clean_folder(
        self, url: str, *, hook: str | None = None
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        """Run build --browser with the temporary folder set to a new one, and return the result and its root."""
        root = self.new_test_root()
        environment = self.temp_environment(root)
        if hook is not None:
            environment.update(self.startup_hook_environment(root, hook))
        output = root / "out.md"
        output.write_text("previous", encoding="utf-8")
        result = self.run_site2md(
            "build", url, "--browser", "--output", output, "--no-progress",
            timeout=90,
            extra_environment=environment,
        )
        return result, root

    def test_after_a_successful_build(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server:
            result, root = self.run_in_clean_folder(f"{server.origin}/page")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assert_no_browser_left(root)

    def test_after_a_failed_build(self) -> None:
        with RecordingServer({"/page": (404, HTML, PLAIN_PAGE)}) as server:
            result, root = self.run_in_clean_folder(f"{server.origin}/page")

            self.assertNotEqual(result.returncode, 0)
            self.assert_no_browser_left(root)

    def test_after_a_page_that_is_not_ready_in_time(self) -> None:
        with RecordingServer({"/slow": self.never_answers()}) as server:
            result, root = self.run_in_clean_folder(f"{server.origin}/slow", hook=SHORT_TIMEOUT_HOOK)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("timed out", result.stdout)
            self.assert_no_browser_left(root)

    def test_a_browser_folder_that_cannot_be_removed_fails_the_build_with_one_line_that_names_it(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server:
            result, root = self.run_in_clean_folder(f"{server.origin}/page", hook=KEEP_BROWSER_FOLDER_HOOK)

            leftovers = [path for path in (root / TEMP_FOLDER).iterdir() if path.name.startswith("site2md_browser_")]
            self.assertEqual(len(leftovers), 1, "the hook leaves the folder")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(
                result.stdout.startswith(
                    f"Error cleaning remote workspace: Could not remove the browser's temporary folder '{leftovers[0]}': "
                ),
                result.stdout,
            )
            self.assertNotIn("Success", result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual((root / "out.md").read_text(encoding="utf-8"), "previous")

    def test_a_failed_build_reports_its_own_failure_and_not_the_folder_that_stays(self) -> None:
        with RecordingServer({"/page": (404, HTML, PLAIN_PAGE)}) as server:
            result, _ = self.run_in_clean_folder(f"{server.origin}/page", hook=KEEP_BROWSER_FOLDER_HOOK)

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout.strip(), "Error fetching remote page: Final response returned HTTP 404.")

    def test_after_an_interruption(self) -> None:
        with RecordingServer({"/page": (200, HTML, PLAIN_PAGE)}) as server:
            result, root = self.run_in_clean_folder(f"{server.origin}/page", hook=INTERRUPT_AT_NAVIGATION_HOOK)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((root / "out.md").read_text(encoding="utf-8"), "previous")
            self.assertNotIn("Traceback", result.stderr)
            self.assert_no_browser_left(root)
