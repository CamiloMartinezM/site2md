"""Tests for the committed benchmark files, including those that later tickets add."""

from __future__ import annotations

import json
import re
import unittest
from collections.abc import Iterator

from benchmarks._types import JsonValue
from benchmarks.catalog import load_tool
from benchmarks.paths import BENCHMARKS_DOCUMENT, RESULTS_DIRECTORY, TOOLS_DIRECTORY
from benchmarks.report import render_document


class CommittedBenchmarksTests(unittest.TestCase):
    """Check the committed results and BENCHMARKS.md."""

    @staticmethod
    def _strings(value: JsonValue) -> Iterator[str]:
        """Yield every string, key or value, in a parsed JSON document."""
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from CommittedBenchmarksTests._strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from CommittedBenchmarksTests._strings(item)

    def test_committed_results_name_neither_a_path_nor_a_machine(self) -> None:
        paths = sorted(RESULTS_DIRECTORY.glob("*.json"))
        self.assertTrue(paths, "no results are committed")
        absolute_path = re.compile(r"^[A-Za-z]:[\\/]|^/|\\\\|/Users/|/home/|\\Users\\")
        for path in paths:
            for text in self._strings(json.loads(path.read_text(encoding="utf-8"))):
                with self.subTest(file=path.name, text=text):
                    self.assertIsNone(absolute_path.search(text))
            environment = json.loads(path.read_text(encoding="utf-8"))["environment"]
            with self.subTest(file=path.name, part="environment keys"):
                self.assertEqual(sorted(environment), ["hyperfine", "os", "python", "ruff", "uv"])

    def test_benchmarks_document_shows_the_committed_results(self) -> None:
        # A stale document means `python -m benchmarks render` was not rerun after a merge.
        document = BENCHMARKS_DOCUMENT.read_text(encoding="utf-8")
        self.assertEqual(render_document(document), document)


class Crawl4aiToolTests(unittest.TestCase):
    """Check what the crawl4ai definition promises, since CI cannot install crawl4ai to see it."""

    def setUp(self) -> None:
        self.tool = load_tool(TOOLS_DIRECTORY / "crawl4ai")

    def test_it_is_pinned_to_one_exact_version(self) -> None:
        self.assertEqual(self.tool.requirements, ("crawl4ai==0.9.5",))

    def test_its_home_folder_is_inside_the_cache(self) -> None:
        # Unset, crawl4ai writes its logs and robots.txt cache to the user's home folder.
        home = (self.tool.env or {}).get("CRAWL4_AI_BASE_DIRECTORY", "")
        self.assertTrue(home.startswith("{cache}/"), home)

    def test_the_command_line_footnote_explains_why_its_one_line_is_not_counted(self) -> None:
        notes = [note.text for note in self.tool.footnotes if note.column == "lines"]
        self.assertTrue(any("crwl" in note and "browser" in note for note in notes), notes)


if __name__ == "__main__":
    unittest.main()
