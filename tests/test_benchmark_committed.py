"""Tests for the committed benchmark files, including those that later tickets add."""

from __future__ import annotations

import json
import re
import unittest
from collections.abc import Iterator

from benchmarks._types import JsonValue, TaskName
from benchmarks.catalog import count_solution, load_tool
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


class Site2mdToolsTests(unittest.TestCase):
    """Check what the two site2md entries promise, since CI cannot install either to see it."""

    ARCHIVE = "https://github.com/CamiloMartinezM/site2md/releases/download/v0.5.0/site2md-0.5.0-windows-x86_64.zip"
    ARCHIVE_SHA256 = "0b5a0d96149b633c1fcce8447258c211780dffee414e77672e967b7b8dd3e023"

    def setUp(self) -> None:
        self.package = load_tool(TOOLS_DIRECTORY / "site2md")
        self.executable = load_tool(TOOLS_DIRECTORY / "site2md-executable")

    def test_the_package_installs_the_0_5_0_tag(self) -> None:
        self.assertEqual(self.package.version, "0.5.0")
        self.assertEqual(
            self.package.requirements, ("site2md @ git+https://github.com/CamiloMartinezM/site2md@v0.5.0",)
        )

    def test_the_executable_is_pinned_to_the_0_5_0_archive_and_its_checksum(self) -> None:
        self.assertEqual(self.executable.name, "site2md executable")
        self.assertEqual(self.executable.version, "0.5.0")
        self.assertEqual(self.executable.requirements, ())
        (install,) = self.executable.install[:1]
        self.assertEqual(install[2:4], (self.ARCHIVE, self.ARCHIVE_SHA256))

    def test_the_executables_folder_is_put_on_the_path_where_the_archive_unpacks_it(self) -> None:
        self.assertEqual(self.executable.path, ("site2md-0.5.0-windows-x86_64",))

    def test_the_chart_shows_the_executable_and_leaves_the_package_to_the_tables(self) -> None:
        self.assertFalse(self.package.in_chart)
        self.assertTrue(self.executable.in_chart)

    def test_each_task_is_one_build_extract_step_in_both_entries(self) -> None:
        expected: dict[TaskName, str] = {
            "page": "site2md build {url} --no-progress --output page.md "
            "--extract benchmark.countries --entry-points-only --values-only",
            "crawl": "site2md build {url} --mode site --max-pages 20 --max-depth 2 --no-progress --output page.md "
            "--extract benchmark.countries --entry-points-only --values-only",
        }
        for tool in (self.package, self.executable):
            for task, command in expected.items():
                with self.subTest(tool=tool.id, task=task):
                    self.assertEqual([step.run for step in tool.tasks[task].steps], [command])
                    self.assertEqual([step.file for step in tool.tasks[task].steps], [None])

    def test_both_entries_count_the_same_extractor_files_and_so_the_same_lines(self) -> None:
        for task in ("page", "crawl"):
            with self.subTest(task=task):
                # The executable names the package's Extractor files by a path through the sibling folder.
                self.assertEqual(
                    [(self.executable.directory / name).resolve() for name in self.executable.tasks[task].files],
                    [(self.package.directory / name).resolve() for name in self.package.tasks[task].files],
                )
                self.assertEqual(
                    count_solution(self.executable, task, format_python=_unformatted),
                    count_solution(self.package, task, format_python=_unformatted),
                )

    def test_the_executable_finds_the_extractor_in_a_folder_installed_without_dependencies(self) -> None:
        (command,) = self.executable.setup
        self.assertIn("--no-deps", command)
        folder = command[command.index("--target") + 1]
        self.assertEqual((self.executable.env or {}).get("SITE2MD_PROVIDER_PATH"), folder)

    def test_the_package_never_reads_the_provider_path(self) -> None:
        self.assertNotIn("SITE2MD_PROVIDER_PATH", self.package.env or {})

    def test_the_executables_package_count_is_explained(self) -> None:
        notes = [note.text for note in self.executable.footnotes if note.column == "size"]
        self.assertTrue(any("package count reads 0" in note for note in notes), notes)

    def test_both_solutions_say_which_row_the_chart_shows(self) -> None:
        self.assertIn("chart", self.package.solution)
        self.assertIn("chart", self.executable.solution)


def _unformatted(source: str) -> str:
    """Stand in for the formatter, since these files are already formatted."""
    return source


if __name__ == "__main__":
    unittest.main()
