"""Installed-command tests of what each command loads, and of the help that names the commands."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from tests.cli_test_support import InstalledCliTestCase

# Writes the name of every module the command has loaded by the time it exits.
RECORD_MODULES_HOOK = """import atexit
import json
import os
import sys


def record_modules():
    with open(os.environ["SITE2MD_MODULE_LOG"], "w", encoding="utf-8") as log:
        json.dump(sorted(sys.modules), log)


atexit.register(record_modules)
"""

CONVERSION_MODULES = (
    "site2md.converter",
    "site2md.downloader",
    "site2md.finder",
    "site2md.merger",
    "site2md.remote_build",
)
EXTRACTION_MODULES = ("site2md.extraction", "site2md.extractors", "site2md.file_extraction")

BUILD_SUMMARY = "Build a single Markdown file from a local HTML directory or remote page."
EXTRACT_SUMMARY = "Extract structured records from a Markdown file or standard input."
EXTRACTORS_SUMMARY = "List installed Extractors using static provider metadata."


class CommandStartupTests(InstalledCliTestCase):
    """Check that a command loads only its own modules and that help still describes them all."""

    def modules_loaded_by(
        self, root: Path, *arguments: object, environment: dict[str, str] | None = None
    ) -> set[str]:
        """Run the installed command and return the names of the modules it loaded."""
        log = root / "modules.json"
        hook_environment = self.startup_hook_environment(root, RECORD_MODULES_HOOK)
        hook_environment["SITE2MD_MODULE_LOG"] = str(log)
        hook_environment.update(environment or {})

        result = self.run_site2md(*arguments, extra_environment=hook_environment)

        self.assertEqual(result.returncode, 0, result.stderr)
        return set(json.loads(log.read_text(encoding="utf-8")))

    def modules_loaded_by_local_build(
        self, *options: object, environment: dict[str, str] | None = None
    ) -> set[str]:
        """Build a one-page local folder with the options and return the modules it loaded."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = root / "pages"
            pages.mkdir()
            (pages / "index.html").write_text(
                "<html><body><main><p>Hello</p></main></body></html>", encoding="utf-8"
            )

            return self.modules_loaded_by(
                root, "build", pages, "--output", root / "out.md", *options, environment=environment
            )

    def help_text(self, *arguments: object) -> str:
        """Run the installed command with --help and return its text without box-drawing."""
        result = self.run_site2md(*arguments, "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        # Strip the whole box-drawing block, and rejoin lines that Rich wrapped.
        return " ".join(re.sub(r"[─-╿]+", " ", result.stdout).split())

    def assert_has_no_command_panel(self, text: str) -> None:
        """Assert that a command's help doesn't list --help and --version as commands."""
        self.assertNotIn("Commands", text)
        self.assertNotIn("--version", text)

    @staticmethod
    def is_loaded(modules: set[str], name: str) -> bool:
        """Return whether a module, or one of its submodules, is loaded."""
        return any(module == name or module.startswith(f"{name}.") for module in modules)

    def test_build_does_not_load_the_extraction_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = root / "pages"
            pages.mkdir()
            (pages / "index.html").write_text(
                "<html><body><main><p>Hello</p></main></body></html>", encoding="utf-8"
            )

            modules = self.modules_loaded_by(root, "build", pages, "--output", root / "out.md")

        self.assertTrue(self.is_loaded(modules, "site2md.converter"))
        for name in EXTRACTION_MODULES:
            self.assertFalse(self.is_loaded(modules, name), name)

    def test_build_with_extract_loads_the_extraction_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = root / "pages"
            pages.mkdir()
            (pages / "index.html").write_text(
                "<html><body><main><h3>Startup</h3><p><strong>Capital:</strong> Startup City<br>"
                "<strong>Population:</strong> 3<br><strong>Area (km2):</strong> 4</p>"
                "</main></body></html>",
                encoding="utf-8",
            )

            modules = self.modules_loaded_by(
                root,
                "build",
                pages,
                "--output",
                root / "out.md",
                "--extract",
                "site2md.scrapethissite.countries",
            )

        self.assertTrue(self.is_loaded(modules, "site2md.converter"))
        for name in EXTRACTION_MODULES:
            self.assertTrue(self.is_loaded(modules, name), name)

    def test_build_loads_the_progress_bar_by_default(self) -> None:
        self.assertTrue(self.is_loaded(self.modules_loaded_by_local_build(), "rich.progress"))

    def test_build_with_no_progress_does_not_load_the_progress_bar(self) -> None:
        modules = self.modules_loaded_by_local_build("--no-progress")

        self.assertFalse(self.is_loaded(modules, "rich.progress"))

    def test_plain_build_command_line_does_not_load_cyclopts(self) -> None:
        modules = self.modules_loaded_by_local_build("--no-progress", "--keep-temp")

        self.assertFalse(self.is_loaded(modules, "cyclopts"))

    def test_build_option_written_with_an_equals_sign_is_parsed_by_cyclopts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = root / "pages"
            pages.mkdir()
            (pages / "index.html").write_text(
                "<html><body><main><p>Hello</p></main></body></html>", encoding="utf-8"
            )
            output = root / "out.md"

            modules = self.modules_loaded_by(root, "build", pages, f"--output={output}")

            self.assertTrue(self.is_loaded(modules, "cyclopts"))
            self.assertIn("Hello", output.read_text(encoding="utf-8"))

    def test_build_without_a_progress_bar_or_a_terminal_does_not_load_rich(self) -> None:
        # COLUMNS keeps the long temporary paths on one line: a line to wrap goes through Rich.
        modules = self.modules_loaded_by_local_build(
            "--no-progress", environment={"COLUMNS": "500"}
        )

        self.assertFalse(self.is_loaded(modules, "rich"))

    def test_build_with_a_message_to_wrap_loads_rich(self) -> None:
        modules = self.modules_loaded_by_local_build(
            "--no-progress", environment={"COLUMNS": "20"}
        )

        self.assertTrue(self.is_loaded(modules, "rich"))

    def test_build_with_forced_colour_loads_rich(self) -> None:
        modules = self.modules_loaded_by_local_build(
            "--no-progress", environment={"COLUMNS": "500", "FORCE_COLOR": "1"}
        )

        self.assertTrue(self.is_loaded(modules, "rich"))

    def test_build_with_messages_on_the_null_device_does_not_load_rich(self) -> None:
        # On Windows the null device says that it is a terminal. With --extract the messages
        # go to standard error.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = root / "pages"
            pages.mkdir()
            (pages / "index.html").write_text(
                "<html><body><main><h3>Startup</h3><p><strong>Capital:</strong> Startup City<br>"
                "<strong>Population:</strong> 3<br><strong>Area (km2):</strong> 4</p>"
                "</main></body></html>",
                encoding="utf-8",
            )
            log = root / "modules.json"
            environment = {
                **os.environ,
                **self.startup_hook_environment(root, RECORD_MODULES_HOOK),
                "SITE2MD_MODULE_LOG": str(log),
                "PYTHONIOENCODING": "utf-8",
                "COLUMNS": "500",
            }

            result = subprocess.run(
                [
                    str(self.command),
                    "build",
                    str(pages),
                    "--no-progress",
                    "--output",
                    str(root / "out.md"),
                    "--extract",
                    "site2md.scrapethissite.countries",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=environment,
            )

            self.assertEqual(result.returncode, 0)
            modules = set(json.loads(log.read_text(encoding="utf-8")))
        self.assertFalse(self.is_loaded(modules, "rich"))

    def test_extract_does_not_load_the_conversion_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            markdown = root / "countries.md"
            markdown.write_text(
                "### Startup\n\n**Capital:** Startup City\n**Population:** 3\n**Area (km2):** 4\n",
                encoding="utf-8",
            )

            modules = self.modules_loaded_by(
                root, "extract", "site2md.scrapethissite.countries", markdown
            )

        self.assertTrue(self.is_loaded(modules, "site2md.extraction"))
        for name in CONVERSION_MODULES:
            self.assertFalse(self.is_loaded(modules, name), name)

    def test_extractors_does_not_load_the_conversion_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            modules = self.modules_loaded_by(Path(temp_dir), "extractors")

        self.assertTrue(self.is_loaded(modules, "site2md.extraction"))
        for name in CONVERSION_MODULES:
            self.assertFalse(self.is_loaded(modules, name), name)

    def test_help_lists_every_command_with_its_description(self) -> None:
        text = self.help_text()

        for name, summary in (
            ("build", BUILD_SUMMARY),
            ("extract", EXTRACT_SUMMARY),
            ("extractors", EXTRACTORS_SUMMARY),
        ):
            self.assertIn(f"{name} {summary}", text)

    def test_extract_help_describes_the_command_and_its_arguments(self) -> None:
        text = self.help_text("extract")

        self.assertIn("Usage: site2md extract", text)
        self.assertIn(EXTRACT_SUMMARY, text)
        for expected in ("EXTRACTOR-ID", "INPUT-SOURCE", "--output"):
            self.assertIn(expected, text)
        self.assert_has_no_command_panel(text)

    def test_extractors_help_describes_the_command(self) -> None:
        text = self.help_text("extractors")

        self.assertIn("Usage: site2md extractors", text)
        self.assertIn(EXTRACTORS_SUMMARY, text)
        self.assert_has_no_command_panel(text)

    def test_build_help_describes_the_command_and_its_options(self) -> None:
        text = self.help_text("build")

        self.assertIn("Usage: site2md build", text)
        self.assertIn(BUILD_SUMMARY, text)
        for expected in (
            "INPUT-SOURCE",
            "--output",
            "--keep-temp",
            "--mode",
            "--max-pages",
            "--no-progress",
            "--extract",
            "--extract-output",
            "--entry-points-only",
            "--values-only",
        ):
            self.assertIn(expected, text)
        self.assert_has_no_command_panel(text)
