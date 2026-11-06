"""Tests for the crawl task's generated site and for reading a crawl from the server's request log."""

from __future__ import annotations

import re
import unittest

from benchmarks.crawl import START_PATH, CrawlSite, build_site
from benchmarks.errors import HarnessError

COUNTRY_COUNT = 43
EXPECTED_PAGES = 20
DECOY_PAGES = 5
BLOCK = re.compile(r'<div class="col-md-4 country">.*?</div><!--\.col-->', re.DOTALL)
NAME = re.compile(r'<h3 class="country-name">.*?</i>\s*(.*?)\s*</h3>', re.DOTALL)
ANCHOR = re.compile(r'<a\s[^>]*href="([^"]*)"')


def _block(number: int) -> str:
    """Write one country block as the page copy does."""
    return f"""
                    <div class="col-md-4 country">
                        <h3 class="country-name">
                            <i class="flag-icon flag-icon-xx"></i>
                            Country {number}
                        </h3>
                        <div class="country-info">
                            <strong>Capital:</strong> <span class="country-capital">Capital {number}</span><br>
                            <strong>Population:</strong> <span class="country-population">{number}00</span><br>
                            <strong>Area (km<sup>2</sup>):</strong> <span class="country-area">{number}.5</span><br>
                        </div>
                    </div><!--.col-->
"""


def _page(count: int = COUNTRY_COUNT) -> str:
    """Write a page copy with a menu, an attribution link and `count` countries."""
    return f"""<!doctype html>
<html><head><title>Countries</title><link href="/static/css/styles.css" rel="stylesheet"></head>
<body>
<nav id="site-nav"><ul>
<li><a href="/" class="nav-link hidden-sm">
    <img src="/static/images/icon.png"> Scrape This Site
</a></li>
<li><a href="/pages/" class="nav-link">Sandbox</a></li>
<li><a href="/faq/">FAQ</a></li>
</ul></nav>
<div id="page">
<section id="countries">
<div class="container">
<h1>Countries <small>{count} items</small></h1>
<p>There are <a href="/lessons/">4 video lessons</a>. Data via
<a href="http://peric.github.io/GetCountries/" class="data-attribution">peric</a></p>
<div class="row">
{"".join(_block(number) for number in range(1, count + 1))}
</div>
</div>
</section>
</div>
<footer>Footer</footer>
</body></html>
"""


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


class BuildSiteTests(unittest.TestCase):
    """Check the layout, the countries and the links of the generated site."""

    def setUp(self) -> None:
        self.page = _page()
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
        held = [block for path in self.site.expected for block in BLOCK.findall(_html(self.site, path))]
        self.assertEqual(sorted(held), sorted(BLOCK.findall(self.page)))

    def test_every_expected_page_holds_some_countries(self) -> None:
        for path in self.site.expected:
            with self.subTest(path=path):
                self.assertTrue(BLOCK.search(_html(self.site, path)))

    def test_the_decoy_pages_hold_only_countries_that_are_not_in_the_page_copy(self) -> None:
        real_names = set(NAME.findall(self.page))
        for path in self.site.decoys:
            with self.subTest(path=path):
                names = NAME.findall(_html(self.site, path))
                self.assertTrue(names)
                self.assertFalse(real_names & set(names))
                self.assertTrue(all(name.startswith("Decoy") for name in names))

    def test_a_decoy_country_has_the_markup_of_a_real_one(self) -> None:
        classes = re.compile(r'class="([^"]*)"')
        block = BLOCK.findall(_html(self.site, self.site.decoys[0]))[0]
        self.assertEqual(classes.findall(block), classes.findall(BLOCK.findall(self.page)[0]))
        population = re.search(r'class="country-population">(.*?)</span>', block)
        area = re.search(r'class="country-area">(.*?)</span>', block)
        self.assertIsNotNone(population)
        self.assertIsNotNone(area)
        self.assertTrue(str(population and population.group(1)).isdigit())
        float(str(area and area.group(1)))

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


if __name__ == "__main__":
    unittest.main()
