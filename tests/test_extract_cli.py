"""Installed-command integration tests for structured extraction."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ExtractCliTests(unittest.TestCase):
    """Exercise extraction through the installed command boundary."""

    command: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.command = Path(sys.executable).with_name("site2md")
        if not cls.command.is_file():
            raise RuntimeError(f"Installed site2md command not found at {cls.command}")

    def run_site2md(
        self,
        *arguments: object,
        input_bytes: bytes | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        """Run the installed command and capture its byte streams."""
        environment = os.environ.copy()
        if extra_environment:
            environment.update(extra_environment)
        return subprocess.run(
            [str(self.command), *map(str, arguments)],
            check=False,
            capture_output=True,
            input=input_bytes,
            env=environment,
        )

    @staticmethod
    def startup_hook_environment(root: Path, source: str) -> dict[str, str]:
        """Create a subprocess-only Python startup hook."""
        hook_dir = root / "startup-hook"
        hook_dir.mkdir()
        (hook_dir / "sitecustomize.py").write_text(source, encoding="utf-8")
        python_path = os.environ.get("PYTHONPATH")
        if python_path:
            hook_path = f"{hook_dir}{os.pathsep}{python_path}"
        else:
            hook_path = str(hook_dir)
        return {"PYTHONPATH": hook_path}

    def test_extract_path_writes_deterministic_json_to_standard_output(self) -> None:
        markdown = """<!-- Source: https://example.test/countries -->
### Example

**Capital:** Test City
**Population:** 125000
**Area (km2):** 468
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "countries.md"
            input_path.write_text(markdown, encoding="utf-8")

            first = self.run_site2md(
                "extract", "site2md.scrapethissite.countries", input_path
            )
            second = self.run_site2md(
                "extract", "site2md.scrapethissite.countries", input_path
            )

        self.assertEqual(first.returncode, 0, first.stderr.decode())
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, b"")
        payload = json.loads(first.stdout)
        self.assertEqual(payload["extractor"]["id"], "site2md.scrapethissite.countries")
        self.assertEqual(payload["records"][0]["value"]["name"], "Example")

    def test_extract_rejects_non_utf8_path_and_standard_input_without_traceback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "invalid.md"
            input_path.write_bytes(b"\xff")
            cases = (
                ("path", (input_path,), None),
                ("stdin", ("-",), b"\xff"),
            )
            for name, input_arguments, input_bytes in cases:
                with self.subTest(source=name):
                    result = self.run_site2md(
                        "extract",
                        "site2md.scrapethissite.countries",
                        *input_arguments,
                        input_bytes=input_bytes,
                    )

                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, b"")
                    self.assertIn(b"UTF-8", result.stderr)
                    self.assertNotIn(b"Traceback", result.stderr)

    def test_extract_reads_markdown_from_standard_input(self) -> None:
        result = self.run_site2md(
            "extract",
            "site2md.scrapethissite.countries",
            "-",
            input_bytes=b"""### Standard input

**Capital:** Pipe City
**Population:** 1
**Area (km2):** 2
""",
        )

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            json.loads(result.stdout)["records"][0]["value"]["name"],
            "Standard input",
        )

    def test_extract_atomically_replaces_output_with_complete_json(self) -> None:
        markdown = b"""### Atomic

**Capital:** Safe City
**Population:** 3
**Area (km2):** 4
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            input_path = temp_root / "input.md"
            output_path = temp_root / "result.json"
            audit_path = temp_root / "replace-audit"
            input_path.write_bytes(markdown)
            output_path.write_text("previous", encoding="utf-8")
            environment = self.startup_hook_environment(
                temp_root,
                """import json
import os
from pathlib import Path

real_replace = os.replace
expected_destination = Path(os.environ["SITE2MD_TEST_OUTPUT"])
audit_path = Path(os.environ["SITE2MD_TEST_AUDIT"])

def observing_replace(source, destination):
    source_path = Path(source)
    destination_path = Path(destination)
    if destination_path == expected_destination:
        assert source_path.parent == destination_path.parent
        assert destination_path.read_text(encoding="utf-8") == "previous"
        payload = source_path.read_text(encoding="utf-8")
        json.loads(payload)
        audit_path.write_text(str(len(payload)), encoding="utf-8")
    return real_replace(source, destination)

