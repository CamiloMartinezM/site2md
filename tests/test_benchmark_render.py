"""Tests for the files that `python -m benchmarks render` writes from the committed results."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from benchmarks.render import render_files


class RenderFilesTests(unittest.TestCase):
    """Check that one command keeps every generated file current."""

    def test_render_writes_the_documents_and_both_charts(self) -> None:
        names = {path.name for path in render_files()}
        self.assertEqual(names, {"BENCHMARKS.md", "README.md", "benchmark-light.svg", "benchmark-dark.svg"})

    def test_both_charts_are_well_formed_svg(self) -> None:
        charts = {path: text for path, text in render_files().items() if path.suffix == ".svg"}
        self.assertEqual(len(charts), 2)
        for path, text in charts.items():
            with self.subTest(file=path.name):
                self.assertEqual(ET.fromstring(text).tag, "{http://www.w3.org/2000/svg}svg")

    def test_the_committed_files_are_what_render_writes(self) -> None:
        # A stale file means `python -m benchmarks render` was not rerun after a merge or a new result.
        for path, rendered in render_files().items():
            with self.subTest(file=path.name):
                self.assertEqual(path.read_text(encoding="utf-8"), rendered)


if __name__ == "__main__":
    unittest.main()
