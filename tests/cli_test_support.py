"""Shared support for installed-command integration tests."""

from __future__ import annotations

import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import unittest
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict, overload

if TYPE_CHECKING:
    from typing_extensions import Self

Response = tuple[int, dict[str, str], bytes]
Route = Response | Callable[[BaseHTTPRequestHandler], None]

# Follow and site mode wait a second between requests. The hook skips the wait.
SKIP_PACING_HOOK = """from site2md import downloader
downloader.time.sleep = lambda _seconds: None
"""
# Makes the extraction operation fail the way an Extractor that reports a diagnostic does.
FAIL_EXTRACTION_HOOK = """from site2md import extraction


def fail_extraction(markdown, extractor_id, **options):
    raise extraction.ExtractionError(
        "site2md.test.extraction_failed", "forced extraction failure"
    )


extraction.extract = fail_extraction
"""


class RecordSchemaDeclaration(TypedDict):
    """The record-schema part of an Extractor declaration in a provider manifest."""

    id: str
    version: str
    schema: dict[str, object]


class ExtractorDeclaration(TypedDict):
    """One Extractor declaration in a provider manifest."""

    id: str
    interface_version: int
    implementation_version: str
    record_schema: RecordSchemaDeclaration


class ProviderManifest(TypedDict):
    """A version-one provider manifest as the tests write it."""

    manifest_version: int
    extractors: list[ExtractorDeclaration]


class _TlsServer(ThreadingHTTPServer):
    """Serve HTTPS with one certificate, and shake hands on the handler's thread, not the accepting one."""

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        certificate: Path,
    ) -> None:
        super().__init__(address, handler)
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(certificate)

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        connection, address = super().get_request()
        # A browser opens connections that it never uses, and a handshake here would wait for each.
        return self.context.wrap_socket(connection, server_side=True, do_handshake_on_connect=False), address

    def handle_error(self, request: object, client_address: object) -> None:
        # The browser drops the connections that it opened ahead and the handshakes that it refused.
        pass


class RecordingServer:
    """Serve fixed responses and record every requested path."""

    def __init__(self, routes: Mapping[str, Route], *, certificate: Path | None = None) -> None:
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

        self.httpd: ThreadingHTTPServer
        if certificate is None:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        else:
            self.httpd = _TlsServer(("127.0.0.1", 0), Handler, certificate)
        self.scheme = "http" if certificate is None else "https"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        """Return this server's origin, HTTP unless it has a certificate."""
        # server_name comes from getfqdn(), which names the LAN host on Windows.
        return f"{self.scheme}://127.0.0.1:{self.httpd.server_port}"

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

    @overload
    def _run(
        self,
        arguments: tuple[object, ...],
        *,
        text: Literal[True],
        without_wget: bool,
        timeout: float | None,
        extra_environment: dict[str, str] | None,
    ) -> subprocess.CompletedProcess[str]: ...

    @overload
    def _run(
        self,
        arguments: tuple[object, ...],
        *,
        text: Literal[False],
        without_wget: bool,
        timeout: float | None,
        extra_environment: dict[str, str] | None,
    ) -> subprocess.CompletedProcess[bytes]: ...

    def _run(
        self,
        arguments: tuple[object, ...],
        *,
        text: bool,
        without_wget: bool,
        timeout: float | None,
        extra_environment: dict[str, str] | None,
    ) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
        """Run the installed command and capture its streams as text or as bytes."""
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        if without_wget:
            environment["PATH"] = str(self.command.parent)
        if extra_environment:
            environment.update(extra_environment)
        command = [str(self.command), *map(str, arguments)]
        if text:
            return subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
                timeout=timeout,
            )
        return subprocess.run(
            command, check=False, capture_output=True, env=environment, timeout=timeout
        )

    def run_site2md(
        self,
        *arguments: object,
        without_wget: bool = False,
        timeout: float | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the installed command and capture its observable result."""
        return self._run(
            arguments,
            text=True,
            without_wget=without_wget,
            timeout=timeout,
            extra_environment=extra_environment,
        )

    def run_site2md_bytes(
        self,
        *arguments: object,
        without_wget: bool = False,
        timeout: float | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        """Run the installed command and capture its streams as the exact bytes it wrote."""
        return self._run(
            arguments,
            text=False,
            without_wget=without_wget,
            timeout=timeout,
            extra_environment=extra_environment,
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


def installed_command() -> Path:
    """Return the site2md console script installed next to the running Python."""
    name = "site2md.exe" if sys.platform == "win32" else "site2md"
    return Path(sys.executable).with_name(name)
