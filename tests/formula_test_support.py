"""Shared support for the tests of TeX formulas: pages built through the installed command, and extraction."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from site2md.extraction import extract
from site2md.extractors.v1 import ConvertedDocument, Extraction, RecordCandidate
from tests.cli_test_support import InstalledCliTestCase, RecordingServer

PAGE_START = "<html><body><main>\n"
PAGE_END = "</main></body></html>\n"
# A doctype inside the content makes the converter parse the content a second time (ADR 0005).
SECOND_PARSE_MARKER = "<!DOCTYPE html>\n"


class FormulaObserver:
    """Capture the converted document that the Extractor is given."""

    def __init__(self) -> None:
        self.documents: list[ConvertedDocument] = []

    def extract(self, document: ConvertedDocument) -> Extraction:
        """Return one schema-valid record, so that the extraction succeeds."""
        self.documents.append(document)
        return Extraction(
            records=(
                RecordCandidate(
                    value={
                        "name": "Formulas",
                        "capital": None,
                        "population": 1,
                        "area_km2": 2.0,
                    },
                    provenance=(document.sections[0].nodes[0].span,),
                ),
            )
        )


def read_document(markdown: str) -> ConvertedDocument:
    """Return the document that an Extractor reads from this Markdown."""
    observer = FormulaObserver()
    with patch("site2md.extractors.countries.create_extractor", return_value=observer):
        extract(markdown, "site2md.scrapethissite.countries")
    return observer.documents[0]


class PageBuildTestCase(InstalledCliTestCase):
    """Build one page through the installed command, from a local folder or from a remote URL."""

    def build_local(self, page: str) -> str:
        """Build a folder with one page, and return the Markdown that it writes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "pages"
            root.mkdir()
            (root / "index.html").write_text(page, encoding="utf-8")
            output = Path(temp_dir) / "out.md"

            result = self.run_site2md("build", root, "--output", output, "--no-progress")

            self.assertEqual(result.returncode, 0, result.stderr)
            return output.read_text(encoding="utf-8")

    def build_remote(self, page: str) -> tuple[str, str]:
        """Build one remote page, and return its source URL and the Markdown that it writes."""
        routes = {"/page": (200, {"Content-Type": "text/html; charset=utf-8"}, page.encode())}
        with (
            RecordingServer(routes) as server,
            tempfile.TemporaryDirectory() as temp_dir,
        ):
            output = Path(temp_dir) / "out.md"

            result = self.run_site2md(
                "build", f"{server.origin}/page", "--output", output, "--no-progress"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            return f"{server.origin}/page", output.read_text(encoding="utf-8")
