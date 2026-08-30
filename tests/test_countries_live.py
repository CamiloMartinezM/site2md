"""Opt-in live drift check for the built-in countries Extractor."""

from __future__ import annotations

import json
import os
import shutil
import unittest
import urllib.request
from urllib.robotparser import RobotFileParser

from site2md.converter import convert_remote_page_to_markdown
from site2md.downloader import USER_AGENT, fetch_remote
from site2md.extraction import extract

EXTRACTOR_ID = "site2md.scrapethissite.countries"
PAGE_URL = "https://www.scrapethissite.com/pages/simple/"
ROBOTS_URL = "https://www.scrapethissite.com/robots.txt"


@unittest.skipUnless(
    os.environ.get("SITE2MD_LIVE_TESTS") == "1",
    "set SITE2MD_LIVE_TESTS=1 to enable the permitted live drift check",
)
class CountriesLiveTests(unittest.TestCase):
    """Check current permitted training-page output with one page request."""

    def test_training_page_still_produces_expected_country_records(self) -> None:
        robots_request = urllib.request.Request(
            ROBOTS_URL,
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(robots_request, timeout=30) as response:
            robots = response.read().decode("utf-8")
        policy = RobotFileParser(ROBOTS_URL)
        policy.parse(robots.splitlines())
        self.assertTrue(
            policy.can_fetch(USER_AGENT, PAGE_URL),
            "the current robots policy does not permit the live page check",
        )

        page = fetch_remote(PAGE_URL)
        try:
            markdown = convert_remote_page_to_markdown(page)
        finally:
            shutil.rmtree(page.content_path.parent)
        payload = json.loads(extract(markdown, EXTRACTOR_ID).to_json())
        records = [record["value"] for record in payload["records"]]

        self.assertEqual(len(records), 250)
        self.assertEqual(
            records[0],
            {
                "name": "Andorra",
                "capital": "Andorra la Vella",
                "population": 84000,
                "area_km2": 468.0,
            },
        )
        self.assertEqual(
            records[-1],
            {
                "name": "Zimbabwe",
                "capital": "Harare",
                "population": 11651858,
                "area_km2": 390580.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
