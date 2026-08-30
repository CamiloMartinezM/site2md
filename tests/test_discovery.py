"""Public-interface tests for installed Extractor discovery."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from site2md.extraction import ExtractionError, extract, list_extractors


def _manifest(extractor_id: str, interface_version: int = 1) -> dict[str, object]:
    """Return a minimal static provider manifest for tests."""
    return {
        "manifest_version": 1,
        "extractors": [
            {
                "id": extractor_id,
                "interface_version": interface_version,
                "implementation_version": "1.4.0",
                "record_schema": {
                    "id": f"urn:example:{extractor_id}:v1",
                    "version": "1.0.0",
                    "schema": {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "$id": f"urn:example:{extractor_id}:v1",
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["instance"],
                            "properties": {"instance": {"type": "integer"}},
                        },
                    },
                },
            }
        ],
    }


def _install_provider(
    root: Path,
    *,
    distribution_name: str,
    extractor_id: str,
    module_name: str,
    module_source: str,
    manifest: object | None = None,
    entry_point_id: str | None = None,
    extra_manifest: bool = False,
) -> None:
    """Create importable package metadata for one synthetic distribution."""
    normalized_name = distribution_name.replace("-", "_")
    dist_info = root / f"{normalized_name}-2.3.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\n"
        f"Name: {distribution_name}\n"
        "Version: 2.3.0\n",
        encoding="utf-8",
    )
    (dist_info / "entry_points.txt").write_text(
        "[site2md.extractors.v1]\n"
        f"{entry_point_id or extractor_id} = {module_name}:create_extractor\n",
        encoding="utf-8",
    )
    (root / f"{module_name}.py").write_text(module_source, encoding="utf-8")

    data_dir = root / f"{normalized_name}_data"
    data_dir.mkdir()
    manifest_path = data_dir / "provider-manifest-v1.json"
    manifest_path.write_text(
        json.dumps(_manifest(extractor_id) if manifest is None else manifest),
        encoding="utf-8",
    )
    recorded_paths = [
        f"{module_name}.py",
        str(manifest_path.relative_to(root)),
        str((dist_info / "METADATA").relative_to(root)),
        str((dist_info / "entry_points.txt").relative_to(root)),
    ]
    if extra_manifest:
        second_manifest = data_dir / "nested" / "provider-manifest-v1.json"
        second_manifest.parent.mkdir()
        second_manifest.write_text(json.dumps(_manifest(extractor_id)), encoding="utf-8")
        recorded_paths.append(str(second_manifest.relative_to(root)))
    record_path = dist_info / "RECORD"
    recorded_paths.append(str(record_path.relative_to(root)))
    record_path.write_text(
        "".join(f"{path},,\n" for path in recorded_paths),
        encoding="utf-8",
    )


@contextmanager
def _installed(root: Path, *module_names: str) -> Iterator[None]:
    """Expose synthetic distributions to import and metadata discovery."""
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    try:
        yield
    finally:
        sys.path.remove(str(root))
        for module_name in module_names:
            sys.modules.pop(module_name, None)
        importlib.invalidate_caches()


class ExtractorDiscoveryTests(unittest.TestCase):
    """Exercise discovery and selection through the public Python operations."""

    def test_synthetic_provider_is_listed_without_import_then_selected_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            imported = root / "imported"
            module_source = f'''from pathlib import Path
from site2md.extractors.v1 import Extraction, RecordCandidate

Path({str(imported)!r}).write_text("imported", encoding="utf-8")
created = 0

class SyntheticExtractor:
    def __init__(self, instance):
        self.instance = instance

    def extract(self, document):
        first = document.sections[0].nodes[0]
        return Extraction(records=(RecordCandidate(
            value={{"instance": self.instance}},
            provenance=(first.span,),
        ),))

def create_extractor():
    global created
    created += 1
    return SyntheticExtractor(created)
'''
            _install_provider(
                root,
                distribution_name="synthetic-provider",
                extractor_id="example.synthetic",
                module_name="synthetic_provider",
                module_source=module_source,
            )

            with _installed(root, "synthetic_provider"):
                info = next(
                    item for item in list_extractors() if item.id == "example.synthetic"
                )

                self.assertFalse(imported.exists())
                self.assertEqual(info.status, "available")
                self.assertEqual(info.provider_distribution, "synthetic-provider")
                self.assertEqual(info.provider_version, "2.3.0")
                self.assertEqual(info.implementation_version, "1.4.0")
                self.assertEqual(info.record_schema_id, "urn:example:example.synthetic:v1")
                self.assertEqual(info.record_schema_version, "1.0.0")
                self.assertEqual(info.record_schema["type"], "array")
                self.assertEqual(json.loads(json.dumps(info.record_schema))["type"], "array")

                first = json.loads(extract("# Synthetic\n", info.id).to_json())
                second = json.loads(extract("# Synthetic\n", info.id).to_json())

                self.assertTrue(imported.exists())
                self.assertEqual(first["records"][0]["value"], {"instance": 1})
                self.assertEqual(second["records"][0]["value"], {"instance": 2})

    def test_exact_id_conflict_fails_closed_and_reports_every_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index, provider in enumerate(["provider-z", "provider-a"]):
                marker = root / f"imported-{index}"
                _install_provider(
                    root,
                    distribution_name=provider,
                    extractor_id="example.conflict",
                    module_name=f"conflicting_provider_{index}",
                    module_source=(
                        "from pathlib import Path\n"
                        f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n"
                        "def create_extractor():\n    return object()\n"
                    ),
                )

            with _installed(root, "conflicting_provider_0", "conflicting_provider_1"):
                conflicts = [
                    item for item in list_extractors() if item.id == "example.conflict"
                ]
                with self.assertRaises(ExtractionError) as raised:
                    extract("# Never imported\n", "example.conflict")

            self.assertEqual(
                [item.provider_distribution for item in conflicts],
                ["provider-a", "provider-z"],
            )
            self.assertEqual([item.status for item in conflicts], ["conflict", "conflict"])
            self.assertEqual(raised.exception.code, "site2md.extractor_conflict")
            self.assertEqual(
                raised.exception.providers,
                ("provider-a 2.3.0", "provider-z 2.3.0"),
            )
            self.assertFalse((root / "imported-0").exists())
            self.assertFalse((root / "imported-1").exists())

    def test_unrelated_malformed_provider_does_not_block_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            valid_source = '''from site2md.extractors.v1 import Extraction, RecordCandidate
class WorkingExtractor:
    def extract(self, document):
        first = document.sections[0].nodes[0]
        return Extraction(records=(RecordCandidate(value={"instance": 1}, provenance=(first.span,)),))
def create_extractor():
    return WorkingExtractor()
'''
            _install_provider(
                root,
                distribution_name="working-provider",
                extractor_id="example.working",
                module_name="working_provider",
                module_source=valid_source,
            )
            _install_provider(
                root,
                distribution_name="malformed-provider",
                extractor_id="example.malformed",
                module_name="malformed_provider",
                module_source="raise RuntimeError('must not import')\n",
                extra_manifest=True,
            )

            with _installed(root, "working_provider", "malformed_provider"):
                entries = {
                    item.id: item
                    for item in list_extractors()
                    if item.id.startswith("example.")
                }
                result = extract("# Working\n", "example.working")

            self.assertEqual(entries["example.working"].status, "available")
            self.assertEqual(entries["example.malformed"].status, "unavailable")
            self.assertIn("exactly one", entries["example.malformed"].detail)
            self.assertEqual(json.loads(result.to_json())["records"][0]["value"], {"instance": 1})

    def test_unknown_unsupported_and_broken_providers_raise_structured_failures(self) -> None:
        with self.assertRaises(ExtractionError) as unknown:
            extract("# Unknown\n", "example.does-not-exist")
        self.assertEqual(unknown.exception.code, "site2md.extractor_unknown")

        cases = [
            (
                "unsupported-provider",
                "example.unsupported",
                "unsupported_provider",
                "def create_extractor():\n    return object()\n",
                _manifest("example.unsupported", interface_version=2),
                "site2md.extractor_unsupported",
                None,
            ),
            (
                "import-provider",
                "example.import-failure",
                "import_provider",
                "raise RuntimeError('import exploded')\n",
                None,
                "site2md.extractor_import_failed",
                RuntimeError,
            ),
            (
                "factory-provider",
                "example.factory-failure",
                "factory_provider",
                "def create_extractor():\n    raise RuntimeError('factory exploded')\n",
                None,
                "site2md.extractor_factory_failed",
                RuntimeError,
            ),
            (
                "interface-provider",
                "example.interface-failure",
                "interface_provider",
                "def create_extractor():\n    return object()\n",
                None,
                "site2md.extractor_interface_invalid",
                TypeError,
            ),
        ]
        for provider, extractor_id, module, source, manifest, code, cause in cases:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                _install_provider(
                    root,
                    distribution_name=provider,
                    extractor_id=extractor_id,
                    module_name=module,
                    module_source=source,
                    manifest=manifest,
                )
                with _installed(root, module), self.assertRaises(
                    ExtractionError
                ) as raised:
                    extract("# Failure\n", extractor_id)
                self.assertEqual(raised.exception.code, code)
                if cause is not None:
                    self.assertIsInstance(raised.exception.__cause__, cause)


class ExtractionContractTests(unittest.TestCase):
    """Exercise provider contracts through the public extraction operation."""

    def test_invalid_or_remote_schema_is_rejected_before_provider_import(self) -> None:
        cases = {
            "remote": {"items": {"$ref": "https://example.test/record.json"}},
            "missing-local": {"items": {"$ref": "#/$defs/missing"}},
            "nested-anchor": {
                "items": {"$ref": "#record"},
                "$defs": {
                    "other": {
                        "$id": "urn:example:other-resource",
                        "$anchor": "record",
                        "type": "object",
                    }
                },
            },
            "wrong-root": {"type": "object"},
            "wrong-draft": {"$schema": "http://json-schema.org/draft-07/schema#"},
        }
        for suffix, replacement in cases.items():
            with self.subTest(case=suffix), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                extractor_id = f"example.schema-{suffix}"
                manifest = _manifest(extractor_id)
                declaration = manifest["extractors"][0]  # type: ignore[index]
                schema = declaration["record_schema"]["schema"]  # type: ignore[index]
                schema.update(replacement)  # type: ignore[union-attr]
                imported = root / "imported"
                _install_provider(
                    root,
                    distribution_name=f"schema-{suffix}-provider",
                    extractor_id=extractor_id,
                    module_name=f"schema_{suffix.replace('-', '_')}_provider",
                    module_source=(
                        "from pathlib import Path\n"
                        f"Path({str(imported)!r}).write_text('imported', encoding='utf-8')\n"
                        "def create_extractor():\n    return object()\n"
                    ),
                    manifest=manifest,
                )
                module = f"schema_{suffix.replace('-', '_')}_provider"
                with _installed(root, module):
                    info = next(
                        item for item in list_extractors() if item.id == extractor_id
                    )
                    with self.assertRaises(ExtractionError) as raised:
                        extract("# Must not execute\n", extractor_id)

                self.assertEqual(info.status, "unavailable")
                self.assertEqual(raised.exception.code, "site2md.extractor_unavailable")
                self.assertFalse(imported.exists())

    def test_local_references_work_and_format_checking_is_disabled(self) -> None:
        extractor_id = "example.local-schema"
        manifest = _manifest(extractor_id)
        declaration = manifest["extractors"][0]  # type: ignore[index]
        schema = declaration["record_schema"]["schema"]  # type: ignore[index]
        schema["$defs"] = {  # type: ignore[index]
            "record": {
                "type": "object",
                "required": ["instance"],
                "properties": {
                    "instance": {"type": "string", "format": "uuid"},
                    "literal": {
                        "const": {"$ref": "https://example.test/instance-data"}
                    },
                },
            }
        }
        schema["items"] = {"$ref": "#/$defs/record"}  # type: ignore[index]
        source = '''from site2md.extractors.v1 import Extraction, RecordCandidate
class LocalReferenceExtractor:
    def extract(self, document):
        return Extraction(records=(RecordCandidate(value={"instance": "not-a-uuid"}, provenance=(document.sections[0].nodes[0].span,)),))
def create_extractor():
    return LocalReferenceExtractor()
'''
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _install_provider(
                root,
                distribution_name="local-schema-provider",
                extractor_id=extractor_id,
                module_name="local_schema_provider",
                module_source=source,
                manifest=manifest,
            )
            with _installed(root, "local_schema_provider"):
                result = extract("# Local schema\n", extractor_id)

        self.assertEqual(
            json.loads(result.to_json())["records"][0]["value"]["instance"],
            "not-a-uuid",
        )

    def test_collection_schema_controls_zero_records_and_array_constraints(self) -> None:
        source = '''from site2md.extractors.v1 import Extraction, RecordCandidate
class CollectionExtractor:
    def extract(self, document):
        records = () if INSTANCE is None else (RecordCandidate(value={"instance": INSTANCE}, provenance=(document.sections[0].nodes[0].span,)),)
        return Extraction(records=records)
def create_extractor():
    return CollectionExtractor()
'''
        cases = (("zero", None, None, True), ("minimum", 1, 2, False))
        for suffix, instance, minimum, succeeds in cases:
            with self.subTest(case=suffix), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                extractor_id = f"example.collection-{suffix}"
                manifest = _manifest(extractor_id)
                declaration = manifest["extractors"][0]  # type: ignore[index]
                schema = declaration["record_schema"]["schema"]  # type: ignore[index]
                if minimum is not None:
                    schema["minItems"] = minimum  # type: ignore[index]
                module = f"collection_{suffix}_provider"
                _install_provider(
                    root,
                    distribution_name=f"collection-{suffix}-provider",
                    extractor_id=extractor_id,
                    module_name=module,
                    module_source=f"INSTANCE = {instance!r}\n{source}",
                    manifest=manifest,
                )
                with _installed(root, module):
                    if succeeds:
                        payload = json.loads(extract("# Collection\n", extractor_id).to_json())
                        self.assertEqual(payload["records"], [])
                    else:
                        with self.assertRaises(ExtractionError) as raised:
                            extract("# Collection\n", extractor_id)
                        self.assertEqual(
                            raised.exception.code,
                            "site2md.record_schema_validation_failed",
                        )

    def test_manifest_versions_follow_independent_versioning_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            extractor_id = "example.invalid-version"
            manifest = _manifest(extractor_id)
            declaration = manifest["extractors"][0]  # type: ignore[index]
            declaration["implementation_version"] = "not a version"  # type: ignore[index]
            declaration["record_schema"]["version"] = "1"  # type: ignore[index]
            _install_provider(
                root,
                distribution_name="invalid-version-provider",
                extractor_id=extractor_id,
                module_name="invalid_version_provider",
                module_source="def create_extractor():\n    return object()\n",
                manifest=manifest,
            )
            with _installed(root, "invalid_version_provider"):
                info = next(
                    item for item in list_extractors() if item.id == extractor_id
                )

        self.assertEqual(info.status, "unavailable")
        self.assertIn("PEP 440", info.detail)
        self.assertIn("semantic versioning", info.detail)

    def test_record_and_field_order_are_preserved_without_deduplication(self) -> None:
        extractor_id = "example.ordered"
        manifest = _manifest(extractor_id)
        declaration = manifest["extractors"][0]  # type: ignore[index]
        schema = declaration["record_schema"]["schema"]  # type: ignore[index]
        schema["items"] = {"type": "object"}  # type: ignore[index]
        source = '''from site2md.extractors.v1 import Extraction, RecordCandidate
class OrderedExtractor:
    def extract(self, document):
        span = document.sections[0].nodes[0].span
        return Extraction(records=(
            RecordCandidate(value={"second": 2, "first": 1}, provenance=(span,)),
            RecordCandidate(value={"second": 2, "first": 1}, provenance=(span,)),
        ))
def create_extractor():
    return OrderedExtractor()
'''
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _install_provider(
                root,
                distribution_name="ordered-provider",
                extractor_id=extractor_id,
                module_name="ordered_provider",
                module_source=source,
                manifest=manifest,
            )
            with _installed(root, "ordered_provider"):
                payload = json.loads(extract("# Ordered\n", extractor_id).to_json())

        self.assertEqual(len(payload["records"]), 2)
        self.assertEqual(
            list(payload["records"][0]["value"]),
            ["second", "first"],
        )
        self.assertEqual(
            payload["records"][0]["value"],
            payload["records"][1]["value"],
        )


class ExtractorsCliTests(unittest.TestCase):
    """Exercise the installed human-readable listing command."""

    def test_listing_succeeds_and_is_deterministic_with_broken_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _install_provider(
                root,
                distribution_name="broken-provider",
                extractor_id="example.broken",
                module_name="broken_provider",
                module_source="raise RuntimeError('must not import')\n",
                extra_manifest=True,
            )
            command = Path(sys.executable).with_name("site2md")
            environment = os.environ.copy()
            existing_path = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = (
                f"{root}{os.pathsep}{existing_path}" if existing_path else str(root)
            )

            first = subprocess.run(
                [str(command), "extractors"],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            second = subprocess.run(
                [str(command), "extractors"],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertIn("example.broken", first.stdout)
        self.assertIn("unavailable", first.stdout)
        self.assertNotIn("Traceback", first.stderr)


if __name__ == "__main__":
    unittest.main()
