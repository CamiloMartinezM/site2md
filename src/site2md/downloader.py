"""Remote page retrieval for site2md."""

from __future__ import annotations

import io
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from email.message import Message
from http.client import HTTPMessage
from pathlib import Path
from typing import IO, Literal

RemoteMode = Literal["page", "follow", "site"]
DEFAULT_MAX_PAGE_SIZE_MIB = 25
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "site2md/0.4.0"
ROBOTS_MAX_BYTES = 512 * 1024
_BYTES_PER_MIB = 1024 * 1024
_CHUNK_SIZE = 64 * 1024
_ALLOWED_MEDIA_TYPES = {"text/html", "application/xhtml+xml"}


class RemoteFetchError(RuntimeError):
    """Raised when a remote page cannot be safely fetched."""

    def __init__(
        self,
        message: str,
        *,
        bytes_received: int = 0,
        reached_limit: Literal["page", "aggregate"] | None = None,
        policy_rejection: Literal["origin", "robots"] | None = None,
    ) -> None:
        super().__init__(message)
        self.bytes_received = bytes_received
        self.reached_limit = reached_limit
        self.policy_rejection = policy_rejection


@dataclass
class TraversalRequestPolicy:
    """Enforce one concrete traversal origin, robots policy, and request delay."""

    origin: tuple[str, str, int]
    robots: urllib.robotparser.RobotFileParser
    delay_seconds: float
    last_request_at: float | None = None

    @classmethod
    def for_entry(
        cls,
        entry_url: str,
        robots: urllib.robotparser.RobotFileParser,
    ) -> TraversalRequestPolicy:
        """Create the concrete request policy for one traversal origin."""
        return cls(
            origin=url_origin(entry_url),
            robots=robots,
            delay_seconds=_request_delay(robots),
        )

    def prepare_request(self, url: str) -> None:
        """Reject an out-of-policy URL and pace an accepted network request."""
        if url_origin(url) != self.origin:
            raise RemoteFetchError(
                f"Child redirect left the traversal origin: {url}.",
                policy_rejection="origin",
            )
        if not self.robots.can_fetch(USER_AGENT, url):
            raise RemoteFetchError(
                f"Robots policy disallows {url}.",
                policy_rejection="robots",
            )
        if self.last_request_at is not None:
            elapsed = time.monotonic() - self.last_request_at
            if elapsed < self.delay_seconds:
                time.sleep(self.delay_seconds - elapsed)
        self.last_request_at = time.monotonic()


@dataclass
class _ResponseAccounting:
    """Enforce per-response and aggregate limits across one redirect chain."""

    page_max_bytes: int
    aggregate_max_bytes: int | None
    bytes_received: int = 0

    def read(
        self,
        response: IO[bytes],
        headers: HTTPMessage | Message[str, str],
        output: IO[bytes] | None = None,
    ) -> int:
        """Read and count one response body, optionally retaining its bytes."""
        max_bytes = self.page_max_bytes
        reached_limit: Literal["page", "aggregate"] = "page"
        if self.aggregate_max_bytes is not None:
            remaining = self.aggregate_max_bytes - self.bytes_received
            if remaining <= max_bytes:
                max_bytes = max(remaining, 0)
                reached_limit = "aggregate"

        declared_size = headers.get("Content-Length")
        if declared_size is not None:
            try:
                content_length = int(declared_size)
            except ValueError as error:
                raise RemoteFetchError(
                    "Response Content-Length is malformed.",
                    bytes_received=self.bytes_received,
                ) from error
            if content_length > max_bytes:
                raise self._limit_error(reached_limit, declared_size=content_length)

        response_bytes = 0
        while True:
            chunk = response.read(_CHUNK_SIZE)
            if not chunk:
                break
            response_bytes += len(chunk)
            self.bytes_received += len(chunk)
            if response_bytes > max_bytes:
                raise self._limit_error(reached_limit)
            if output is not None:
                output.write(chunk)
        return response_bytes

    def _limit_error(
        self,
        reached_limit: Literal["page", "aggregate"],
        *,
        declared_size: int | None = None,
    ) -> RemoteFetchError:
        """Describe the response limit that stopped this redirect chain."""
        if reached_limit == "aggregate":
            if declared_size is None:
                message = "Response exceeded the aggregate content budget."
            else:
                message = "Response exceeds the remaining aggregate content budget."
        else:
            page_size_mib = self.page_max_bytes // _BYTES_PER_MIB
            if declared_size is None:
                message = (
                    f"Response exceeded the {page_size_mib} MiB limit while streaming."
                )
            else:
                message = (
                    f"Response declares {declared_size} bytes, exceeding the "
                    f"{page_size_mib} MiB limit."
                )
        return RemoteFetchError(
            message,
            bytes_received=self.bytes_received,
            reached_limit=reached_limit,
        )


@dataclass(frozen=True)
class RemotePage:
    """An HTML document and the final URL from which it was fetched."""

    content_path: Path
    source_url: str
    encoding: str | None
    body_bytes: int


