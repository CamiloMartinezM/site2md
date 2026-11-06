"""Tests for the rule that picks the chart's measure and for the SVG charts."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from benchmarks._types import ChartMeasure
from benchmarks.chart import choose_measure, render_chart
from tests.benchmark_test_support import make_result, make_tool

SVG = "{http://www.w3.org/2000/svg}"


class ChooseMeasureTests(unittest.TestCase):
    """Check the rule from #40: time only if site2md is the fastest tool whose output matches."""

    def test_time_when_site2md_has_the_lowest_mean(self) -> None:
        results = {
            "site2md": make_result(mean=0.5),
            "scrapling": make_result(mean=0.6),
            "crawl4ai": make_result(mean=1.0),
        }
        self.assertEqual(choose_measure(results), "time")

    def test_size_when_another_tool_whose_output_matches_is_faster(self) -> None:
        results = {"site2md": make_result(mean=0.66), "scrapling": make_result(mean=0.48)}
        self.assertEqual(choose_measure(results), "size")

    def test_a_faster_tool_whose_output_does_not_match_is_ignored(self) -> None:
        results = {
            "site2md": make_result(mean=0.66),
            "scrapling": make_result(mean=0.48, matches=False),
        }
        self.assertEqual(choose_measure(results), "time")

    def test_size_when_site2md_own_output_does_not_match(self) -> None:
        results = {"site2md": make_result(mean=0.1, matches=False), "pandoc": make_result(mean=0.9)}
        self.assertEqual(choose_measure(results), "size")

    def test_size_when_there_are_no_results_for_site2md(self) -> None:
        self.assertEqual(choose_measure({"pandoc": make_result()}), "size")


class RenderChartTests(unittest.TestCase):
    """Check the SVG that the README shows, through the XML it contains."""

    def test_site2md_alone_renders_one_labelled_bar_for_each_measure(self) -> None:
        tools = [make_tool("site2md")]
        results = {"site2md": make_result(mean=0.661, size_bytes=11_485_228)}
        measures: list[tuple[ChartMeasure, str]] = [("time", "0.66s"), ("size", "11.5 MB")]
        for measure, label in measures:
            with self.subTest(measure=measure):
                chart = render_chart(tools, results, measure, "light")
                root = ET.fromstring(chart)
                self.assertEqual(root.tag, f"{SVG}svg")
                self.assertEqual(len(list(root.iter(f"{SVG}rect"))), 1)
                self.assertIn("site2md", _texts(chart))
                self.assertIn(label, _texts(chart))

    def test_bars_run_from_the_smallest_value_and_their_widths_follow_the_values(self) -> None:
        tools = [make_tool("alpha"), make_tool("beta"), make_tool("gamma")]
        results = {
            "alpha": make_result(size_bytes=200_000_000),
            "beta": make_result(size_bytes=50_000_000),
            "gamma": make_result(size_bytes=100_000_000),
        }
        chart = render_chart(tools, results, "size", "light")
        widths = [float(bar.get("width", "")) for bar in ET.fromstring(chart).iter(f"{SVG}rect")]
        self.assertEqual(_names(chart), ["beta", "gamma", "alpha"])
        self.assertAlmostEqual(widths[1] / widths[0], 2, places=1)
        self.assertAlmostEqual(widths[2] / widths[0], 4, places=1)

    def test_a_tool_whose_output_does_not_match_has_no_bar(self) -> None:
        tools = [make_tool("site2md"), make_tool("scrapling")]
        results = {"site2md": make_result(), "scrapling": make_result(matches=False)}
        chart = render_chart(tools, results, "time", "light")
        self.assertNotIn("scrapling", _texts(chart))
        self.assertEqual(len(list(ET.fromstring(chart).iter(f"{SVG}rect"))), 1)

    def test_a_tool_added_later_gets_a_bar_under_its_display_name(self) -> None:
        tools = [make_tool("site2md"), make_tool("newcomer", name="New Comer")]
        results = {"site2md": make_result(), "newcomer": make_result(size_bytes=94_800_000)}
        texts = _texts(render_chart(tools, results, "size", "light"))
        self.assertIn("New Comer", texts)
        self.assertIn("94.8 MB", texts)

    def test_a_tool_that_has_no_results_has_no_bar(self) -> None:
        chart = render_chart([make_tool("site2md"), make_tool("pandoc")], {"site2md": make_result()}, "size", "light")
        self.assertNotIn("pandoc", _texts(chart))

    def test_a_chart_without_any_matching_tool_is_still_valid_svg(self) -> None:
        chart = render_chart([make_tool("site2md")], {"site2md": make_result(matches=False)}, "time", "dark")
        self.assertEqual(ET.fromstring(chart).tag, f"{SVG}svg")

    def test_names_are_escaped_so_that_the_svg_stays_valid(self) -> None:
        tools = [make_tool("site2md", name="Fast & <Loose>")]
        self.assertIn("Fast & <Loose>", _texts(render_chart(tools, {"site2md": make_result()}, "time", "light")))

    def test_the_themes_set_the_text_colour_and_keep_the_bar_colour(self) -> None:
        tools, results = [make_tool("site2md")], {"site2md": make_result()}
        light = render_chart(tools, results, "time", "light")
        dark = render_chart(tools, results, "time", "dark")
        self.assertIn('fill="#333333"', light)
        self.assertIn('fill="#C9D1D9"', dark)
        self.assertEqual(light.count('fill="#0969DA"'), dark.count('fill="#0969DA"'))

    def test_the_time_axis_marks_round_values(self) -> None:
        results = {"site2md": make_result(mean=1.78)}
        texts = _texts(render_chart([make_tool("site2md")], results, "time", "light"))
        for tick in ("0s", "0.5s", "1s", "1.5s", "2s"):
            self.assertIn(tick, texts)

    def test_the_size_axis_marks_round_values(self) -> None:
        results = {"site2md": make_result(size_bytes=554_800_000)}
        texts = _texts(render_chart([make_tool("site2md")], results, "size", "light"))
        for tick in ("0 MB", "200 MB", "400 MB", "600 MB"):
            self.assertIn(tick, texts)


def _texts(chart: str) -> list[str]:
    """Return the text of every label in an SVG chart, in document order."""
    return [element.text or "" for element in ET.fromstring(chart).iter(f"{SVG}text")]


def _names(chart: str) -> list[str]:
    """Return the tool names on the left of the bars, from the top down."""
    labels = ET.fromstring(chart).iter(f"{SVG}text")
    return [label.text or "" for label in labels if label.get("text-anchor") == "end"]


if __name__ == "__main__":
    unittest.main()
