"""Tests for the local server that hosts the benchmark's fixtures."""

from __future__ import annotations

import unittest
import urllib.error
import urllib.request

from benchmarks.server import FixtureServer


class FixtureServerTests(unittest.TestCase):
    """Check what the server answers and what it records."""

    def test_a_page_is_served_as_html_on_loopback(self) -> None:
        with FixtureServer({"/pages/simple/": "<h1>Fran\u00e7ais</h1>".encode()}) as server:
            self.assertTrue(server.origin.startswith("http://127.0.0.1:"))
            status, content_type, body = _get(server.origin + "/pages/simple/")
        self.assertEqual((status, content_type, body), (200, "text/html; charset=utf-8", "<h1>Fran\u00e7ais</h1>"))

    def test_an_unknown_path_is_not_found(self) -> None:
        with FixtureServer({}) as server:
            self.assertEqual(_get(server.origin + "/missing")[0], 404)

    def test_robots_txt_allows_everything_unless_the_fixture_defines_it(self) -> None:
        with FixtureServer({}) as server:
            status, _, body = _get(server.origin + "/robots.txt")
        self.assertEqual(status, 200)
        self.assertIn("Allow: /", body)

    def test_each_request_is_recorded_with_its_path_in_order_with_rising_times(self) -> None:
        with FixtureServer({"/a": b"a", "/b": b"b"}) as server:
            _get(server.origin + "/b")
            _get(server.origin + "/a")
            _get(server.origin + "/missing")
        self.assertEqual([path for _, path in server.requests], ["/b", "/a", "/missing"])
        times = [time for time, _ in server.requests]
        self.assertEqual(times, sorted(times))

    def test_requests_in_quick_succession_get_different_times(self) -> None:
        # time.monotonic() ticks every 15.6 ms on Windows under Python 3.12, so quick requests would share a time.
        with FixtureServer({"/a": b"a"}) as server:
            for _ in range(30):
                _get(server.origin + "/a")
        times = [time for time, _ in server.requests]
        self.assertEqual(len(set(times)), 30)

    def test_servers_running_at_the_same_time_use_different_ports(self) -> None:
        with FixtureServer({}) as first, FixtureServer({}) as second:
            self.assertNotEqual(first.origin, second.origin)


def _get(url: str) -> tuple[int, str, str]:
    """Return the status, content type and body of one response."""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.headers["Content-Type"], response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.headers["Content-Type"], error.read().decode("utf-8")


if __name__ == "__main__":
    unittest.main()
