"""Tests for the catalog of benchmark tool definitions and counting their solutions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.catalog import count_solution, load_tool, tool_ids
from benchmarks.line_count import LineCount
from benchmarks.paths import TOOLS_DIRECTORY


def _unformatted(source: str) -> str:
    """Stand in for the formatter, since these files are already formatted."""
    return source


class ToolDirectoryTestCase(unittest.TestCase):
    """Provide a temporary tool folder that tests fill with files."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "example"
        self.directory.mkdir()

    def write(self, relative_path: str, contents: str) -> None:
        """Write one file of the tool folder."""
        path = self.directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def write_definition(self, **overrides: object) -> None:
        """Write tool.json with a minimal valid definition plus overrides."""
        definition: dict[str, object] = {
            "name": "Example",
            "version": "1.0",
            "solution": "Fetch the page.",
            "requirements": ["example==1.0"],
            "page": {"steps": [{"run": "example {url}"}]},
        }
        definition.update(overrides)
        self.write("tool.json", json.dumps(definition))


class CountSolutionTests(ToolDirectoryTestCase):
    """Check that a solution's count covers its commands, step files and extra files."""

    def test_commands_count_one_line_each_and_files_count_their_own_lines(self) -> None:
        self.write("records.py", "import json\n\nprint(json.dumps([]))\n")
        self.write("extractor/manifest.json", '{"id": "x"}')
        self.write("extractor/pyproject.toml", '[project]\nname = "x"\n')
        self.write_definition(
            page={
                "steps": [
                    {"run": "example build {url}"},
                    {"run": "example extract"},
                    {"run": "python records.py", "file": "records.py"},
                ],
                "files": ["extractor/manifest.json", "extractor/pyproject.toml"],
            }
        )
        tool = load_tool(self.directory)
        # 2 commands + 2 Python lines + 3 JSON lines ({, "id", }) + 2 TOML lines
        self.assertEqual(count_solution(tool, "page", format_python=_unformatted), LineCount(9, ()))

    def test_a_command_needed_only_for_the_local_server_is_named_not_counted(self) -> None:
        self.write_definition(
            page={
                "steps": [
                    {"run": "example allow 127.0.0.1:{port}", "local_only": True},
                    {"run": "example fetch {url}"},
                ]
            }
        )
        tool = load_tool(self.directory)
        self.assertEqual(
            count_solution(tool, "page", format_python=_unformatted),
            LineCount(1, ("example allow 127.0.0.1:{port}",)),
        )

    def test_local_server_lines_inside_a_file_are_named_not_counted(self) -> None:
        self.write("solution.py", 'fetch(url)\nallow("127.0.0.1")  # 127.0.0.1-only\n')
        self.write_definition(page={"steps": [{"run": "python solution.py {url}", "file": "solution.py"}]})
        tool = load_tool(self.directory)
        self.assertEqual(
            count_solution(tool, "page", format_python=_unformatted),
            LineCount(1, ('allow("127.0.0.1")',)),
        )

    def test_a_file_type_without_counting_rules_is_rejected(self) -> None:
        self.write("notes.md", "text\n")
        self.write_definition(page={"steps": [{"run": "example {url}"}], "files": ["notes.md"]})
        with self.assertRaisesRegex(ValueError, "notes.md"):
            count_solution(load_tool(self.directory), "page", format_python=_unformatted)


class LoadToolTests(ToolDirectoryTestCase):
    """Check that a tool definition is validated when it is loaded."""

    def test_a_minimal_definition_loads_with_its_defaults(self) -> None:
        self.write_definition()
        tool = load_tool(self.directory)
        self.assertEqual((tool.id, tool.name, tool.version), ("example", "Example", "1.0"))
        self.assertEqual(tool.solution, "Fetch the page.")
        self.assertEqual(tool.requirements, ("example==1.0",))
        self.assertEqual(tool.footnotes, ())

    def test_a_missing_key_is_named(self) -> None:
        self.write("tool.json", json.dumps({"name": "Example"}))
        with self.assertRaisesRegex(ValueError, "version"):
            load_tool(self.directory)

    def test_an_unknown_key_is_named(self) -> None:
        self.write_definition(requirments=["typo"])
        with self.assertRaisesRegex(ValueError, "requirments"):
            load_tool(self.directory)

    def test_a_listed_file_that_does_not_exist_is_named(self) -> None:
        self.write_definition(page={"steps": [{"run": "python gone.py", "file": "gone.py"}]})
        with self.assertRaisesRegex(ValueError, "gone.py"):
            load_tool(self.directory)

    def test_footnotes_name_the_column_they_explain(self) -> None:
        self.write_definition(footnotes=[{"column": "lines", "text": "One line is local."}])
        tool = load_tool(self.directory)
        self.assertEqual((tool.footnotes[0].column, tool.footnotes[0].text), ("lines", "One line is local."))

    def test_a_footnote_for_an_unknown_column_is_rejected(self) -> None:
        self.write_definition(footnotes=[{"column": "colour", "text": "?"}])
        with self.assertRaisesRegex(ValueError, "colour"):
            load_tool(self.directory)


class CommittedToolsTests(unittest.TestCase):
    """Check every tool folder in the repository, including those later tickets add."""

    def test_every_committed_tool_definition_is_valid(self) -> None:
        ids = tool_ids()
        self.assertIn("site2md", ids)
        for tool_id in ids:
            with self.subTest(tool=tool_id):
                tool = load_tool(TOOLS_DIRECTORY / tool_id)
                self.assertEqual(tool.id, tool_id)
                count_solution(tool, "page", format_python=_unformatted)


if __name__ == "__main__":
    unittest.main()
