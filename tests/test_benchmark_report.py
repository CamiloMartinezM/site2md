"""Tests for rendering the benchmark results into BENCHMARKS.md."""

from __future__ import annotations

import unittest

from benchmarks.catalog import Footnote
from benchmarks.report import (
    render_generated,
    render_results,
    splice_generated,
)
from tests.benchmark_test_support import make_crawl, make_result, make_tool


class RenderResultsTests(unittest.TestCase):
    """Check the results table and its footnotes."""

    def test_a_row_shows_the_tool_its_version_and_every_measure(self) -> None:
        table = render_results([make_tool("site2md")], {"site2md": make_result()})
        self.assertIn(
            "| Tool | Version | Output matches | Time | Lines | Install size | Packages "
            "| Crawl output matches | Extra pages | Shortest gap | Crawl lines |",
            table,
        )
        self.assertIn("| site2md | 0.4.3 | yes | 661 ms ± 12 ms | 54 | 11.5 MB | 20 |", table)

    def test_times_of_a_second_or_more_are_shown_in_seconds(self) -> None:
        table = render_results([make_tool("crawl4ai")], {"crawl4ai": make_result(mean=1.034, stddev=0.021)})
        self.assertIn("| 1.03 s ± 0.02 s |", table)

    def test_a_solution_that_does_not_match_is_marked(self) -> None:
        table = render_results([make_tool("site2md")], {"site2md": make_result(matches=False)})
        self.assertIn("| site2md | 0.4.3 | no |", table)

    def test_rows_follow_the_documented_tool_order_then_other_tools_by_name(self) -> None:
        tools = [make_tool(name) for name in ("pandoc", "zeta", "site2md", "alpha", "crawl4ai")]
        results = {tool.id: make_result() for tool in tools}
        rows = [line.split("|")[1].strip() for line in render_results(tools, results).splitlines()[2:]]
        self.assertEqual(rows[:3], ["site2md", "crawl4ai", "pandoc"])
        self.assertEqual(rows[3:5], ["alpha", "zeta"])

    def test_a_tool_without_results_has_no_row(self) -> None:
        table = render_results([make_tool("site2md"), make_tool("scrapling")], {"site2md": make_result()})
        self.assertNotIn("scrapling", table)

    def test_footnotes_are_numbered_in_table_order_and_listed_under_the_table(self) -> None:
        tools = [
            make_tool("site2md", Footnote("time", "Time note.")),
            make_tool("crawl4ai", Footnote("lines", "Lines note."), Footnote("size", "Size note.")),
        ]
        results = {"site2md": make_result(), "crawl4ai": make_result(lines=7)}
        table = render_results(tools, results)
        self.assertIn("| 661 ms ± 12 ms [^1] | 54 |", table)
        self.assertIn("| 7 [^2] | 11.5 MB [^3] |", table)
        self.assertTrue(table.endswith("\n[^1]: Time note.\n[^2]: Lines note.\n[^3]: Size note.\n"))

    def test_lines_needed_only_for_the_local_server_get_a_footnote_that_names_them(self) -> None:
        results = {"scrapling": make_result(local_only=('allowed_domains = {"127.0.0.1:8000"}',))}
        table = render_results([make_tool("scrapling")], results)
        self.assertIn("| 54 [^1] |", table)
        self.assertIn(
            '[^1]: Not counted: `allowed_domains = {"127.0.0.1:8000"}`. The harness passes the local '
            "server's 127.0.0.1 URL on the command line, and this code only reads it. "
            "A solution for the live site writes the URL inline.",
            table,
        )


