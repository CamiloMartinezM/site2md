"""Read one page from an installed Chromium-based browser over the DevTools protocol on a pipe."""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import suppress
from email.message import Message
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

from site2md import downloader
from site2md._types import DevToolsMessage
from site2md.downloader import RemoteFetchError, RemotePage

_FOLDER_PREFIX = "site2md_browser_"
VIRTUAL_TIME_BUDGET_MILLISECONDS = 10_000
BROWSER_SWITCHES = (
    "--headless",
    "--remote-debugging-pipe",
    "--no-first-run",
    "--no-default-browser-check",
    # Without it, Edge on Windows hands over to a second process and exits.
    "--edge-skip-compat-layer-relaunch",
    # Chrome 154 upgrades an http:// page to https, and falls back to http if that fails. Without
    # these, the page isn't requested at the address given, and the fallback looks like a downgrade.
    "--disable-features=HttpsUpgrades,HttpsFirstBalancedModeAutoEnable",
)
_BYTES_PER_MIB = 1024 * 1024
_READ_SIZE = 64 * 1024
# A wait on a queue isn't interrupted by Ctrl+C on Windows, so a wait is made in short turns.
_POLL_SECONDS = 0.25
_CLOSE_SECONDS = 5
_REASON_LENGTH = 300
# The address, the doctype and the markup of the document as it stands, which the page's scripts have changed.
_READ_DOCUMENT = (
    "[document.location.href, (document.doctype ? '<!DOCTYPE ' + document.doctype.name + '>\\n' : '')"
    " + document.documentElement.outerHTML]"
)
_DOCUMENT_REQUESTS = [{"urlPattern": "*", "resourceType": "Document", "requestStage": "Request"}]


class _PipeClosed(RuntimeError):
    """Raised when the browser has closed its end of the pipe, which means that it has stopped."""


class _ProtocolError(RuntimeError):
    """Raised when the browser answers a command with an error."""


class _Process:
    """The browser's process, which can be waited for and killed with its children."""

    def __init__(self, pid: int, popen: subprocess.Popen[bytes] | None) -> None:
        self._pid = pid
        # Only Windows starts the browser through subprocess. Elsewhere it is started by pid.
        self._popen = popen

    def wait(self, timeout: float) -> bool:
        """Return whether the process has exited, after waiting up to timeout seconds for it."""
        if sys.platform == "win32":
            assert self._popen is not None
            try:
                self._popen.wait(timeout)
            except subprocess.TimeoutExpired:
                return False
            return True
        end = time.monotonic() + timeout
        while True:
            try:
                finished, _ = os.waitpid(self._pid, os.WNOHANG)
            except ChildProcessError:
                return True
            if finished:
                return True
            if time.monotonic() >= end:
                return False
            time.sleep(0.01)

    def kill(self) -> None:
        """End the process and its children at once."""
        if sys.platform == "win32":
            assert self._popen is not None
            # The browser's other processes exit when this one does.
            self._popen.kill()
            return
        # The browser leads its own process group, which holds its children as well.
        with suppress(ProcessLookupError):
            os.killpg(self._pid, signal.SIGKILL)


