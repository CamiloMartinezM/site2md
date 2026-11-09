"""Installed-command tests of build --extract, which converts and extracts in one process."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from tests.cli_test_support import InstalledCliTestCase, RecordingServer, Route

COUNTRIES_ID = "site2md.scrapethissite.countries"
HTML = {"Content-Type": "text/html"}
CURACAO = """<div class="country"><h3 class="country-name">Curaçao</h3>
<div class="country-info"><strong>Capital:</strong> <span>Willemstad</span><br>
<strong>Population:</strong> <span>150000</span><br>
<strong>Area (km<sup>2</sup>):</strong> <span>444</span><br></div></div>"""
ARUBA = """<div class="country"><h3 class="country-name">Aruba</h3>
<div class="country-info"><strong>Capital:</strong> <span>Oranjestad</span><br>
<strong>Population:</strong> <span>106000</span><br>
<strong>Area (km<sup>2</sup>):</strong> <span>180</span><br></div></div>"""
COUNTRIES_PAGE = f"<html><body><main>{CURACAO}{ARUBA}</main></body></html>"
COUNTRIES_VALUES = """[
  {
    "name": "Curaçao",
    "capital": "Willemstad",
    "population": 150000,
    "area_km2": 444.0
  },
  {
    "name": "Aruba",
    "capital": "Oranjestad",
    "population": 106000,
    "area_km2": 180.0
  }
]
""".encode()

# Follow and site mode wait a second between requests. The hook skips the wait.
SKIP_PACING_HOOK = """from site2md import downloader
downloader.time.sleep = lambda _seconds: None
"""
# Records what build passes to the extraction module's extract operation.
RECORD_EXTRACT_CALL_HOOK = """import json
import os
from site2md import extraction

real_extract = extraction.extract


def recording_extract(markdown, extractor_id, **options):
    with open(os.environ["SITE2MD_EXTRACT_LOG"], "w", encoding="utf-8") as log:
        json.dump({"extractor_id": extractor_id, "options": options}, log)
    return real_extract(markdown, extractor_id, **options)


extraction.extract = recording_extract
"""
FAIL_EXTRACTION_HOOK = """from site2md import extraction


def fail_extraction(markdown, extractor_id, **options):
    raise extraction.ExtractionError(
        "site2md.test.extraction_failed", "forced extraction failure"
    )


extraction.extract = fail_extraction
"""
NOISY_EXTRACTOR_HOOK = """import ctypes
import os
import sys
from site2md.extractors import countries

real_create_extractor = countries.create_extractor


class NoisyExtractor:
    def extract(self, document):
        print("provider standard output")
        print("provider standard error", file=sys.stderr)
        os.write(1, b"provider descriptor output\\n")
        os.write(2, b"provider descriptor error\\n")
        ctypes.CDLL("ucrtbase" if sys.platform == "win32" else None).puts(b"provider native output")
        return real_create_extractor().extract(document)


