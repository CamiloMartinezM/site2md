"""Public-interface tests for remote builds."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from site2md.remote_build import RemoteBuildError, RemoteBuildRequest, build_remote
from tests.cli_test_support import RecordingServer


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
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
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
            index = json.loads((workspace / "index.json").read_text(encoding="utf-8"))
            self.assertEqual([page["status"] for page in index["pages"]], ["converted"])
            self.assertIn("remote", destination.read_text(encoding="utf-8"))
            self.assertEqual(summary.document, destination.read_bytes())
            self.assertEqual(summary.document, (workspace / "document.md").read_bytes())

    def test_kept_workspace_holds_only_the_named_artifacts(self) -> None:
        routes = {
            "/page": (200, {"Content-Type": "text/html"}, b"<html><body>remote</body></html>")
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            summary = build_remote(
                RemoteBuildRequest(
                    entry_url=f"{server.origin}/page",
                    destination=Path(temp_dir) / "result.md",
                    keep_temp=True,
                )
            )

            workspace = summary.retained_workspace
            assert workspace is not None
            self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
            self.assertEqual(
                sorted(path.name for path in workspace.iterdir()),
                ["converted.md", "document.md", "index.json", "page.html"],
            )

    def test_failed_fetch_keeps_an_index_that_records_the_failure(self) -> None:
        routes = {"/missing": (404, {"Content-Type": "text/html"}, b"nope")}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(RemoteBuildError) as raised:
                build_remote(
                    RemoteBuildRequest(
                        entry_url=f"{server.origin}/missing",
                        destination=Path(temp_dir) / "result.md",
                        keep_temp=True,
                    )
                )

            workspace = raised.exception.retained_workspace
            assert workspace is not None
            self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
            self.assertEqual([path.name for path in workspace.iterdir()], ["index.json"])
            index = json.loads((workspace / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(
                index["pages"],
                [
                    {
                        "requested_url": f"{server.origin}/missing",
                        "html": "page.html",
                        "status": "failed",
                        "body_bytes": 4,
                        "stored_bytes": 0,
                        "detail": "Final response returned HTTP 404.",
                    }
                ],
            )

    def test_page_build_syncs_only_the_staged_output_to_disk(self) -> None:
        # The debugging index is deleted after the run, so only the user's output is fsynced.
        routes = {
            "/page": (200, {"Content-Type": "text/html"}, b"<html><body>remote</body></html>")
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("os.fsync", wraps=os.fsync) as fsync:
                build_remote(
                    RemoteBuildRequest(
                        entry_url=f"{server.origin}/page",
                        destination=Path(temp_dir) / "result.md",
                    )
                )

            self.assertEqual(fsync.call_count, 1)


if __name__ == "__main__":
    unittest.main()