class _Browser:
    """A running browser, and the two pipes that carry the DevTools protocol to and from it."""

    def __init__(self, program: str, folder: Path) -> None:
        self._log_path = folder / "browser.log"
        commands_read, self._commands = os.pipe()
        self._answers, answers_write = os.pipe()
        try:
            with self._log_path.open("wb") as log:
                self._process = _start(program, folder / "profile", log, commands_read, answers_write)
        except OSError as error:
            os.close(self._commands)
            os.close(self._answers)
            raise RemoteFetchError(f"Could not start the browser {program}: {error}") from error
        finally:
            # The browser holds the other ends now. Without this, its exit would never end a read.
            os.close(commands_read)
            os.close(answers_write)
        self._messages: queue.Queue[bytes | None] = queue.Queue()
        self._reader = threading.Thread(target=self._read_answers, daemon=True)
        self._reader.start()

    def _read_answers(self) -> None:
        """Split what the browser writes into messages, which end with a NUL byte, and queue them."""
        buffer = bytearray()
        try:
            while chunk := os.read(self._answers, _READ_SIZE):
                buffer += chunk
                while (end := buffer.find(0)) >= 0:
                    self._messages.put(bytes(buffer[:end]))
                    del buffer[: end + 1]
        except OSError:
            pass
        # A read can't time out, so the end of the pipe is how a stopped browser is noticed.
        self._messages.put(None)

    def send(self, message: DevToolsMessage) -> None:
        """Send one command."""
        try:
            os.write(self._commands, json.dumps(message).encode("utf-8") + b"\0")
        except OSError as error:
            raise _PipeClosed from error

    def receive(self, deadline: float) -> DevToolsMessage:
        """Return the next message, or raise TimeoutError when the deadline passes first."""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            try:
                raw = self._messages.get(timeout=min(remaining, _POLL_SECONDS))
            except queue.Empty:
                continue
            if raw is None:
                raise _PipeClosed
            message: DevToolsMessage = json.loads(raw)
            return message

    def stopped_reason(self) -> str:
        """Return the line that explains why the browser stopped, from what it printed, or an empty string."""
        lines = [
            line.strip()
            for line in self._log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        ]
        fatal = [line for line in lines if "FATAL" in line]
        return (fatal or lines or [""])[0][:_REASON_LENGTH]

    def close(self) -> None:
        """End the browser: ask it to close, and kill it if it is still there after a few seconds."""
        with suppress(_PipeClosed):
            self.send({"id": 0, "method": "Browser.close"})
        # Closing the commands also ends the browser, which is how it finds out that site2md has gone.
        os.close(self._commands)
        if not self._process.wait(_CLOSE_SECONDS):
            self._process.kill()
            self._process.wait(_CLOSE_SECONDS)
        self._reader.join(_CLOSE_SECONDS)
        if not self._reader.is_alive():
            os.close(self._answers)


