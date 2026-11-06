"""Tests for the benchmark's line-counting rules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from benchmarks.line_count import LineCount, count_lines, format_with_ruff


def _unformatted(source: str) -> str:
    """Stand in for the formatter when a test is not about formatting."""
    return source


class CountLinesTests(unittest.TestCase):
    """Check what counts as one line of a solution, per file type."""

    def test_python_counts_code_and_imports_but_not_blank_or_comment_lines(self) -> None:
        source = (
            "import json\n"
            "\n"
            "# a comment line\n"
            "records = json.loads('[]')  # a trailing comment does not add a line\n"
            "print(records)\n"
        )
        self.assertEqual(count_lines(source, "python", format_python=_unformatted), LineCount(3, ()))

    def test_python_is_counted_after_formatting(self) -> None:
        def split_statements(source: str) -> str:
            return source.replace("; ", "\n")

        count = count_lines("a = 1; b = 2; c = 3\n", "python", format_python=split_statements)
        self.assertEqual(count.counted, 3)

    def test_python_lines_needed_only_for_the_local_server_are_named_not_counted(self) -> None:
        source = (
            "fetch(url)\n"
            'allowed = {"127.0.0.1:8000"}  # 127.0.0.1-only\n'
            "# 127.0.0.1-only\n"
            "save()\n"
        )
        count = count_lines(source, "python", format_python=_unformatted)
        self.assertEqual(count, LineCount(2, ('allowed = {"127.0.0.1:8000"}',)))

    def test_json_is_counted_with_two_space_indentation(self) -> None:
        # The compact text is one line, the formatted text is the seven lines below.
        #   {
        #     "a": 1,
        #     "b": [
        #       1,
        #       2
        #     ]
        #   }
        count = count_lines('{"a": 1, "b": [1, 2]}', "json", format_python=_unformatted)
        self.assertEqual(count.counted, 7)

    def test_json_keeps_empty_containers_on_one_line(self) -> None:
        count = count_lines('{"a": {}, "b": []}', "json", format_python=_unformatted)
        self.assertEqual(count.counted, 4)

    def test_json_that_does_not_parse_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            count_lines('{"a": ', "json", format_python=_unformatted)

    def test_toml_counts_headers_and_keys_but_not_comments_or_blank_lines(self) -> None:
        text = (
            "# the build backend\n"
            "[build-system]\n"
            'requires = ["hatchling"]\n'
            "\n"
            'build-backend = "hatchling.build"\n'
        )
        self.assertEqual(count_lines(text, "toml", format_python=_unformatted).counted, 3)

    def test_toml_lines_needed_only_for_the_local_server_are_named_not_counted(self) -> None:
        text = 'name = "x"\nhost = "127.0.0.1"  # 127.0.0.1-only\n'
        self.assertEqual(
            count_lines(text, "toml", format_python=_unformatted),
            LineCount(1, ('host = "127.0.0.1"',)),
        )


class RuffFormattingTests(unittest.TestCase):
    """Check the real formatter when ruff is installed next to the running Python."""

    ruff = Path(sys.executable).with_name("ruff.exe" if sys.platform == "win32" else "ruff")

    @unittest.skipUnless(ruff.is_file(), "ruff is not installed in this environment")
    def test_long_statements_are_wrapped_at_88_columns(self) -> None:
        names = ", ".join(f"name_{index}" for index in range(12))
        source = f"values = [{names}]\n"
        self.assertGreater(len(source), 88)
        formatted = format_with_ruff(source, command=(str(self.ruff),))
        self.assertGreater(len(formatted.splitlines()), 1)
        self.assertTrue(all(len(line) <= 88 for line in formatted.splitlines()))


if __name__ == "__main__":
    unittest.main()
