"""Tests for the SVG charts that the README shows."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from benchmarks._types import ChartTheme
from benchmarks.chart import render_chart
from tests.benchmark_test_support import make_result, make_tool

SVG = "{http://www.w3.org/2000/svg}"
# Blue for install size and orange for time. The dataviz skill's validator passes each pair on GitHub's
# page colours (CVD ΔE 25 or more, contrast 3:1 or more): light on #ffffff, dark on #0d1117.
SIZE_COLOURS: dict[ChartTheme, str] = {"light": "#2A78D6", "dark": "#3987E5"}
TIME_COLOURS: dict[ChartTheme, str] = {"light": "#EB6834", "dark": "#D95926"}
THEMES: tuple[ChartTheme, ...] = ("light", "dark")


class RenderChartTests(unittest.TestCase):
    """Check the SVG that the README shows, through the XML it contains."""

    def test_each_tool_has_two_bars_labelled_with_its_install_size_and_its_time(self) -> None:
        tools = [make_tool("site2md"), make_tool("scrapling", name="Scrapling")]
        results = {
            "site2md": make_result(mean=0.870, size_bytes=11_485_228),
            "scrapling": make_result(mean=0.338, size_bytes=242_900_000),
        }
        rows = _rows(render_chart(tools, results, "light"))
        self.assertEqual([_name(row) for row in rows], ["site2md", "Scrapling"])
        self.assertEqual([_values(row) for row in rows], [["11.5 MB", "870 ms"], ["242.9 MB", "338 ms"]])
        self.assertEqual([len(_bars(row)) for row in rows], [2, 2])

    def test_a_time_of_a_second_or_more_is_labelled_in_seconds(self) -> None:
        rows = _rows(render_chart([make_tool("crawl4ai")], {"crawl4ai": make_result(mean=1.04)}, "light"))
        self.assertEqual(_values(rows[0])[1], "1.04 s")

    def test_a_legend_names_both_measures_in_the_colours_of_their_bars(self) -> None:
        chart = render_chart([make_tool("site2md")], {"site2md": make_result()}, "light")
        legend = ET.fromstring(chart).find(f".//{SVG}g[@class='legend']")
        assert legend is not None
        self.assertEqual([text.text for text in legend.iter(f"{SVG}text")], ["Install size", "Time"])
        self.assertEqual(
            [swatch.get("fill") for swatch in legend.iter(f"{SVG}rect")],
            [bar.get("fill") for bar in _bars(_rows(chart)[0])],
        )

    def test_the_two_measures_have_two_colours_in_every_row(self) -> None:
        tools = [make_tool("alpha"), make_tool("beta")]
        chart = render_chart(tools, {"alpha": make_result(), "beta": make_result(size_bytes=50_000_000)}, "light")
        fills = [[bar.get("fill") for bar in _bars(row)] for row in _rows(chart)]
        self.assertEqual(fills, [[SIZE_COLOURS["light"], TIME_COLOURS["light"]]] * 2)

    def test_rows_run_from_the_smallest_install_to_the_largest(self) -> None:
        tools = [make_tool("alpha"), make_tool("beta"), make_tool("gamma")]
        results = {
            "alpha": make_result(size_bytes=200_000_000, mean=0.1),
            "beta": make_result(size_bytes=50_000_000, mean=0.9),
            "gamma": make_result(size_bytes=100_000_000, mean=0.5),
        }
        self.assertEqual([_name(row) for row in _rows(render_chart(tools, results, "light"))], ["beta", "gamma", "alpha"])

    def test_only_the_name_of_site2md_is_bold(self) -> None:
        tools = [make_tool("site2md"), make_tool("pandoc")]
        rows = _rows(render_chart(tools, {"site2md": make_result(), "pandoc": make_result()}, "light"))
        self.assertEqual([_name_element(row).get("font-weight") for row in rows], ["bold", None])

    def test_each_measure_is_scaled_to_its_own_maximum(self) -> None:
        tools = [make_tool("alpha"), make_tool("beta"), make_tool("gamma")]
        results = {
            "alpha": make_result(size_bytes=200_000_000, mean=2.0),
            "beta": make_result(size_bytes=50_000_000, mean=1.0),
            "gamma": make_result(size_bytes=100_000_000, mean=0.5),
        }
        rows = _rows(render_chart(tools, results, "light"))
        sizes = [float(_bars(row)[0].get("width", "")) for row in rows]
        times = [float(_bars(row)[1].get("width", "")) for row in rows]
        # Rows run beta, gamma, alpha: sizes 50, 100 and 200 MB, times 1, 0.5 and 2 s.
        self.assertAlmostEqual(sizes[1] / sizes[0], 2, places=1)
        self.assertAlmostEqual(sizes[2] / sizes[0], 4, places=1)
        self.assertAlmostEqual(times[1] / times[0], 0.5, places=1)
        self.assertAlmostEqual(times[2] / times[0], 2, places=1)
        self.assertEqual(max(sizes), max(times))

    def test_the_bars_share_a_start_but_not_a_scale_so_the_chart_has_no_gridlines_or_ticks(self) -> None:
        chart = render_chart([make_tool("site2md")], {"site2md": make_result()}, "light")
        root = ET.fromstring(chart)
        self.assertEqual(list(root.iter(f"{SVG}line")), [])
        self.assertEqual(
            [text.text for text in root.iter(f"{SVG}text")],
            ["Install size", "Time", "Each measure has its own scale", "site2md", "11.5 MB", "661 ms"],
        )

    def test_a_tool_whose_output_does_not_match_has_no_bars(self) -> None:
        tools = [make_tool("site2md"), make_tool("scrapling")]
        results = {"site2md": make_result(), "scrapling": make_result(matches=False)}
        chart = render_chart(tools, results, "light")
        self.assertEqual([_name(row) for row in _rows(chart)], ["site2md"])
        self.assertNotIn("scrapling", _texts(chart))

    def test_a_tool_added_later_gets_two_bars_under_its_display_name(self) -> None:
        tools = [make_tool("site2md"), make_tool("newcomer", name="New Comer")]
        results = {"site2md": make_result(), "newcomer": make_result(size_bytes=94_800_000, mean=0.632)}
        row = _rows(render_chart(tools, results, "light"))[1]
        self.assertEqual(_name(row), "New Comer")
        self.assertEqual(_values(row), ["94.8 MB", "632 ms"])
        self.assertEqual(len(_bars(row)), 2)

    def test_a_tool_that_has_no_results_has_no_bars(self) -> None:
        chart = render_chart([make_tool("site2md"), make_tool("pandoc")], {"site2md": make_result()}, "light")
        self.assertNotIn("pandoc", _texts(chart))

    def test_a_chart_without_any_matching_tool_is_still_valid_svg(self) -> None:
        for theme in THEMES:
            with self.subTest(theme=theme):
                chart = render_chart([make_tool("site2md")], {"site2md": make_result(matches=False)}, theme)
                root = ET.fromstring(chart)
                self.assertEqual(root.tag, f"{SVG}svg")
                self.assertEqual(_rows(chart), [])

    def test_both_themes_render_well_formed_svg(self) -> None:
        tools = [make_tool("site2md"), make_tool("pandoc")]
        results = {"site2md": make_result(), "pandoc": make_result(size_bytes=239_600_000, mean=0.25)}
        for theme in THEMES:
            with self.subTest(theme=theme):
                self.assertEqual(ET.fromstring(render_chart(tools, results, theme)).tag, f"{SVG}svg")

    def test_names_are_escaped_so_that_the_svg_stays_valid(self) -> None:
        tools = [make_tool("site2md", name="Fast & <Loose>")]
        self.assertIn("Fast & <Loose>", _texts(render_chart(tools, {"site2md": make_result()}, "light")))

    def test_the_themes_set_the_text_colour_and_their_own_bar_colours(self) -> None:
        tools, results = [make_tool("site2md")], {"site2md": make_result()}
        text_colours = {"light": "#333333", "dark": "#C9D1D9"}
        for theme in THEMES:
            with self.subTest(theme=theme):
                chart = render_chart(tools, results, theme)
                self.assertEqual(ET.fromstring(chart).get("fill"), text_colours[theme])
                self.assertEqual(
                    [bar.get("fill") for bar in _bars(_rows(chart)[0])], [SIZE_COLOURS[theme], TIME_COLOURS[theme]]
                )

    def test_the_description_gives_each_tools_two_values_for_readers_who_cannot_see_the_bars(self) -> None:
        tools = [make_tool("site2md"), make_tool("pandoc")]
        results = {
            "site2md": make_result(size_bytes=11_485_228, mean=0.870),
            "pandoc": make_result(size_bytes=239_600_000, mean=0.250),
        }
        root = ET.fromstring(render_chart(tools, results, "light"))
        self.assertEqual(root.findtext(f"{SVG}desc"), "site2md: 11.5 MB, 870 ms; pandoc: 239.6 MB, 250 ms")


def _rows(chart: str) -> list[ET.Element]:
    """Return the group of each tool's row, from the top down."""
    return ET.fromstring(chart).findall(f".//{SVG}g[@class='row']")


def _bars(row: ET.Element) -> list[ET.Element]:
    """Return a row's bars: install size first, then time."""
    return list(row.iter(f"{SVG}rect"))


def _name_element(row: ET.Element) -> ET.Element:
    """Return the label of a row's tool, which sits to the left of the bars."""
    name = row.find(f"{SVG}text[@text-anchor='end']")
    assert name is not None
    return name


def _name(row: ET.Element) -> str:
    """Return the name of a row's tool."""
    return _name_element(row).text or ""


def _values(row: ET.Element) -> list[str]:
    """Return the labels at the ends of a row's bars, install size first."""
    return [text.text or "" for text in row.iter(f"{SVG}text") if text.get("text-anchor") != "end"]


def _texts(chart: str) -> list[str]:
    """Return the text of every label in an SVG chart, in document order."""
    return [element.text or "" for element in ET.fromstring(chart).iter(f"{SVG}text")]


if __name__ == "__main__":
    unittest.main()