class _Page:
    """One page of the browser, its commands, and what the browser says about the page's own document."""

    def __init__(self, browser: _Browser, deadline: float) -> None:
        self.browser = browser
        self.deadline = deadline
        # The last response that the browser gave for the page's own document.
        self.document: DevToolsMessage | None = None
        self.refused_downgrade = False
        self.is_time_up = False
        self._next_id = 0
        self._session = ""
        self._main_frame = ""
        # The address of each request for the page's own document, by the id that the browser gave it.
        self._requested: dict[str, str] = {}

    def attach(self) -> None:
        """Attach to the browser's page, and set it up: no downloads, a new User-Agent, and a view of redirects."""
        targets = self.call("Target.getTargets", in_page=False)["targetInfos"]
        pages = [target["targetId"] for target in targets if target["type"] == "page"]
        target_id = pages[0] if pages else self.call("Target.createTarget", in_page=False, url="about:blank")["targetId"]
        # A flat session carries a session id on every command to the page, as the protocol advises.
        self._session = self.call("Target.attachToTarget", in_page=False, targetId=target_id, flatten=True)["sessionId"]
        self.call("Browser.setDownloadBehavior", in_page=False, behavior="deny")
        self.call("Page.enable")
        self.call("Network.enable")
        self._main_frame = self.call("Page.getFrameTree")["frameTree"]["frame"]["id"]
        agent = self.call("Browser.getVersion", in_page=False)["userAgent"]
        self.call("Network.setUserAgentOverride", userAgent=f"{agent} {downloader.USER_AGENT}")
        # Only the page's own documents are paused, to refuse an HTTPS-to-HTTP redirect before the http request leaves.
        self.call("Fetch.enable", patterns=_DOCUMENT_REQUESTS)

    def call(self, method: str, *, in_page: bool = True, **parameters: object) -> DevToolsMessage:
        """Send one command and return its result, while handling the events that arrive first."""
        sent = self._send(method, parameters, in_page=in_page)
        while True:
            message = self.browser.receive(self.deadline)
            if message.get("id") == sent:
                if "error" in message:
                    raise _ProtocolError(f"{method}: {message['error'].get('message')}")
                result: DevToolsMessage = message.get("result", {})
                return result
            self._handle(message)

    def wait_until_time_is_up(self) -> None:
        """Wait for the end of the page's virtual time budget."""
        while not self.is_time_up:
            self._handle(self.browser.receive(self.deadline))

    def navigation_failure(self, navigation: DevToolsMessage) -> RemoteFetchError:
        """Describe why a navigation failed, in the words of a plain fetch where it has some."""
        if self.refused_downgrade:
            return RemoteFetchError("Refusing HTTPS-to-HTTP redirect downgrade.")
        if navigation.get("isDownload"):
            return RemoteFetchError("Final response is a download, which the browser refuses, not a page.")
        return RemoteFetchError(f"Malformed or unavailable response: {navigation['errorText']}")

    def _send(self, method: str, parameters: DevToolsMessage, *, in_page: bool) -> int:
        """Send one command without waiting for its answer, and return its id."""
        self._next_id += 1
        message: DevToolsMessage = {"id": self._next_id, "method": method, "params": parameters}
        if in_page:
            message["sessionId"] = self._session
        self.browser.send(message)
        return self._next_id

    def _handle(self, message: DevToolsMessage) -> None:
        """Act on one event of the page, and ignore the rest."""
        method = message.get("method")
        parameters = message.get("params", {})
        if method == "Page.javascriptDialogOpening":
            # A dialog stops the page, and every command to it, until it is answered.
            self._send("Page.handleJavaScriptDialog", {"accept": False}, in_page=True)
        elif method == "Fetch.requestPaused":
            self._answer_request(parameters)
        elif (
            method == "Network.responseReceived"
            and parameters.get("type") == "Document"
            and parameters.get("frameId") == self._main_frame
        ):
            self.document = parameters
        elif method == "Emulation.virtualTimeBudgetExpired":
            self.is_time_up = True

    def _answer_request(self, parameters: DevToolsMessage) -> None:
        """Let a request for a document go on, unless it redirects the page from HTTPS to HTTP."""
        request_id = parameters["requestId"]
        url = parameters["request"]["url"]
        if parameters.get("frameId") == self._main_frame:
            earlier = self._requested.get(parameters.get("redirectedRequestId", ""))
            self._requested[request_id] = url
            if earlier is not None and urlsplit(earlier).scheme == "https" and urlsplit(url).scheme == "http":
                self.refused_downgrade = True
                self._send(
                    "Fetch.failRequest",
                    {"requestId": request_id, "errorReason": "BlockedByClient"},
                    in_page=True,
                )
                return
        self._send("Fetch.continueRequest", {"requestId": request_id}, in_page=True)


def _app_paths(name: str) -> Iterator[str]:
    """Yield the paths that the registry names for a program, in its 64-bit and 32-bit views, for all users first."""
    if sys.platform != "win32":
        return
    # Imported here because the module exists only on Windows.
    import winreg

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for software in ("SOFTWARE", r"SOFTWARE\WOW6432Node"):
            key_name = rf"{software}\Microsoft\Windows\CurrentVersion\App Paths\{name}"
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    yield str(winreg.QueryValueEx(key, "")[0])
            except OSError:
                continue


def _candidates() -> Iterator[str | None]:
    """Yield the places where a system installs Chrome, then Edge, then Chromium."""
    if sys.platform == "win32":
        yield from _app_paths("chrome.exe")
        yield from _app_paths("msedge.exe")
        # A Chromium build registers the same key as Chrome, so it can only be found by where it installs.
        yield str(Path(os.environ.get("LOCALAPPDATA", "")) / "Chromium" / "Application" / "chrome.exe")
    elif sys.platform == "darwin":
        yield "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        yield "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
        yield "/Applications/Chromium.app/Contents/MacOS/Chromium"
    else:
        # The browsers themselves come first: the launcher scripts on the PATH redirect the standard streams.
        yield "/opt/google/chrome/chrome"
        yield from map(shutil.which, ("google-chrome-stable", "google-chrome"))
        yield "/opt/microsoft/msedge/msedge"
        yield from map(shutil.which, ("microsoft-edge-stable", "microsoft-edge"))
    yield from map(shutil.which, ("chromium", "chromium-browser"))


