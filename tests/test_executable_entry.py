"""Tests for the executable's entry script and its Extractor provider folders."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.cli_test_support import InstalledCliTestCase

ENTRY_SCRIPT = Path(__file__).resolve().parents[1] / "executable" / "entry.py"
BUILT_IN_ID = "site2md.scrapethissite.countries"


def _write_provider(folder: Path, extractor_id: str) -> None:
    """Write a static provider into a folder, the way `pip install --target` lays one out."""
    package = folder / "folder_provider"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("def create_extractor():\n    return object()\n", encoding="utf-8")
    manifest = {
        "manifest_version": 1,
        "extractors": [
            {
                "id": extractor_id,
                "interface_version": 1,
                "implementation_version": "1.0.0",
                "record_schema": {
                    "id": "urn:example:folder-provider:v1",
                    "version": "1.0.0",
                    "schema": {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "$id": "urn:example:folder-provider:v1",
                        "type": "array",
                    },
                },
            }
        ],
    }
    (package / "provider-manifest-v1.json").write_text(json.dumps(manifest), encoding="utf-8")
    dist_info = folder / "folder_provider-1.0.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text("Metadata-Version: 2.1\nName: folder-provider\nVersion: 1.0.0\n", encoding="utf-8")
    (dist_info / "entry_points.txt").write_text(
        f"[site2md.extractors.v1]\n{extractor_id} = folder_provider:create_extractor\n", encoding="utf-8"
    )
    (dist_info / "RECORD").write_text(
        "folder_provider/__init__.py,,\n"
        "folder_provider/provider-manifest-v1.json,,\n"
        "folder_provider-1.0.0.dist-info/METADATA,,\n"
        "folder_provider-1.0.0.dist-info/entry_points.txt,,\n"
        "folder_provider-1.0.0.dist-info/RECORD,,\n",
        encoding="utf-8",
    )


def _list_extractors(provider_path: str | None, *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run `site2md extractors` through the entry script, with the variable set when given."""
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    environment.pop("SITE2MD_PROVIDER_PATH", None)
    if provider_path is not None:
        environment["SITE2MD_PROVIDER_PATH"] = provider_path
    return subprocess.run(
        [sys.executable, str(ENTRY_SCRIPT), "extractors"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        cwd=cwd,
    )


class ProviderPathTests(unittest.TestCase):
    """Exercise `SITE2MD_PROVIDER_PATH` through the entry script's process boundary."""

    def test_a_provider_in_a_named_folder_is_listed_beside_the_built_in_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "providers"
            _write_provider(folder, "example.folder.records")

            without = _list_extractors(None)
            with_folder = _list_extractors(str(folder))

        self.assertEqual(without.returncode, 0, without.stderr)
        self.assertNotIn("example.folder.records", without.stdout)
        self.assertEqual(with_folder.returncode, 0, with_folder.stderr)
        self.assertIn(BUILT_IN_ID, with_folder.stdout)
        self.assertIn("example.folder.records", with_folder.stdout)

    def test_every_folder_in_the_variable_is_searched(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first"
            second = Path(temp_dir) / "second"
            _write_provider(first, "example.first.records")
            # The same package name in a second folder would hide the first, so give it another distribution.
            _write_provider(second, "example.second.records")
            (second / "folder_provider-1.0.0.dist-info").rename(second / "second_provider-1.0.0.dist-info")
            (second / "second_provider-1.0.0.dist-info" / "METADATA").write_text(
                "Metadata-Version: 2.1\nName: second-provider\nVersion: 1.0.0\n", encoding="utf-8"
            )

            result = _list_extractors(os.pathsep.join([str(first), str(second)]))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("example.first.records", result.stdout)
        self.assertIn("example.second.records", result.stdout)

    def test_an_empty_entry_does_not_add_the_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "providers"
            _write_provider(folder, "example.folder.records")

            result = _list_extractors(os.pathsep, cwd=folder)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("example.folder.records", result.stdout)

    def test_a_named_folder_cannot_replace_a_module_the_environment_provides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "providers"
            _write_provider(folder, "example.folder.records")
            (folder / "site2md").mkdir()
            (folder / "site2md" / "__init__.py").write_text("raise RuntimeError('shadowed')\n", encoding="utf-8")

            result = _list_extractors(str(folder))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(BUILT_IN_ID, result.stdout)
        self.assertIn("example.folder.records", result.stdout)

    def test_path_files_in_a_named_folder_are_processed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "providers"
            _write_provider(folder / "lib", "example.folder.records")
            (folder / "providers.pth").write_text("lib\n", encoding="utf-8")

            result = _list_extractors(str(folder))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("example.folder.records", result.stdout)


class PackageIgnoresProviderPathTests(InstalledCliTestCase):
    """The installed package keeps finding providers in its own environment only."""

    def test_the_installed_command_does_not_read_the_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "providers"
            _write_provider(folder, "example.folder.records")

            result = self.run_site2md("extractors", extra_environment={"SITE2MD_PROVIDER_PATH": str(folder)})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(BUILT_IN_ID, result.stdout)
        self.assertNotIn("example.folder.records", result.stdout)


if __name__ == "__main__":
    unittest.main()
