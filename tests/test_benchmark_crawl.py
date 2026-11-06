"""Tests for the crawl task's generated site and for reading a crawl from the server's request log."""

from __future__ import annotations

import re
import unittest

from benchmarks.crawl import (
    START_PATH,
    CrawlSite,
    build_site,
    extra_pages,
    shortest_gap,
)
from benchmarks.errors import HarnessError
from tests.benchmark_test_support import make_page

COUNTRY_COUNT = 43
EXPECTED_PAGES = 20
DECOY_PAGES = 5
NAME = re.compile(r'<h3 class="country-name">.*?</i>\s*(.*?)\s*</h3>', re.DOTALL)
ANCHOR = re.compile(r'<a\s[^>]*href="([^"]*)"')


class BuildSiteTests(unittest.TestCase):
    """Check the layout, the countries and the links of the generated site."""

    def setUp(self) -> None:
        self.page = make_page(COUNTRY_COUNT)
        self.site = build_site(self.page)

    def test_the_site_has_twenty_expected_pages_and_five_decoy_pages(self) -> None:
        self.assertEqual(len(self.site.expected), EXPECTED_PAGES)
        self.assertEqual(len(self.site.decoys), DECOY_PAGES)
        self.assertEqual(set(self.site.pages), {*self.site.expected, *self.site.decoys})

    def test_the_entry_page_is_the_first_expected_page(self) -> None:
        self.assertEqual(self.site.expected[0], START_PATH)

    def test_every_expected_page_is_within_depth_two_and_every_decoy_is_one_level_deeper(self) -> None:
        depths = _depths(self.site)
        self.assertEqual(set(depths), set(self.site.pages))
        self.assertEqual({depths[path] for path in self.site.expected}, {0, 1, 2})
        self.assertEqual({depths[path] for path in self.site.decoys}, {3})

    def test_the_expected_pages_are_listed_in_breadth_first_order(self) -> None:
        depths = _depths(self.site)
        listed = [depths[path] for path in self.site.expected]
        self.assertEqual(listed, sorted(listed))

    def test_each_decoy_page_is_linked_from_a_different_page(self) -> None:
        parents = [
            path
            for decoy in self.site.decoys
            for path in self.site.pages
            if f'href="{decoy}"' in _html(self.site, path)
        ]
        self.assertEqual(len(set(parents)), DECOY_PAGES)

    def test_the_expected_pages_together_hold_every_country_exactly_once(self) -> None:
        held = [name for path in self.site.expected for name in NAME.findall(_html(self.site, path))]
        self.assertEqual(sorted(held), sorted(f"Country {number}" for number in range(1, COUNTRY_COUNT + 1)))

    def test_every_expected_page_holds_some_countries(self) -> None:
        for path in self.site.expected:
            with self.subTest(path=path):
                self.assertTrue(NAME.search(_html(self.site, path)))

    def test_the_decoy_pages_hold_only_countries_that_are_not_in_the_page_copy(self) -> None:
        real_names = set(NAME.findall(self.page))
        for path in self.site.decoys:
            with self.subTest(path=path):
                names = NAME.findall(_html(self.site, path))
                self.assertTrue(names)
                self.assertFalse(real_names & set(names))
                self.assertTrue(all(name.startswith("Decoy") for name in names))

    def test_a_decoy_country_has_the_markup_of_a_real_one(self) -> None:
        page = _html(self.site, self.site.decoys[0])
        for markup in (
            '<div class="col-md-4 country">',
            '<h3 class="country-name">',
            '<span class="country-capital">Decoy City 1</span>',
            '<span class="country-population">1001</span>',
            '<span class="country-area">1.0</span>',
        ):
            self.assertIn(markup, page)

    def test_the_copys_own_menu_links_are_gone(self) -> None:
        for path, body in self.site.pages.items():
            for link in ANCHOR.findall(body.decode("utf-8")):
                with self.subTest(path=path, link=link):
                    self.assertTrue(link in self.site.pages or not link.startswith("/"), link)

    def test_the_text_of_a_removed_menu_link_stays(self) -> None:
        self.assertIn("Sandbox", _html(self.site, START_PATH))

    def test_a_link_to_another_site_stays(self) -> None:
        self.assertIn('href="http://peric.github.io/GetCountries/"', _html(self.site, START_PATH))

    def test_every_other_page_links_back_to_the_entry_page(self) -> None:
        for path in self.site.pages:
            if path != START_PATH:
                with self.subTest(path=path):
                    self.assertIn(f'href="{START_PATH}"', _html(self.site, path))

    def test_the_entry_page_does_not_link_to_itself(self) -> None:
        self.assertNotIn(f'href="{START_PATH}"', _html(self.site, START_PATH))

    def test_a_page_without_countries_is_rejected(self) -> None:
        with self.assertRaisesRegex(HarnessError, "countries"):
            build_site("<html><body>Nothing here</body></html>")


