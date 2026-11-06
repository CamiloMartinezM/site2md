"""Generate the crawl task's site from the page copy, and read a crawl from the server's request log."""

from __future__ import annotations

import itertools
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from benchmarks._types import RequestLog
from benchmarks.errors import HarnessError

START_PATH = "/"
ROBOTS_PATH = "/robots.txt"
# The layout: 1 entry page, 4 pages below it and 15 below those fill the 20-page budget within depth 2.
LEVEL_1_PAGES = 4
LEVEL_2_PAGES = 15
DECOY_PAGES = 5
DECOYS_PER_PAGE = 2
# The copy's own links, such as its menu, point at paths that this server doesn't have.
_OWN_LINK = re.compile(r'<a href="/[^"]*"[^>]*>(.*?)</a>', re.DOTALL)
_COUNTRY = re.compile(r'<div class="col-md-4 country">.*?</div><!--\.col-->', re.DOTALL)
_COUNTRY_NAME = re.compile(r"(</i>).*?(</h3>)", re.DOTALL)


@dataclass(frozen=True)
class CrawlSite:
    """The generated site: its pages ready to serve, the 20 that a crawl may fetch and the 5 decoys."""

    pages: Mapping[str, bytes]
    # In breadth-first order, starting with the entry page.
    expected: tuple[str, ...]
    decoys: tuple[str, ...]


def _decoy_country(template: str, number: int) -> str:
    """Copy a country block, giving it values that no real country has."""
    country = _COUNTRY_NAME.sub(rf"\g<1>Decoy Country {number}\g<2>", template)
    values = {"capital": f"Decoy City {number}", "population": str(1000 + number), "area": f"{number}.0"}
    for field, value in values.items():
        country = re.sub(rf'(class="country-{field}">).*?(</span>)', rf"\g<1>{value}\g<2>", country)
    return country


def _page(head: str, tail: str, countries: list[str], links: list[str]) -> bytes:
    """Assemble one page from the copy's head and tail, some countries and its links."""
    menu = "".join(f'<li><a href="{link}">{link}</a></li>' for link in links)
    section = '<section id="countries">'
    head = head.replace(section, f'{section}<ul class="site-links">{menu}</ul>', 1)
    return (head + "\n".join(countries) + tail).encode("utf-8")


def _page_requests(requests: RequestLog) -> list[tuple[float, str]]:
    """Return the requests for pages, which leaves out robots.txt."""
    return [request for request in requests if request[1] != ROBOTS_PATH]


def build_site(page_html: str) -> CrawlSite:
    """Build the site: 20 pages within depth 2 that split the copy's countries, and 5 decoy pages at depth 3."""
    html = _OWN_LINK.sub(r"\1", page_html)
    matches = list(_COUNTRY.finditer(html))
    if not matches:
        raise HarnessError("the page copy holds no countries to build the crawl site from")
    head, tail = html[: matches[0].start()], html[matches[-1].end() :]
    countries = [match.group() for match in matches]
    level_1 = [f"/level-1/page-{number}.html" for number in range(1, LEVEL_1_PAGES + 1)]
    level_2 = [f"/level-2/page-{number}.html" for number in range(1, LEVEL_2_PAGES + 1)]
    decoys = tuple(f"/level-3/page-{number}.html" for number in range(1, DECOY_PAGES + 1))
    expected = (START_PATH, *level_1, *level_2)
    # Four children per page below the entry page, and a decoy below each of the first level-2 pages.
    children = {START_PATH: level_1}
    children.update({path: level_2[index * 4 : index * 4 + 4] for index, path in enumerate(level_1)})
    children.update({path: [decoys[index]] for index, path in enumerate(level_2[:DECOY_PAGES])})
    pages = {
        path: _page(
            head,
            tail,
            countries[index :: len(expected)],
            ([] if path == START_PATH else [START_PATH]) + children.get(path, []),
        )
        for index, path in enumerate(expected)
    }
    for index, path in enumerate(decoys):
        numbers = range(index * DECOYS_PER_PAGE + 1, (index + 1) * DECOYS_PER_PAGE + 1)
        pages[path] = _page(head, tail, [_decoy_country(countries[0], number) for number in numbers], [START_PATH])
    return CrawlSite(pages, expected, decoys)


def extra_pages(requests: RequestLog, expected: Collection[str]) -> list[str]:
    """Return the pages fetched beyond one fetch of each expected page, in request order."""
    seen: set[str] = set()
    extra = []
    for _, path in _page_requests(requests):
        if path in expected and path not in seen:
            seen.add(path)
        else:
            extra.append(path)
    return extra


def shortest_gap(requests: RequestLog) -> float | None:
    """Return the shortest time in seconds between two consecutive child-page requests, if there are two.

    The first page request is the entry page, so the children are the page requests after it.
    """
    # Handler threads can log a later request first, so the times are sorted before they are paired.
    children = sorted(moment for moment, _ in _page_requests(requests)[1:])
    return min((later - earlier for earlier, later in itertools.pairwise(children)), default=None)