def fetch_remote(
    url: str,
    mode: RemoteMode = "page",
    *,
    max_page_size_mib: int = DEFAULT_MAX_PAGE_SIZE_MIB,
    max_body_bytes: int | None = None,
    content_path: Path | None = None,
    request_policy: TraversalRequestPolicy | None = None,
) -> RemotePage:
    """Fetch remote content using the selected implemented mode."""
    owns_workspace = content_path is None
    if content_path is None:
        content_path = Path(tempfile.mkdtemp(prefix="site2md_page_")) / "page.html"
    try:
        if mode in {"page", "follow", "site"}:
            return _fetch_page(
                url,
                max_page_size_mib=max_page_size_mib,
                max_body_bytes=max_body_bytes,
                content_path=content_path,
                request_policy=request_policy,
            )
        raise ValueError(f"Unsupported remote mode: {mode}")
    except BaseException:
        if owns_workspace:
            shutil.rmtree(content_path.parent, ignore_errors=True)
        raise


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Account and authorize each redirect before making its next request."""

    def __init__(
        self,
        accounting: _ResponseAccounting,
        request_policy: TraversalRequestPolicy | None = None,
        content_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.accounting = accounting
        self.request_policy = request_policy
        self.content_path = content_path

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        if self.content_path is None:
            self.accounting.read(fp, headers)
        else:
            with self.content_path.open("wb") as output:
                self.accounting.read(fp, headers, output)
        old_scheme = urllib.parse.urlsplit(req.full_url).scheme.lower()
        new_scheme = urllib.parse.urlsplit(newurl).scheme.lower()
        if old_scheme == "https" and new_scheme == "http":
            raise RemoteFetchError("Refusing HTTPS-to-HTTP redirect downgrade.")
        if self.request_policy is not None:
            self.request_policy.prepare_request(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _RobotsRedirectHandler(_SafeRedirectHandler):
    """Apply one bounded body budget across a robots redirect chain."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if self.accounting.bytes_received >= ROBOTS_MAX_BYTES:
            raise RemoteFetchError(
                "Robots policy exhausted its response-body budget during redirect.",
                bytes_received=self.accounting.bytes_received,
                reached_limit="aggregate",
            )
        return redirected


def fetch_robots_policy(
    entry_url: str,
) -> tuple[urllib.robotparser.RobotFileParser | None, str | None]:
    """Fetch one robots policy within a shared redirect-chain body budget."""
    parsed = urllib.parse.urlsplit(entry_url)
    robots_url = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, "/robots.txt", "", "")
    )
    accounting = _ResponseAccounting(ROBOTS_MAX_BYTES, ROBOTS_MAX_BYTES)
    opener = urllib.request.build_opener(_RobotsRedirectHandler(accounting))
    request = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body_buffer = io.BytesIO()
            accounting.read(response, response.headers, body_buffer)
            body = body_buffer.getvalue()
    except RemoteFetchError as error:
        if error.reached_limit is not None:
            return None, (
                "Robots policy exceeded the 512 KiB limit; child traversal stopped."
            )
        return None, f"Robots policy was unavailable ({error}); child traversal stopped."
    except urllib.error.HTTPError as error:
        if 400 <= error.code < 500:
            body = b""
        else:
            return None, (
                f"Robots policy was unavailable (HTTP {error.code}); "
                "child traversal stopped."
            )
    except Exception as error:
        return None, (
            f"Robots policy was unavailable ({error}); child traversal stopped."
        )

    policy = urllib.robotparser.RobotFileParser(robots_url)
    policy.parse(body.decode("utf-8", errors="replace").splitlines())
    return policy, None


def _fetch_page(
    url: str,
    *,
    max_page_size_mib: int,
    max_body_bytes: int | None,
    content_path: Path,
    request_policy: TraversalRequestPolicy | None,
) -> RemotePage:
    """Fetch one HTML document without following links from its content."""
    page_max_bytes = max_page_size_mib * _BYTES_PER_MIB
    accounting = _ResponseAccounting(page_max_bytes, max_body_bytes)

    try:
        if request_policy is not None:
            request_policy.prepare_request(url)
        opener = urllib.request.build_opener(
            _SafeRedirectHandler(accounting, request_policy, content_path)
        )
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", response.getcode())
            if status < 200 or status >= 300:
                raise RemoteFetchError(f"Final response returned HTTP {status}.")

            content_type = response.headers.get_content_type().lower()
            if content_type not in _ALLOWED_MEDIA_TYPES:
                raise RemoteFetchError(
                    "Final response must be text/html or application/xhtml+xml "
                    f"(got {content_type})."
                )

            with content_path.open("wb") as output:
                final_body_bytes = accounting.read(
                    response,
                    response.headers,
                    output,
                )

            if final_body_bytes == 0:
                raise RemoteFetchError("Final HTML response body is empty.")

            return RemotePage(
                content_path=content_path,
                source_url=response.geturl(),
                encoding=response.headers.get_content_charset(),
                body_bytes=accounting.bytes_received,
            )
    except RemoteFetchError as error:
        error.bytes_received = max(error.bytes_received, accounting.bytes_received)
        raise
    except urllib.error.HTTPError as error:
        accounting.read(error, error.headers)
        raise RemoteFetchError(
            f"Final response returned HTTP {error.code}.",
            bytes_received=accounting.bytes_received,
        ) from error
    except Exception as error:
        raise RemoteFetchError(
            f"Malformed or unavailable response: {error}",
            bytes_received=accounting.bytes_received,
        ) from error


def url_origin(url: str) -> tuple[str, str, int]:
    """Return the normalized scheme, host, and effective port for one URL."""
    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or parsed.hostname is None:
        raise RemoteFetchError(f"Redirect target is not an HTTP(S) URL: {url}.")
    default_port = 443 if scheme == "https" else 80
    return scheme, parsed.hostname.lower(), parsed.port or default_port


def _request_delay(policy: urllib.robotparser.RobotFileParser) -> float:
    """Return the greatest applicable publisher-aware child request delay."""
    crawl_delay = policy.crawl_delay(USER_AGENT) or policy.crawl_delay("*") or 0
    request_rate = policy.request_rate(USER_AGENT) or policy.request_rate("*")
    rate_delay = 0.0
    if request_rate is not None and request_rate.requests > 0:
        rate_delay = request_rate.seconds / request_rate.requests
    return max(1.0, float(crawl_delay), rate_delay)
