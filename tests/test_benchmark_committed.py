"""Tests for the committed benchmark files, including those that later tickets add."""

from __future__ import annotations

import json
import re
import unittest
from collections.abc import Iterator

from benchmarks._types import JsonValue
from benchmarks.paths import BENCHMARKS_DOCUMENT, RESULTS_DIRECTORY
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


if __name__ == "__main__":
    unittest.main()