os.replace = observing_replace
""",
            )
            environment.update(
                {
                    "SITE2MD_TEST_OUTPUT": str(output_path),
                    "SITE2MD_TEST_AUDIT": str(audit_path),
                }
            )

            result = self.run_site2md(
                "extract",
                "site2md.scrapethissite.countries",
                input_path,
                "--output",
                output_path,
                extra_environment=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b"")
            self.assertEqual(result.stderr, b"")
            payload = output_path.read_text(encoding="utf-8")
            self.assertEqual(audit_path.read_text(encoding="utf-8"), str(len(payload)))
            self.assertEqual(json.loads(payload)["records"][0]["value"]["name"], "Atomic")

    def test_extract_failures_preserve_output_and_leave_standard_output_empty(
        self,
    ) -> None:
        cases = {
            "extraction": (
                """from site2md import extraction

def fail_extraction(markdown, extractor_id):
    raise extraction.ExtractionError(
        "site2md.test.extraction_failed", "forced extraction failure"
    )

extraction.extract = fail_extraction
""",
                b"forced extraction failure",
            ),
            "validation": (
                """from site2md.extractors import countries
from site2md.extractors.v1 import Extraction, RecordCandidate

class InvalidExtractor:
    def extract(self, document):
        heading = document.sections[0].nodes[0]
        return Extraction(records=(RecordCandidate(
            value={
                "name": 7,
                "capital": "Invalid",
                "population": 1,
                "area_km2": 2,
            },
            provenance=(heading.span,),
        ),))

countries.create_extractor = lambda: InvalidExtractor()
""",
                b"record_schema_validation_failed",
            ),
            "serialization": (
                """from site2md import extraction

def fail_serialization(self):
    raise ValueError("forced serialization failure")

extraction.ExtractionResult.to_json = fail_serialization
""",
                b"forced serialization failure",
            ),
            "output": (
                """from site2md import main

def fail_replace(source, destination):
    raise OSError("forced output failure")

main.os.replace = fail_replace
""",
                b"forced output failure",
            ),
        }
        markdown = b"""### Failure stages

