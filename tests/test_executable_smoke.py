"""Tests for the executable smoke test's comparisons against the package."""

from __future__ import annotations

import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from executable.smoke import PROVIDER, run_smoke

ENTRY_SCRIPT = Path(__file__).resolve().parents[1] / "executable" / "entry.py"
PACKAGE = [sys.executable, "-m", "site2md.main"]
# The entry script run by Python is the executable minus the freezing.
UNFROZEN = [sys.executable, str(ENTRY_SCRIPT)]


def _install_smoke_provider(folder: Path) -> None:
    """Lay out the smoke provider in a folder by hand, as `pip install --target` would."""
    shutil.copytree(PROVIDER / "smoke_headings", folder / "smoke_headings", ignore=shutil.ignore_patterns("__pycache__"))
    dist_info = folder / "smoke_headings-0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text("Metadata-Version: 2.1\nName: smoke-headings\nVersion: 0\n", encoding="utf-8")
    (dist_info / "entry_points.txt").write_text(
        "[site2md.extractors.v1]\nsmoke.headings = smoke_headings:create_extractor\n", encoding="utf-8"
    )
    (dist_info / "RECORD").write_text(
        "smoke_headings/__init__.py,,\n"
        "smoke_headings/provider-manifest-v1.json,,\n"
        "smoke_headings-0.dist-info/METADATA,,\n"
        "smoke_headings-0.dist-info/entry_points.txt,,\n"
        "smoke_headings-0.dist-info/RECORD,,\n",
        encoding="utf-8",
    )


class SmokeComparisonTests(unittest.TestCase):
    """Run the smoke steps against stand-ins for the executable."""

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.providers = self.root / "providers"
        self.providers.mkdir()
        _install_smoke_provider(self.providers)
        self.work = self.root / "work"
        self.work.mkdir()

    def smoke(self, executable: list[str]) -> list[str]:
        """Return the problems that the smoke steps report for a stand-in executable."""
        return run_smoke(PACKAGE, executable, providers=self.providers, work=self.work)

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


if __name__ == "__main__":
    unittest.main()
