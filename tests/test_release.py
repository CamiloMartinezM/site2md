"""Installed release metadata tests for site2md."""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from importlib.metadata import metadata, requires, version
from pathlib import Path

from packaging.requirements import Requirement


class ReleaseMetadataTests(unittest.TestCase):
    """Exercise package identity and compatibility through installed metadata."""

    def test_package_and_cli_report_version_0_4_0(self) -> None:
        command = Path(sys.executable).with_name("site2md")

        result = subprocess.run(
            [str(command), "--version"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(version("site2md"), "0.4.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.4.0")

    def test_python_and_extraction_dependencies_match_supported_versions(self) -> None:
        package_metadata = metadata("site2md")
        requirements = [Requirement(value) for value in requires("site2md") or ()]
        marko = [requirement for requirement in requirements if requirement.name == "marko"]
        jsonschema = [
            requirement
            for requirement in requirements
            if requirement.name == "jsonschema"
        ]

        self.assertEqual(package_metadata["Requires-Python"], ">=3.9")
        self.assertEqual(
            {requirement.name for requirement in requirements},
            {
                "beautifulsoup4",
                "cyclopts",
                "jsonschema",
                "markdownify",
                "marko",
                "packaging",
                "rich",
                "soupsieve",
            },
        )
        self.assertEqual([str(requirement.specifier) for requirement in marko], ["<3,>=2.2.4"])
        self.assertEqual(
            {(str(requirement.specifier), str(requirement.marker)) for requirement in jsonschema},
            {
                ("<4.25,>=4.18", 'python_version < "3.10"'),
                ("<5,>=4.18", 'python_version >= "3.10"'),
            },
        )

    def test_build_help_documents_traversal_contract(self) -> None:
        command = Path(sys.executable).with_name("site2md")

        result = subprocess.run(
            [str(command), "build", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        help_text = " ".join(re.sub(r"[│╭╮╰╯─]+", " ", result.stdout).split())
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in (
            "Page mode is the default",
            "Follow mode requires at least one --follow-selector",
            "Page mode rejects traversal-only options",
            "Follow mode rejects --max-depth and --include-query",
            "Site mode rejects --follow-selector",
            "Positive traversal page budget (default: 50)",
            "Positive site-mode depth budget (default: 3)",
            "Positive traversal body budget (default: 250)",
            "Positive MiB limit for one remote page (default: 25)",
        ):
            self.assertIn(expected, help_text)


if __name__ == "__main__":
    unittest.main()