class RenderCrawlColumnsTests(unittest.TestCase):
    """Check the crawl columns: the output check, the extra pages, the shortest gap and the lines."""

    def test_a_row_shows_whether_the_crawl_matched_how_many_extra_pages_and_the_gap(self) -> None:
        table = render_results([make_tool("site2md")], {"site2md": make_result(crawl=make_crawl())})
        self.assertIn("| 20 | yes | 0 | 1.004 s | 33 |", table)

    def test_a_crawl_that_does_not_match_is_marked(self) -> None:
        table = render_results([make_tool("site2md")], {"site2md": make_result(crawl=make_crawl(matches=False))})
        self.assertIn("| 20 | no | 0 |", table)

    def test_extra_pages_are_counted(self) -> None:
        crawl = make_crawl(extra_pages=("/", "/level-3/page-1.html"))
        table = render_results([make_tool("crawl4ai")], {"crawl4ai": make_result(crawl=crawl)})
        self.assertIn("| yes | 2 | 1.004 s |", table)

    def test_a_crawl_with_fewer_than_two_child_requests_has_no_gap(self) -> None:
        table = render_results([make_tool("site2md")], {"site2md": make_result(crawl=make_crawl(shortest_gap=None))})
        self.assertIn("| yes | 0 | n/a | 33 |", table)

    def test_a_tool_without_a_crawl_result_shows_no_crawler_in_every_crawl_column(self) -> None:
        table = render_results([make_tool("markitdown")], {"markitdown": make_result()})
        self.assertIn("| 20 | no crawler | no crawler | no crawler | no crawler |", table)

    def test_a_crawl_footnote_explains_the_crawl_output_cell(self) -> None:
        tool = make_tool("scrapling", Footnote("crawl", "Crawl note."))
        table = render_results([tool], {"scrapling": make_result(crawl=make_crawl())})
        self.assertIn("| yes [^1] | 0 |", table)
        self.assertIn("[^1]: Crawl note.", table)

    def test_a_gap_footnote_explains_the_shortest_gap_cell(self) -> None:
        tool = make_tool("site2md", Footnote("gap", "Gap note."))
        table = render_results([tool], {"site2md": make_result(crawl=make_crawl())})
        self.assertIn("| 0 | 1.004 s [^1] | 33 |", table)
        self.assertIn("[^1]: Gap note.", table)

    def test_crawl_footnotes_are_numbered_after_the_footnotes_of_the_columns_before_them(self) -> None:
        tool = make_tool("scrapling", Footnote("crawl", "Crawl note."), Footnote("time", "Time note."))
        table = render_results([tool], {"scrapling": make_result(crawl=make_crawl())})
        self.assertIn("| 661 ms ± 12 ms [^1] |", table)
        self.assertIn("| yes [^2] |", table)
        self.assertTrue(table.endswith("[^1]: Time note.\n[^2]: Crawl note.\n"))

    def test_crawl_lines_needed_only_for_the_local_server_get_a_footnote_that_names_them(self) -> None:
        crawl = make_crawl(local_only=('allowed_domains = {"127.0.0.1:8000"}',))
        table = render_results([make_tool("scrapling")], {"scrapling": make_result(crawl=crawl)})
        self.assertIn("| 33 [^1] |", table)
        self.assertIn('`allowed_domains = {"127.0.0.1:8000"}`', table)


class RenderGeneratedTests(unittest.TestCase):
    """Check the machine facts and the page copy facts around the table."""

    def test_the_machine_section_lists_only_the_os_and_software_versions(self) -> None:
        generated = render_generated([make_tool("site2md")], {"site2md": make_result()}, page_date="2026-11-06", page_sha256="ab" * 32)
        for fact in ("Windows 11", "3.12.14", "2.0.0", "0.12.21", "0.17.4"):
            self.assertIn(fact, generated)

    def test_the_page_copy_section_names_its_download_date_and_hash(self) -> None:
        generated = render_generated([make_tool("site2md")], {"site2md": make_result()}, page_date="2026-11-05", page_sha256="ab" * 32)
        self.assertIn("2026-11-05", generated)
        self.assertIn("ab" * 32, generated)

    def test_differing_values_across_tools_are_all_listed(self) -> None:
        results = {"site2md": make_result(), "crawl4ai": make_result()}
        results["crawl4ai"]["environment"]["python"] = "3.12.13"
        generated = render_generated([make_tool("site2md"), make_tool("crawl4ai")], results, page_date="d", page_sha256="s")
        self.assertIn("3.12.13, 3.12.14", generated)

    def test_each_tool_with_results_has_its_solution_described(self) -> None:
        generated = render_generated(
            [make_tool("site2md"), make_tool("scrapling")], {"site2md": make_result()}, page_date="d", page_sha256="s"
        )
        self.assertIn("- **site2md**: The solution of site2md.\n", generated)
        self.assertNotIn("scrapling", generated)

    def test_the_version_table_links_each_raw_results_file(self) -> None:
        generated = render_generated([make_tool("site2md")], {"site2md": make_result()}, page_date="d", page_sha256="s")
        self.assertIn("| site2md | 0.4.3 | 2026-11-06 | [site2md.json](benchmarks/results/site2md.json) |", generated)


class SpliceGeneratedTests(unittest.TestCase):
    """Check that only the generated block of the document is replaced."""

    START = "<!-- benchmarks:generated:start -->"
    END = "<!-- benchmarks:generated:end -->"

    def test_only_the_text_between_the_markers_is_replaced(self) -> None:
        document = f"# Title\n\nHand-written.\n\n{self.START}\nold\n{self.END}\n\nMore hand-written text.\n"
        spliced = splice_generated(document, "new\nlines\n")
        self.assertEqual(
            spliced,
            f"# Title\n\nHand-written.\n\n{self.START}\nnew\nlines\n{self.END}\n\nMore hand-written text.\n",
        )

    def test_splicing_twice_changes_nothing_more(self) -> None:
        document = f"{self.START}\nold\n{self.END}\n"
        once = splice_generated(document, "new\n")
        self.assertEqual(splice_generated(once, "new\n"), once)

    def test_a_document_without_markers_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "benchmarks:generated"):
            splice_generated("# Title\n", "new\n")


if __name__ == "__main__":
    unittest.main()
