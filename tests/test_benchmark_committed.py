"""Tests for the committed benchmark files, including those that later tickets add."""

from __future__ import annotations

import json
import re
import unittest
from collections.abc import Iterator

from benchmarks._types import JsonValue
from benchmarks.catalog import load_tool
from benchmarks.paths import RESULTS_DIRECTORY, TOOLS_DIRECTORY


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

    @staticmethod
    def _offenders(result: dict[str, JsonValue]) -> list[str]:
        """Return the strings of a results file that name a path or a machine."""
        absolute_path = re.compile(r"^[A-Za-z]:[\\/]|^/|\\\\|/Users/|/home/|\\Users\\")
        # The pages that a crawl fetched are paths on the fixture server, so they start with a slash.
        crawl = result.get("crawl")
        pages = crawl.get("extra_pages") if isinstance(crawl, dict) else None
        server_paths = {str(page) for page in pages} if isinstance(pages, list) else set()
        texts = [text for text in CommittedBenchmarksTests._strings(result) if text not in server_paths]
        return [
            *(text for text in texts if absolute_path.search(text)),
            *(page for page in sorted(server_paths) if not re.fullmatch(r"/[\w./-]*", page)),
        ]

    def test_a_crawled_page_is_a_server_path_but_a_file_path_is_still_found(self) -> None:
        self.assertEqual(self._offenders({"crawl": {"extra_pages": ["/", "/level-3/page-1.html"]}}), [])
        file_path = "C:\\Users\\me\\page.html"
        self.assertEqual(self._offenders({"crawl": {"extra_pages": [file_path]}}), [file_path])
        self.assertEqual(self._offenders({"install": {"packages": {file_path: "1"}}}), [file_path])

    def test_committed_results_name_neither_a_path_nor_a_machine(self) -> None:
        paths = sorted(RESULTS_DIRECTORY.glob("*.json"))
        self.assertTrue(paths, "no results are committed")
        for path in paths:
            with self.subTest(file=path.name):
                self.assertEqual(self._offenders(json.loads(path.read_text(encoding="utf-8"))), [])
            environment = json.loads(path.read_text(encoding="utf-8"))["environment"]
            with self.subTest(file=path.name, part="environment keys"):
                self.assertEqual(sorted(environment), ["hyperfine", "os", "python", "ruff", "uv"])


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