countries.create_extractor = lambda: NoisyExtractor()
"""


class BuildExtractTests(InstalledCliTestCase):
    """Check that build --extract saves the converted document, then extracts from it."""

    @staticmethod
    def write_pages(root: Path, *, html: str = COUNTRIES_PAGE) -> Path:
        """Write a one-page local folder."""
        pages = root / "pages"
        pages.mkdir()
        (pages / "index.html").write_text(html, encoding="utf-8")
        return pages

    def extract_saved(
        self, saved: Path, *options: object
    ) -> subprocess.CompletedProcess[bytes]:
        """Run site2md extract on a saved Markdown file and check that it succeeded."""
        separate = self.run_site2md_bytes("extract", COUNTRIES_ID, saved, *options)
        self.assertEqual(separate.returncode, 0, separate.stderr.decode())
        return separate

    def assert_names_kept_markdown(
        self, built: subprocess.CompletedProcess[bytes], saved: Path
    ) -> None:
        """Assert that the failure message says where the converted document was kept."""
        # The success line before it also names the file, so look for the error line itself.
        self.assertIn(f"error: the converted document is kept at {saved};", built.stderr.decode())

    def test_local_build_writes_the_extraction_result_to_standard_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            saved = root / "page.md"

            built = self.run_site2md_bytes(
                "build", self.write_pages(root), "--output", saved, "--extract", COUNTRIES_ID
            )

            self.assertEqual(built.returncode, 0, built.stderr.decode())
            self.assertIn("Aruba", saved.read_text(encoding="utf-8"))
            separate = self.extract_saved(saved)
        self.assertEqual(built.stdout, separate.stdout)
        self.assertEqual(
            [record["value"]["name"] for record in json.loads(built.stdout)["records"]],
            ["Curaçao", "Aruba"],
        )

    def test_build_messages_and_progress_bar_go_to_standard_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            built = self.run_site2md_bytes(
                "build",
                self.write_pages(root),
                "--output",
                root / "page.md",
                "--extract",
                COUNTRIES_ID,
                "--extract-output",
                root / "result.json",
            )

            self.assertEqual(built.returncode, 0, built.stderr.decode())
        self.assertEqual(built.stdout, b"")
        for message in (b"Found 1 HTML files.", b"Converting HTML to Markdown...", b"Success!"):
            self.assertIn(message, built.stderr)

    def test_values_only_writes_the_record_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            saved = root / "page.md"

            built = self.run_site2md_bytes(
                "build",
                self.write_pages(root),
                "--output",
                saved,
                "--extract",
                COUNTRIES_ID,
                "--values-only",
            )

            self.assertEqual(built.returncode, 0, built.stderr.decode())
            separate = self.extract_saved(saved, "--values-only")
        self.assertEqual(built.stdout, COUNTRIES_VALUES)
        self.assertEqual(built.stdout, separate.stdout)

    def test_extract_output_atomically_replaces_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            saved = root / "page.md"
            result = root / "result.json"
            result.write_text("previous", encoding="utf-8")

            built = self.run_site2md_bytes(
                "build",
                self.write_pages(root),
                "--output",
                saved,
                "--extract",
                COUNTRIES_ID,
                "--extract-output",
                result,
            )

            self.assertEqual(built.returncode, 0, built.stderr.decode())
            self.assertEqual(result.read_bytes(), self.extract_saved(saved).stdout)
            self.assertEqual(list(root.glob(".result.json.*.tmp")), [])

    def test_entry_points_only_reaches_the_extraction_module(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log = root / "extract-call.json"
            environment = self.startup_hook_environment(root, RECORD_EXTRACT_CALL_HOOK)
            environment["SITE2MD_EXTRACT_LOG"] = str(log)
            pages = self.write_pages(root)

            for options, expected in (((), False), (("--entry-points-only",), True)):
                with self.subTest(options=options):
                    built = self.run_site2md_bytes(
                        "build",
                        pages,
                        "--output",
                        root / "page.md",
                        "--extract",
                        COUNTRIES_ID,
                        *options,
                        extra_environment=environment,
                    )

                    self.assertEqual(built.returncode, 0, built.stderr.decode())
                    call = json.loads(log.read_text(encoding="utf-8"))
                    self.assertEqual(call["extractor_id"], COUNTRIES_ID)
                    self.assertEqual(call["options"], {"entry_points_only": expected})

    def test_page_mode_extracts_from_the_saved_markdown(self) -> None:
        routes: dict[str, Route] = {"/page": (200, HTML, COUNTRIES_PAGE.encode())}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            saved = Path(temp_dir) / "page.md"

            built = self.run_site2md_bytes(
                "build", f"{server.origin}/page", "--output", saved, "--extract", COUNTRIES_ID
            )
            values = self.run_site2md_bytes(
                "build",
                f"{server.origin}/page",
                "--output",
                saved,
                "--extract",
                COUNTRIES_ID,
                "--values-only",
            )

            self.assertEqual(built.returncode, 0, built.stderr.decode())
            self.assertEqual(built.stdout, self.extract_saved(saved).stdout)
            self.assertEqual(values.returncode, 0, values.stderr.decode())
            self.assertEqual(values.stdout, COUNTRIES_VALUES)
            self.assertIn(b"Fetched 1; skipped 0; failed 0.", values.stderr)
        self.assertEqual(server.requests, ["/page", "/page"])

    def test_follow_and_site_modes_extract_from_every_fetched_page(self) -> None:
        entry = f"""<html><body><main>{CURACAO}
