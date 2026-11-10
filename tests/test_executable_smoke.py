"""Tests for the executable smoke test's comparisons against the package."""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from executable.smoke import run_smoke
from tests.browser_test_support import BrowserTestCase
from tests.executable_test_support import install_smoke_provider

ENTRY_SCRIPT = Path(__file__).resolve().parents[1] / "executable" / "entry.py"
PACKAGE = [sys.executable, "-m", "site2md.main"]
# The entry script run by Python is the executable minus the freezing.
UNFROZEN = [sys.executable, str(ENTRY_SCRIPT)]


class SmokeComparisonTests(unittest.TestCase):
    """Run the smoke steps against stand-ins for the executable."""

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.providers = self.root / "providers"
        self.providers.mkdir()
        install_smoke_provider(self.providers)
        self.work = self.root / "work"
        self.work.mkdir()

    def smoke(self, executable: list[str], *, with_browser: bool = False) -> list[str]:
        """Return the problems that the smoke steps report for a stand-in executable."""
        return run_smoke(
            PACKAGE, executable, providers=self.providers, work=self.work, with_browser=with_browser
        )

    def test_an_executable_that_behaves_like_the_package_has_no_problems(self) -> None:
        self.assertEqual(self.smoke(UNFROZEN), [])

    def test_an_extraction_that_differs_from_the_packages_is_reported(self) -> None:
        wrapper = self.root / "tampering.py"
        wrapper.write_text(
            textwrap.dedent(
                f"""\
                import subprocess
                import sys

                result = subprocess.run([sys.executable, {str(ENTRY_SCRIPT)!r}, *sys.argv[1:]], check=False)
                if sys.argv[1] == "extract":
                    sys.stdout.write(" ")
                raise SystemExit(result.returncode)
                """
            ),
            encoding="utf-8",
        )

        problems = self.smoke([sys.executable, str(wrapper)])

        self.assertEqual(
            [problem.split(":")[0] for problem in problems],
            ["extract with the built-in Extractor", "extract with an Extractor provider"],
        )
        self.assertIn("differs", problems[0])

    def test_a_failing_executable_is_reported_at_every_step(self) -> None:
        problems = self.smoke([sys.executable, "-c", "raise SystemExit(3)"])

        self.assertEqual(
            [problem.split(":")[0] for problem in problems],
            [
                "build",
                "extract with the built-in Extractor",
                "extract with an Extractor provider",
                "extractors",
            ],
        )
        self.assertIn("exited 3", problems[0])

    def test_an_executable_that_ignores_the_provider_variable_is_reported(self) -> None:
        # The package never reads SITE2MD_PROVIDER_PATH, so as an executable it can't find the provider.
        problems = self.smoke(PACKAGE)

        self.assertEqual(
            [problem.split(":")[0] for problem in problems],
            ["extract with an Extractor provider", "extractors"],
        )
        self.assertIn("exited 1", problems[0])
        self.assertIn("smoke.headings", problems[1])

    def test_a_machine_without_a_browser_skips_the_browser_step_and_a_runner_in_ci_fails_it(self) -> None:
        without_browser = {"SITE2MD_BROWSER": str(self.root / "no-such-browser")}

        with mock.patch.dict(os.environ, {**without_browser, "CI": ""}):
            skipped = self.smoke(UNFROZEN, with_browser=True)
        with mock.patch.dict(os.environ, {**without_browser, "CI": "true"}):
            in_ci = self.smoke(UNFROZEN, with_browser=True)

        self.assertEqual(skipped, [])
        self.assertEqual(len(in_ci), 1)
        self.assertTrue(in_ci[0].startswith("build with --browser: SITE2MD_BROWSER"), in_ci[0])


class BrowserSmokeTests(BrowserTestCase):
    """Run the browser step against stand-ins for the executable, on a machine that has a browser."""

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.providers = self.root / "providers"
        self.providers.mkdir()
        install_smoke_provider(self.providers)
        self.work = self.root / "work"
        self.work.mkdir()

    def smoke(self, executable: list[str]) -> list[str]:
        """Return the problems that all the smoke steps, with the browser step, report for a stand-in."""
        return run_smoke(PACKAGE, executable, providers=self.providers, work=self.work, with_browser=True)

    def test_an_executable_that_behaves_like_the_package_has_no_problems(self) -> None:
        self.assertEqual(self.smoke(UNFROZEN), [])

    def test_an_executable_that_does_not_run_the_pages_script_is_reported(self) -> None:
        wrapper = self.root / "without_browser.py"
        wrapper.write_text(
            textwrap.dedent(
                f"""                import subprocess
                import sys

                arguments = [argument for argument in sys.argv[1:] if argument != "--browser"]
                raise SystemExit(subprocess.run([sys.executable, {str(ENTRY_SCRIPT)!r}, *arguments], check=False).returncode)
                """
            ),
            encoding="utf-8",
        )

        problems = self.smoke([sys.executable, str(wrapper)])

        self.assertEqual(problems, ["build with --browser: the executable's output differs from the package's"])


if __name__ == "__main__":
    unittest.main()
