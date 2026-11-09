"""Shared support for the executable tests: providers laid out in a folder by hand."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from executable.smoke import PROVIDER


def write_provider(folder: Path, extractor_id: str, *, distribution: str = "folder-provider") -> None:
    """Write a static provider into a folder, the way `pip install --target` lays one out.

    The package is always `folder_provider`. `distribution` names the dist-info folder, so that
    two folders can hold providers that the metadata keeps apart.
    """
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
    dist_info_name = f"{distribution.replace('-', '_')}-1.0.0.dist-info"
    dist_info = folder / dist_info_name
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {distribution}\nVersion: 1.0.0\n", encoding="utf-8"
    )
    (dist_info / "entry_points.txt").write_text(
        f"[site2md.extractors.v1]\n{extractor_id} = folder_provider:create_extractor\n", encoding="utf-8"
    )
    (dist_info / "RECORD").write_text(
        "folder_provider/__init__.py,,\n"
        "folder_provider/provider-manifest-v1.json,,\n"
        f"{dist_info_name}/METADATA,,\n"
        f"{dist_info_name}/entry_points.txt,,\n"
        f"{dist_info_name}/RECORD,,\n",
        encoding="utf-8",
    )


def install_smoke_provider(folder: Path) -> None:
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