<a class="detail" href="/child">Child</a></main></body></html>"""
        routes: dict[str, Route] = {
            "/entry": (200, HTML, entry.encode()),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/child": (200, HTML, f"<html><body><main>{ARUBA}</main></body></html>".encode()),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            environment = self.startup_hook_environment(root, SKIP_PACING_HOOK)
            for mode, options in (("follow", ("--follow-selector", "a.detail")), ("site", ())):
                with self.subTest(mode=mode):
                    saved = root / f"{mode}.md"

                    built = self.run_site2md_bytes(
                        "build",
                        f"{server.origin}/entry",
                        "--mode",
                        mode,
                        *options,
                        "--output",
                        saved,
                        "--extract",
                        COUNTRIES_ID,
                        extra_environment=environment,
                    )

                    self.assertEqual(built.returncode, 0, built.stderr.decode())
                    self.assertEqual(built.stdout, self.extract_saved(saved).stdout)
                    names = [r["value"]["name"] for r in json.loads(built.stdout)["records"]]
                    self.assertEqual(names, ["Curaçao", "Aruba"])

    def test_options_that_need_extract_fail_before_any_request(self) -> None:
        for options in (
            ("--extract-output", "result.json"),
            ("--entry-points-only",),
            ("--values-only",),
        ):
            with (
                self.subTest(options=options),
                RecordingServer({}) as server,
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                root = Path(temp_dir)

                built = self.run_site2md_bytes(
                    "build", f"{server.origin}/page", "--output", root / "page.md", *options
                )

                self.assertEqual(built.returncode, 1)
                self.assertEqual(server.requests, [])
                self.assertFalse((root / "page.md").exists())
                text = " ".join((built.stdout + built.stderr).decode().split())
                self.assertIn("require --extract.", text)

    def test_missing_extract_output_folder_fails_before_any_request(self) -> None:
        with RecordingServer({}) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing = root / "missing"

            built = self.run_site2md_bytes(
                "build",
                f"{server.origin}/page",
                "--output",
                root / "page.md",
                "--extract",
                COUNTRIES_ID,
                "--extract-output",
                missing / "result.json",
            )

            self.assertEqual(built.returncode, 1)
            self.assertEqual(built.stdout, b"")
            self.assertIn(f"Extract output folder '{missing}' does not exist.", built.stderr.decode())
            self.assertEqual(server.requests, [])
            self.assertFalse((root / "page.md").exists())

    def test_extract_output_cannot_replace_the_markdown(self) -> None:
        with RecordingServer({}) as server, tempfile.TemporaryDirectory() as temp_dir:
            saved = Path(temp_dir) / "page.md"

            built = self.run_site2md_bytes(
                "build",
                f"{server.origin}/page",
                "--output",
                saved,
                "--extract",
                COUNTRIES_ID,
                "--extract-output",
                saved,
            )

            self.assertEqual(built.returncode, 1)
            self.assertEqual(server.requests, [])
            self.assertFalse(saved.exists())
            self.assertIn("--extract-output must differ", " ".join(built.stderr.decode().split()))

    def test_missing_extractor_keeps_the_markdown_and_names_it(self) -> None:
        routes: dict[str, Route] = {"/page": (200, HTML, COUNTRIES_PAGE.encode())}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            saved = root / "page.md"
            result = root / "result.json"
            result.write_text("previous", encoding="utf-8")

            for options in ((), ("--extract-output", result)):
                with self.subTest(options=options):
                    saved.unlink(missing_ok=True)

                    built = self.run_site2md_bytes(
                        "build",
                        f"{server.origin}/page",
                        "--output",
                        saved,
                        "--extract",
                        "site2md.no.such.extractor",
                        *options,
                    )

                    self.assertEqual(built.returncode, 1)
                    self.assertEqual(built.stdout, b"")
                    self.assertIn(b"site2md.extractor_unknown", built.stderr)
                    self.assert_names_kept_markdown(built, saved)
                    self.assertNotIn(b"Traceback", built.stderr)
                    self.assertIn("Aruba", saved.read_text(encoding="utf-8"))
                    self.assertEqual(result.read_text(encoding="utf-8"), "previous")
        self.assertEqual(server.requests, ["/page", "/page"])

    def test_failing_extractor_keeps_the_markdown_and_names_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            saved = root / "page.md"
            result = root / "result.json"
            result.write_text("previous", encoding="utf-8")

            built = self.run_site2md_bytes(
                "build",
                self.write_pages(root),
                "--output",
                saved,
                "--extract",
                COUNTRIES_ID,
                "--extract-output",
                result,
                extra_environment=self.startup_hook_environment(root, FAIL_EXTRACTION_HOOK),
            )

            self.assertEqual(built.returncode, 1)
            self.assertEqual(built.stdout, b"")
            self.assertIn(b"forced extraction failure", built.stderr)
            self.assert_names_kept_markdown(built, saved)
            self.assertNotIn(b"Traceback", built.stderr)
            self.assertIn("Aruba", saved.read_text(encoding="utf-8"))
            self.assertEqual(result.read_text(encoding="utf-8"), "previous")

    def test_provider_output_stays_off_standard_output_and_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            built = self.run_site2md_bytes(
                "build",
                self.write_pages(root),
                "--output",
                root / "page.md",
                "--extract",
                COUNTRIES_ID,
                extra_environment=self.startup_hook_environment(root, NOISY_EXTRACTOR_HOOK),
            )

        self.assertEqual(built.returncode, 0, built.stderr.decode())
        json.loads(built.stdout)
        for noise in (b"provider standard", b"provider descriptor", b"provider native"):
            self.assertNotIn(noise, built.stdout)
            self.assertNotIn(noise, built.stderr)

    def test_local_folder_without_html_fails_instead_of_extracting_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "pages").mkdir()

            built = self.run_site2md_bytes(
                "build", root / "pages", "--output", root / "page.md", "--extract", COUNTRIES_ID
            )

            self.assertEqual(built.returncode, 1)
            self.assertEqual(built.stdout, b"")
            self.assertIn(b"No HTML files found.", built.stderr)
            self.assertFalse((root / "page.md").exists())
