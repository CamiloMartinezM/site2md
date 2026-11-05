"""Shared support for installed-command integration tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import unittest
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import Self

Response = tuple[int, dict[str, str], bytes]
Route = Response | Callable[[BaseHTTPRequestHandler], None]


def installed_command() -> Path:
    """Return the site2md console script installed next to the running Python."""
    name = "site2md.exe" if sys.platform == "win32" else "site2md"
    return Path(sys.executable).with_name(name)


class RecordingServer:
    """Serve fixed responses and record every requested path."""

    def __init__(self, routes: Mapping[str, Route]) -> None:
        self.requests: list[str] = []
        self.user_agents: list[str | None] = []
        requests = self.requests
        user_agents = self.user_agents

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                requests.append(self.path)
                user_agents.append(self.headers.get("User-Agent"))
                route = routes.get(self.path)
                if route is None:
                    response = (404, {"Content-Type": "text/plain"}, b"not found")
                elif callable(route):
                    route(self)
                    return
                else:
                    response = route

                status, headers, body = response
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        """Return this server's HTTP origin."""
        # server_name comes from getfqdn(), which names the LAN host on Windows.
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def __enter__(self) -> Self:
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()


class InstalledCliTestCase(unittest.TestCase):
    """Run the installed command with explicit environment and timeout controls."""

    command: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.command = installed_command()
        if not cls.command.is_file():
            raise RuntimeError(f"Installed site2md command not found at {cls.command}")

    def run_site2md(
        self,
        *arguments: object,
        without_wget: bool = False,
        timeout: float | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the installed command and capture its observable result."""
        environment = os.environ.copy()
        if without_wget:
            environment["PATH"] = str(self.command.parent)
        if extra_environment:
            environment.update(extra_environment)
        return subprocess.run(
            [str(self.command), *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=timeout,
        )

    def retained_workspace(self, stdout: str) -> Path:
        """Return the reported retained workspace and remove it after the test."""
        marker = "Temporary files kept at "
        self.assertIn(marker, stdout)
        workspace = Path(stdout.split(marker, 1)[1].splitlines()[0].strip())
        # A misparsed path must fail here, never reach rmtree: Path("") is the current directory.
        self.assertTrue(workspace.is_absolute(), f"not an absolute path: {str(workspace)!r}")
        self.assertTrue(workspace.name.startswith("site2md_remote_"), workspace)
        self.assertTrue(workspace.is_dir(), workspace)
        self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
        return workspace

    @staticmethod
    def startup_hook_environment(root: Path, source: str) -> dict[str, str]:
        """Create a subprocess-only Python startup hook."""
        hook_dir = root / "startup-hook"
        hook_dir.mkdir()
        (hook_dir / "sitecustomize.py").write_text(source, encoding="utf-8")
        python_path = os.environ.get("PYTHONPATH")
        hook_path = (
            f"{hook_dir}{os.pathsep}{python_path}" if python_path else str(hook_dir)
        )
        return {"PYTHONPATH": hook_path}
