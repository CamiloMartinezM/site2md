"""Public-interface tests for remote builds."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from site2md.remote_build import RemoteBuildRequest, build_remote
from tests import test_cli


class RemoteBuildTests(unittest.TestCase):
    """Exercise the request-to-summary remote-build seam."""

    def test_page_build_returns_summary_and_retains_debugging_artifacts(self) -> None:
        routes = {
            "/page": (
                200,
                {"Content-Type": "text/html; charset=utf-8"},
                b"<html><body><main><p>remote</p></main></body></html>",
            )
        }
        with test_cli.RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "result.md"

            summary = build_remote(
                RemoteBuildRequest(
                    entry_url=f"{server.origin}/page",
                    destination=destination,
                    keep_temp=True,
                )
            )

            self.assertEqual(summary.fetched, 1)
            self.assertEqual(summary.skipped, 0)
            self.assertEqual(summary.failed, 0)
            self.assertEqual(summary.warnings, ())
            self.assertEqual(summary.reached_limits, ())
            self.assertIsNotNone(summary.retained_workspace)
            workspace = summary.retained_workspace
            assert workspace is not None
            self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
            self.assertEqual((workspace / "page.html").read_bytes(), routes["/page"][2])
            self.assertTrue((workspace / "converted.md").is_file())
            self.assertIn("remote", destination.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
