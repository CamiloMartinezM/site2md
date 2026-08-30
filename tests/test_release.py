"""Installed release metadata tests for site2md."""

from __future__ import annotations

import subprocess
import sys
import unittest
from importlib.metadata import metadata, requires, version
from pathlib import Path

from packaging.requirements import Requirement


class ReleaseMetadataTests(unittest.TestCase):
    """Exercise package identity and compatibility through installed metadata."""

    def test_package_and_cli_report_version_0_3_0(self) -> None:
        command = Path(sys.executable).with_name("site2md")

        result = subprocess.run(
            [str(command), "--version"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(version("site2md"), "0.3.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.3.0")

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
        self.assertEqual([str(requirement.specifier) for requirement in marko], ["<3,>=2.2.4"])
        self.assertEqual(
            {(str(requirement.specifier), str(requirement.marker)) for requirement in jsonschema},
            {
                ("<4.25,>=4.18", 'python_version < "3.10"'),
                ("<5,>=4.18", 'python_version >= "3.10"'),
            },
        )


if __name__ == "__main__":
    unittest.main()