class ExtraPagesTests(unittest.TestCase):
    """Check which fetches of a crawl fall outside the expected pages."""

    EXPECTED = ("/", "/a", "/b")

    def test_a_crawl_of_the_expected_pages_fetched_nothing_extra(self) -> None:
        log = [(0.0, "/robots.txt"), (0.1, "/"), (1.2, "/a"), (2.3, "/b")]
        self.assertEqual(extra_pages(log, self.EXPECTED), [])

    def test_a_decoy_page_is_extra(self) -> None:
        log = [(0.1, "/"), (1.2, "/a"), (2.3, "/b"), (3.4, "/level-3/page-1.html")]
        self.assertEqual(extra_pages(log, self.EXPECTED), ["/level-3/page-1.html"])

    def test_fetching_the_entry_page_a_second_time_is_one_extra_page(self) -> None:
        log = [(0.1, "/"), (1.2, "/a"), (2.3, "/"), (3.4, "/b")]
        self.assertEqual(extra_pages(log, self.EXPECTED), ["/"])

    def test_a_path_the_site_does_not_have_is_extra_even_though_it_was_not_found(self) -> None:
        log = [(0.1, "/"), (1.2, "/pages/"), (2.3, "/a"), (3.4, "/b")]
        self.assertEqual(extra_pages(log, self.EXPECTED), ["/pages/"])

    def test_extra_pages_come_in_the_order_they_were_fetched(self) -> None:
        log = [(0.1, "/"), (1.2, "/z"), (2.3, "/a"), (3.4, "/y"), (4.5, "/z")]
        self.assertEqual(extra_pages(log, self.EXPECTED), ["/z", "/y", "/z"])

    def test_robots_txt_is_not_a_page_however_often_it_is_fetched(self) -> None:
        log = [(0.0, "/robots.txt"), (0.1, "/"), (0.2, "/robots.txt"), (1.3, "/a")]
        self.assertEqual(extra_pages(log, self.EXPECTED), [])

    def test_a_crawl_that_fetched_nothing_has_nothing_extra(self) -> None:
        self.assertEqual(extra_pages([], self.EXPECTED), [])


class ShortestGapTests(unittest.TestCase):
    """Check the shortest time between two consecutive child-page requests."""

    def test_it_is_the_smallest_difference_between_consecutive_child_requests(self) -> None:
        log = [(0.0, "/"), (5.0, "/a"), (6.5, "/b"), (7.25, "/c"), (9.0, "/d")]
        self.assertEqual(shortest_gap(log), 0.75)

    def test_the_gap_between_the_entry_page_and_the_first_child_is_not_a_child_gap(self) -> None:
        log = [(0.0, "/"), (0.1, "/a"), (1.4, "/b")]
        self.assertAlmostEqual(shortest_gap(log) or 0.0, 1.3)

    def test_robots_txt_requests_are_not_child_pages(self) -> None:
        log = [(0.0, "/robots.txt"), (0.1, "/"), (0.2, "/robots.txt"), (2.0, "/a"), (2.05, "/robots.txt"), (4.0, "/b")]
        self.assertEqual(shortest_gap(log), 2.0)

    def test_a_repeated_fetch_is_a_child_request(self) -> None:
        log = [(0.0, "/"), (1.0, "/a"), (1.02, "/")]
        self.assertAlmostEqual(shortest_gap(log) or 0.0, 0.02)

    def test_requests_logged_out_of_time_order_are_paired_by_time(self) -> None:
        # Concurrent handler threads can append a later request before an earlier one.
        log = [(0.0, "/"), (5.0, "/b"), (4.0, "/a"), (6.5, "/c")]
        self.assertEqual(shortest_gap(log), 1.0)

    def test_there_is_no_gap_with_fewer_than_two_child_requests(self) -> None:
        self.assertIsNone(shortest_gap([]))
        self.assertIsNone(shortest_gap([(0.0, "/robots.txt"), (0.1, "/")]))
        self.assertIsNone(shortest_gap([(0.0, "/"), (1.0, "/a")]))


def _html(site: CrawlSite, path: str) -> str:
    """Return one generated page."""
    return site.pages[path].decode("utf-8")


def _depths(site: CrawlSite) -> dict[str, int]:
    """Return how many links lead from the entry page to each page, found breadth first."""
    depths = {START_PATH: 0}
    queue = [START_PATH]
    for path in queue:
        for link in ANCHOR.findall(_html(site, path)):
            if link in site.pages and link not in depths:
                depths[link] = depths[path] + 1
                queue.append(link)
    return depths


if __name__ == "__main__":
    unittest.main()
