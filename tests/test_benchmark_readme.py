"""Tests for the parts of the README that come from the benchmark results."""

from __future__ import annotations

import unittest

from benchmarks.catalog import Footnote
from benchmarks.readme import render_chart_block, render_readme, render_table
from tests.benchmark_test_support import make_crawl, make_result, make_tool

PAGE = "[Scrape This Site's countries page](https://www.scrapethissite.com/pages/simple/)"


class RenderChartBlockTests(unittest.TestCase):
    """Check the picture under the tagline and its caption."""

    def test_the_picture_follows_the_reader_theme_with_the_light_chart_as_the_fallback(self) -> None:
        block = render_chart_block()
        self.assertIn('<source media="(prefers-color-scheme: dark)" srcset="docs/benchmark-dark.svg">', block)
        self.assertIn('<source media="(prefers-color-scheme: light)" srcset="docs/benchmark-light.svg">', block)
        self.assertIn('src="docs/benchmark-light.svg"', block)

    def test_the_caption_describes_both_measures_and_links_to_the_details(self) -> None:
        self.assertIn(
            f"*Install size and time to extract the 250 countries from a local copy of {PAGE} as JSON, "
            "for each tool's smallest install that does it without a browser. "
            "The exception is site2md, whose row is its standalone executable. [Details](BENCHMARKS.md).*\n",
            render_chart_block(),
        )

    def test_the_alternative_text_names_both_measures(self) -> None:
        self.assertIn(
            'alt="Bar chart of each tool\'s install size and the time it takes to extract the countries."',
            render_chart_block(),
        )


class RenderTableTests(unittest.TestCase):
    """Check the README's table and its footnotes."""

    def test_a_row_shows_the_time_both_line_counts_and_the_install_size(self) -> None:
        results = {"site2md": make_result(mean=0.661, lines=54, crawl=make_crawl(counted=31), size_bytes=11_485_228)}
        self.assertEqual(
            render_table([make_tool("site2md")], results),
            "| Tool | Time | Lines (page) | Lines (crawl) | Install size |\n"
            "|---|---|---|---|---|\n"
            "| site2md | 661 ms ± 12 ms | 54 | 31 | 11.5 MB |\n",
        )

    def test_a_tool_without_a_crawler_gets_a_footnote_where_the_crawl_lines_would_be(self) -> None:
        table = render_table([make_tool("pandoc")], {"pandoc": make_result()})
        self.assertIn("| pandoc | 661 ms ± 12 ms | 54 | – [^1] | 11.5 MB |\n", table)
        self.assertTrue(table.endswith("\n[^1]: No crawler.\n"))

    def test_a_tool_with_a_crawl_solution_but_no_crawl_results_says_so(self) -> None:
        tools = [make_tool("scrapling", name="Scrapling", has_crawl_solution=True)]
        table = render_table(tools, {"scrapling": make_result()})
        self.assertIn("| – [^1] |", table)
        self.assertIn("[^1]: No crawl results yet.\n", table)

    def test_rows_follow_the_documented_tool_order_and_skip_tools_without_results(self) -> None:
        tools = [make_tool(name) for name in ("pandoc", "scrapling", "site2md")]
        results = {"pandoc": make_result(), "site2md": make_result()}
        rows = [line.split("|")[1].strip() for line in render_table(tools, results).splitlines()[2:4]]
        self.assertEqual(rows, ["site2md", "pandoc"])

    def test_a_tool_left_out_of_the_chart_still_has_its_row_next_to_the_executable_that_the_chart_shows(self) -> None:
        tools = [
            make_tool("pandoc"),
            make_tool("site2md-executable", name="site2md executable"),
            make_tool("site2md", in_chart=False),
        ]
        results = {tool.id: make_result() for tool in tools}
        rows = [line.split("|")[1].strip() for line in render_table(tools, results).splitlines()[2:5]]
        self.assertEqual(rows, ["site2md", "site2md executable", "pandoc"])

    def test_a_tool_added_later_gets_a_row_after_the_documented_tools(self) -> None:
        tools = [make_tool("newcomer", name="New Comer"), make_tool("pandoc")]
        results = {"newcomer": make_result(lines=7, crawl=make_crawl(counted=3)), "pandoc": make_result()}
        table = render_table(tools, results)
        self.assertLess(table.index("| pandoc |"), table.index("| New Comer | 661 ms ± 12 ms | 7 | 3 | 11.5 MB |"))

    def test_footnotes_from_the_tool_are_numbered_in_row_order(self) -> None:
        tools = [
            make_tool("site2md", Footnote("time", "Time note.")),
            make_tool("pandoc", Footnote("lines", "Lines note."), Footnote("size", "Size note.")),
        ]
        results = {"site2md": make_result(crawl=make_crawl(counted=31)), "pandoc": make_result(crawl=make_crawl(counted=7))}
        table = render_table(tools, results)
        self.assertIn("| site2md | 661 ms ± 12 ms [^1] | 54 | 31 | 11.5 MB |", table)
        self.assertIn("| pandoc | 661 ms ± 12 ms | 54 [^2] | 7 | 11.5 MB [^3] |", table)
        self.assertTrue(table.endswith("[^1]: Time note.\n[^2]: Lines note.\n[^3]: Size note.\n"))

    def test_rows_that_share_a_note_point_to_one_footnote(self) -> None:
        tools = [make_tool("markitdown"), make_tool("pandoc")]
        table = render_table(tools, {"markitdown": make_result(), "pandoc": make_result()})
        self.assertIn("| markitdown | 661 ms ± 12 ms | 54 | – [^1] |", table)
        self.assertIn("| pandoc | 661 ms ± 12 ms | 54 | – [^1] |", table)
        self.assertTrue(table.endswith("\n[^1]: No crawler.\n"))

    def test_lines_needed_only_for_the_local_server_get_a_footnote_that_names_them(self) -> None:
        results = {
            "scrapling": make_result(
                local_only=('allowed_domains = {"127.0.0.1:8000"}',),
                crawl=make_crawl(counted=9, local_only=('allowed_domains = {"127.0.0.1:8001"}',)),
            )
        }
        table = render_table([make_tool("scrapling")], results)
        self.assertIn("| 54 [^1] | 9 [^2] |", table)
        self.assertIn('`allowed_domains = {"127.0.0.1:8000"}`', table)
        self.assertIn('`allowed_domains = {"127.0.0.1:8001"}`', table)

    def test_a_tool_whose_output_does_not_match_says_the_chart_leaves_it_out(self) -> None:
        table = render_table([make_tool("scrapling")], {"scrapling": make_result(matches=False, crawl=make_crawl(counted=9))})
        self.assertIn("| scrapling | 661 ms ± 12 ms [^1] |", table)
        self.assertIn("[^1]: Its output doesn't match the reference, so the chart leaves it out.\n", table)

    def test_a_crawl_that_does_not_work_gets_a_footnote_on_its_line_count(self) -> None:
        results = {"scrapling": make_result(crawl=make_crawl(matches=False, counted=9))}
        table = render_table([make_tool("scrapling")], results)
        self.assertIn("| scrapling | 661 ms ± 12 ms | 54 | 9 [^1] |", table)
        self.assertTrue(
            table.endswith("\n[^1]: Its crawl output doesn't match the reference, or the crawl exited with an error.\n")
        )

    def test_a_crawl_that_matches_has_no_mismatch_footnote(self) -> None:
        table = render_table([make_tool("scrapling")], {"scrapling": make_result(crawl=make_crawl(counted=9))})
        self.assertEqual(table.count("["), 0)

    def test_the_tools_crawl_footnote_reaches_the_crawl_cell_and_its_gap_footnote_does_not(self) -> None:
        tool = make_tool("crawl4ai", Footnote("crawl", "Crawl note."), Footnote("gap", "Gap note."))
        table = render_table([tool], {"crawl4ai": make_result(crawl=make_crawl(counted=38))})
        self.assertIn("| crawl4ai | 661 ms ± 12 ms | 54 | 38 [^1] |", table)
        self.assertTrue(table.endswith("\n[^1]: Crawl note.\n"))

    def test_the_footnote_on_a_crawl_that_does_not_work_follows_the_tools_own_crawl_footnote(self) -> None:
        tool = make_tool("crawl4ai", Footnote("crawl", "Crawl note."))
        results = {"crawl4ai": make_result(crawl=make_crawl(matches=False, counted=38))}
        table = render_table([tool], results)
        self.assertIn("| 38 [^1] [^2] |", table)
        self.assertIn("[^1]: Crawl note.\n[^2]: Its crawl output doesn't match the reference", table)