**Capital:** Safe City
**Population:** 3
**Area (km2):** 4
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            for stage, (startup_hook, expected_diagnostic) in cases.items():
                with self.subTest(stage=stage):
                    stage_root = temp_root / stage
                    stage_root.mkdir()
                    input_path = stage_root / "input.md"
                    output_path = stage_root / "result.json"
                    input_path.write_bytes(markdown)
                    output_path.write_text("previous", encoding="utf-8")
                    environment = self.startup_hook_environment(stage_root, startup_hook)

                    result = self.run_site2md(
                        "extract",
                        "site2md.scrapethissite.countries",
                        input_path,
                        "--output",
                        output_path,
                        extra_environment=environment,
                    )

                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, b"")
                    self.assertIn(expected_diagnostic, result.stderr)
                    self.assertNotIn(b"Traceback", result.stderr)
                    self.assertEqual(output_path.read_text(encoding="utf-8"), "previous")
                    self.assertEqual(list(stage_root.glob(".result.json.*.tmp")), [])

    def test_extract_reports_successful_warnings_on_standard_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            environment = self.startup_hook_environment(
                temp_root,
                """from site2md.extractors import countries
from site2md.extractors.v1 import Diagnostic, Extraction

real_create_extractor = countries.create_extractor

class WarningExtractor:
    def extract(self, document):
        extracted = real_create_extractor().extract(document)
        return Extraction(
            records=extracted.records,
            diagnostics=(Diagnostic(
                severity="warning",
                code="site2md.scrapethissite.countries.warning",
                message="command warning",
            ),),
        )

countries.create_extractor = lambda: WarningExtractor()
""",
            )

            result = self.run_site2md(
                "extract",
                "site2md.scrapethissite.countries",
                "-",
                input_bytes=b"""### Warning

**Capital:** Notice City
**Population:** 5
**Area (km2):** 6
""",
                extra_environment=environment,
            )

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(
            result.stderr,
            b"warning: site2md.scrapethissite.countries.warning: command warning\n",
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["diagnostics"][0]["message"], "command warning")

    def test_extract_uses_documented_exit_statuses_and_exact_ids(self) -> None:
        partial_id = self.run_site2md(
            "extract",
            "site2md.scrapethissite",
            "-",
            input_bytes=b"# No fuzzy extractor selection\n",
        )
        usage_error = self.run_site2md(
            "extract", "site2md.scrapethissite.countries"
        )

        self.assertEqual(partial_id.returncode, 1)
        self.assertEqual(partial_id.stdout, b"")
        self.assertIn(b"site2md.extractor_unknown", partial_id.stderr)
        self.assertNotIn(b"Traceback", partial_id.stderr)
        self.assertEqual(usage_error.returncode, 2)
        self.assertEqual(usage_error.stdout, b"")
        self.assertNotIn(b"Traceback", usage_error.stderr)

    def test_extract_usage_status_does_not_change_build_usage_status(self) -> None:
        result = self.run_site2md("build")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertNotIn(b"Traceback", result.stderr)

    def test_extract_performs_no_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            network_sentinel = temp_root / "network-access"
            environment = self.startup_hook_environment(
                temp_root,
                """import os
import socket
from pathlib import Path

network_sentinel = Path(os.environ["SITE2MD_TEST_NETWORK_SENTINEL"])

def reject_network(*args, **kwargs):
    network_sentinel.write_text("attempted", encoding="utf-8")
    raise AssertionError("network access attempted")

socket.create_connection = reject_network
""",
            )
            environment["SITE2MD_TEST_NETWORK_SENTINEL"] = str(network_sentinel)

            result = self.run_site2md(
                "extract",
                "site2md.scrapethissite.countries",
                "-",
                input_bytes=b"""### Offline Markdown

**Capital:** Local City
**Population:** 7
**Area (km2):** 8
""",
                extra_environment=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertFalse(network_sentinel.exists())

    def test_extract_discards_provider_output_on_success_and_failure(self) -> None:
        cases = {
            "success": (
                """import ctypes
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
        ctypes.CDLL(None).printf(b"provider native output\\n")
        return real_create_extractor().extract(document)

countries.create_extractor = lambda: NoisyExtractor()
""",
                0,
            ),
            "failure": (
                """import ctypes
import os
import sys
from site2md.extractors import countries

class NoisyExtractor:
    def extract(self, document):
        print("provider standard output")
        print("provider standard error", file=sys.stderr)
        os.write(1, b"provider descriptor output\\n")
        os.write(2, b"provider descriptor error\\n")
        ctypes.CDLL(None).printf(b"provider native output\\n")
        raise RuntimeError("forced provider failure")

countries.create_extractor = lambda: NoisyExtractor()
""",
                1,
            ),
        }
        markdown = b"""### Provider output

**Capital:** Quiet City
**Population:** 9
**Area (km2):** 10
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            for outcome, (startup_hook, expected_status) in cases.items():
                with self.subTest(outcome=outcome):
                    case_root = temp_root / outcome
                    case_root.mkdir()
                    environment = self.startup_hook_environment(case_root, startup_hook)

                    result = self.run_site2md(
                        "extract",
                        "site2md.scrapethissite.countries",
                        "-",
                        input_bytes=markdown,
                        extra_environment=environment,
                    )

                    self.assertEqual(result.returncode, expected_status)
                    self.assertNotIn(b"provider standard output", result.stdout)
                    self.assertNotIn(b"provider standard error", result.stderr)
                    self.assertNotIn(b"provider descriptor output", result.stdout)
                    self.assertNotIn(b"provider descriptor error", result.stderr)
                    self.assertNotIn(b"provider native output", result.stdout)
                    self.assertNotIn(b"Traceback", result.stderr)
                    if outcome == "success":
                        json.loads(result.stdout)
                    else:
                        self.assertEqual(result.stdout, b"")
                        self.assertIn(b"forced provider failure", result.stderr)

    @unittest.skipUnless(Path("/dev/full").exists(), "requires /dev/full")
    def test_extract_reports_standard_output_write_failures_with_status_one(
        self,
    ) -> None:
        with Path("/dev/full").open("wb", buffering=0) as full_device:
            result = subprocess.run(
                [
                    str(self.command),
                    "extract",
                    "site2md.scrapethissite.countries",
                    "-",
                ],
                check=False,
                input=b"""### Full device

**Capital:** Error City
**Population:** 11
**Area (km2):** 12
""",
                stdout=full_device,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn(b"could not write extraction result", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertNotIn(b"Exception ignored", result.stderr)


if __name__ == "__main__":
    unittest.main()