def _browser_environment() -> dict[str, str]:
    """Return the environment for the browser, without what a frozen executable adds for its own libraries."""
    environment = dict(os.environ)
    if getattr(sys, "frozen", False):
        # PyInstaller puts its folder first on this path, and the browser must load its own libraries.
        original = environment.pop("LD_LIBRARY_PATH_ORIG", None)
        if original is None:
            environment.pop("LD_LIBRARY_PATH", None)
        else:
            environment["LD_LIBRARY_PATH"] = original
    return environment


def _start(program: str, profile: Path, log: BinaryIO, commands_read: int, answers_write: int) -> _Process:
    """Start the browser, which reads commands from the first pipe and writes its answers to the second."""
    arguments = [program, *BROWSER_SWITCHES, f"--user-data-dir={profile}"]
    if sys.platform == "win32":
        # Imported here because the module exists only on Windows.
        import msvcrt

        handles = [msvcrt.get_osfhandle(commands_read), msvcrt.get_osfhandle(answers_write)]
        for handle in handles:
            os.set_handle_inheritable(handle, True)
        # Only these two handles reach the browser, and it is told which they are.
        popen = subprocess.Popen(
            [*arguments, f"--remote-debugging-io-pipes={handles[0]},{handles[1]}", "about:blank"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=log,
            startupinfo=subprocess.STARTUPINFO(lpAttributeList={"handle_list": handles}),
        )
        return _Process(popen.pid, popen)
    # Imported here because the module exists only on Unix.
    import fcntl

    # The browser takes its pipes from file descriptors 3 and 4. The ends may already be 3 and 4, so they move
    # out of the way first, as copies that close when the browser starts, and are then copied onto 3 and 4.
    commands_child = fcntl.fcntl(commands_read, fcntl.F_DUPFD_CLOEXEC, 10)
    answers_child = fcntl.fcntl(answers_write, fcntl.F_DUPFD_CLOEXEC, 10)
    try:
        pid = os.posix_spawn(
            program,
            [*arguments, "about:blank"],
            _browser_environment(),
            file_actions=[
                (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
                (os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0),
                (os.POSIX_SPAWN_DUP2, log.fileno(), 2),
                (os.POSIX_SPAWN_DUP2, commands_child, 3),
                (os.POSIX_SPAWN_DUP2, answers_child, 4),
            ],
            setpgroup=0,
        )
    finally:
        os.close(commands_child)
        os.close(answers_child)
    return _Process(pid, None)


def _check_document(document: DevToolsMessage | None, max_page_size_mib: int) -> None:
    """Apply a plain fetch's rules to the response for the page's own document."""
    if document is None:
        raise RemoteFetchError("Malformed or unavailable response: the browser reported no response.")
    response = document["response"]
    status = response["status"]
    if not 200 <= status < 300:
        raise RemoteFetchError(f"Final response returned HTTP {status}.")
    headers = {name.lower(): value for name, value in response.get("headers", {}).items()}
    # As a plain fetch does, and not by the type that the browser works out for itself.
    message = Message()
    if "content-type" in headers:
        message["Content-Type"] = headers["content-type"]
    content_type = message.get_content_type().lower()
    if content_type not in downloader.ALLOWED_MEDIA_TYPES:
        raise RemoteFetchError(
            f"Final response must be text/html or application/xhtml+xml (got {content_type})."
        )
    declared_size = headers.get("content-length", "")
    if declared_size.isdigit() and int(declared_size) > max_page_size_mib * _BYTES_PER_MIB:
        raise RemoteFetchError(
            f"Response declares {declared_size} bytes, exceeding the {max_page_size_mib} MiB limit."
        )


def _read_page(browser: _Browser, url: str, max_page_size_mib: int, deadline: float) -> tuple[str, str]:
    """Load a URL, let the page's scripts run, and return the address that the browser ends on and the page's markup."""
    page = _Page(browser, deadline)
    page.attach()
    navigation = page.call("Page.navigate", url=url)
    if navigation.get("errorText"):
        raise page.navigation_failure(navigation)
    _check_document(page.document, max_page_size_mib)
    # The page's timers run fast, and its clock stands still while a request is under way.
    page.call(
        "Emulation.setVirtualTimePolicy",
        policy="pauseIfNetworkFetchesPending",
        budget=VIRTUAL_TIME_BUDGET_MILLISECONDS,
    )
    page.wait_until_time_is_up()
    _check_document(page.document, max_page_size_mib)
    assert page.document is not None
    try:
        body = page.call("Network.getResponseBody", requestId=page.document["requestId"])
    except _ProtocolError:
        # The browser has let go of a body that it no longer needs. Only a body that it has and finds empty counts.
        body = {"body": "unknown"}
    if body.get("body") == "":
        raise RemoteFetchError("Final HTML response body is empty.")
    result = page.call("Runtime.evaluate", expression=_READ_DOCUMENT, returnByValue=True)
    if "exceptionDetails" in result:
        raise RemoteFetchError("Malformed or unavailable response: the page could not be read.")
    final_url, markup = result["result"]["value"]
    return final_url, markup


def _remove_folder(folder: Path) -> None:
    """Remove the folder that a browser used, which its last processes may hold open for a moment on Windows."""
    for _ in range(20):
        try:
            shutil.rmtree(folder)
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.1)
        else:
            return
    shutil.rmtree(folder, ignore_errors=True)


def find_browser() -> str:
    """Return the browser to use: SITE2MD_BROWSER if it is set, or else Chrome, Edge or Chromium."""
    configured = os.environ.get("SITE2MD_BROWSER")
    if configured:
        program = shutil.which(configured)
        if program is None:
            raise RemoteFetchError(f"SITE2MD_BROWSER names '{configured}', which is not a program.")
        return program
    for candidate in _candidates():
        if candidate and Path(candidate).is_file():
            return candidate
    raise RemoteFetchError(
        "No Chrome, Edge or Chromium found. Set SITE2MD_BROWSER to the path of a Chromium-based browser."
    )


def fetch_with_browser(url: str, *, max_page_size_mib: int, content_path: Path) -> RemotePage:
    """Read one page from an installed browser after its scripts have run, under a plain fetch's rules."""
    program = find_browser()
    folder = Path(tempfile.mkdtemp(prefix=_FOLDER_PREFIX))
    try:
        deadline = time.monotonic() + downloader.REQUEST_TIMEOUT_SECONDS
        browser = _Browser(program, folder)
        try:
            final_url, markup = _read_page(browser, url, max_page_size_mib, deadline)
        except TimeoutError:
            raise RemoteFetchError("Malformed or unavailable response: timed out") from None
        except _PipeClosed:
            reason = browser.stopped_reason()
            raise RemoteFetchError(
                f"The browser stopped before the page was read{f': {reason}' if reason else '.'}"
            ) from None
        except _ProtocolError as error:
            raise RemoteFetchError(f"Malformed or unavailable response: {error}") from error
        finally:
            browser.close()
    finally:
        _remove_folder(folder)

    content = markup.encode("utf-8")
    max_bytes = max_page_size_mib * _BYTES_PER_MIB
    if len(content) > max_bytes:
        raise RemoteFetchError(
            f"Response exceeded the {max_page_size_mib} MiB limit while streaming.",
            bytes_received=len(content),
            reached_limit="page",
        )
    content_path.write_bytes(content)
    # The page comes out of the browser as text, so it is UTF-8 whatever its <meta charset> says.
    return RemotePage(
        content_path=content_path,
        source_url=final_url,
        encoding="utf-8",
        body_bytes=len(content),
        content=content,
    )