class RenderReadmeTests(unittest.TestCase):
    """Check that the README changes only inside its two generated blocks."""

    DOCUMENT = (
        "# Title\n\nThe tagline.\n\n"
        "<!-- benchmarks:chart:start -->\nold chart\n<!-- benchmarks:chart:end -->\n\n"
        "Links.\n\n## Benchmarks\n\nHand-written introduction.\n\n"
        "<!-- benchmarks:table:start -->\nold table\n<!-- benchmarks:table:end -->\n\nThe rest.\n"
    )

    def test_only_the_text_between_the_markers_is_replaced(self) -> None:
        results = {"site2md": make_result(crawl=make_crawl(counted=31))}
        rendered = render_readme(self.DOCUMENT, [make_tool("site2md")], results)
        self.assertEqual(
            rendered,
            "# Title\n\nThe tagline.\n\n"
            "<!-- benchmarks:chart:start -->\n"
            "<picture>\n"
            '  <source media="(prefers-color-scheme: dark)" srcset="docs/benchmark-dark.svg">\n'
            '  <source media="(prefers-color-scheme: light)" srcset="docs/benchmark-light.svg">\n'
            '  <img alt="Bar chart of each tool\'s install size and the time it takes to extract the countries." '
            'src="docs/benchmark-light.svg">\n'
            "</picture>\n\n"
            f"*Install size and time to extract the 250 countries from a local copy of {PAGE} as JSON, "
            "for each tool's smallest install that does it without a browser. "
            "The exception is site2md, whose row is its standalone executable. [Details](BENCHMARKS.md).*\n"
            "<!-- benchmarks:chart:end -->\n\n"
            "Links.\n\n## Benchmarks\n\nHand-written introduction.\n\n"
            "<!-- benchmarks:table:start -->\n"
            "| Tool | Time | Lines (page) | Lines (crawl) | Install size |\n"
            "|---|---|---|---|---|\n"
            "| site2md | 661 ms ± 12 ms | 54 | 31 | 11.5 MB |\n"
            "<!-- benchmarks:table:end -->\n\nThe rest.\n",
        )

    def test_rendering_twice_changes_nothing_more(self) -> None:
        tools, results = [make_tool("site2md")], {"site2md": make_result()}
        once = render_readme(self.DOCUMENT, tools, results)
        self.assertEqual(render_readme(once, tools, results), once)

    def test_a_readme_without_the_markers_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "benchmarks:chart"):
            render_readme("# Title\n", [make_tool("site2md")], {"site2md": make_result()})


if __name__ == "__main__":
    unittest.main()
