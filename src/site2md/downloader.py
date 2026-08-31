"""Remote page retrieval for site2md."""

from __future__ import annotations

import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.client import HTTPMessage
from pathlib import Path
from typing import IO, Literal

RemoteMode = Literal["page", "follow"]
DEFAULT_MAX_PAGE_SIZE_MIB = 25
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "site2md/0.3.0"
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
    ) -> None:
        super().__init__(message)
        self.bytes_received = bytes_received
        self.reached_limit = reached_limit


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
) -> RemotePage:
    """Fetch remote content using the selected implemented mode."""
    owns_workspace = content_path is None
    if content_path is None:
        content_path = Path(tempfile.mkdtemp(prefix="site2md_page_")) / "page.html"
    try:
        if mode in {"page", "follow"}:
            return _fetch_page(
                url,
                max_page_size_mib=max_page_size_mib,
                max_body_bytes=max_body_bytes,
                content_path=content_path,
            )
        raise ValueError(f"Unsupported remote mode: {mode}")
    except BaseException:
        if owns_workspace:
            shutil.rmtree(content_path.parent, ignore_errors=True)
        raise


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects except HTTPS-to-HTTP downgrades."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        old_scheme = urllib.parse.urlsplit(req.full_url).scheme.lower()
        new_scheme = urllib.parse.urlsplit(newurl).scheme.lower()
        if old_scheme == "https" and new_scheme == "http":
            raise RemoteFetchError("Refusing HTTPS-to-HTTP redirect downgrade.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_page(
    url: str,
    *,
    max_page_size_mib: int,
    max_body_bytes: int | None,
    content_path: Path,
) -> RemotePage:
    """Fetch one HTML document without following links from its content."""
    page_max_bytes = max_page_size_mib * _BYTES_PER_MIB
    max_bytes = page_max_bytes
    reached_limit: Literal["page", "aggregate"] = "page"
    if max_body_bytes is not None and max_body_bytes <= max_bytes:
        max_bytes = max_body_bytes
        reached_limit = "aggregate"
    total = 0

    try:
        opener = urllib.request.build_opener(_SafeRedirectHandler)
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

            declared_size = response.headers.get("Content-Length")
            if declared_size is not None:
                try:
                    content_length = int(declared_size)
                except ValueError as error:
                    raise RemoteFetchError("Response Content-Length is malformed.") from error
                if content_length > max_bytes:
                    if reached_limit == "aggregate":
                        message = "Response exceeds the remaining aggregate content budget."
                    else:
                        message = (
                            f"Response declares {content_length} bytes, exceeding the "
                            f"{max_page_size_mib} MiB limit."
                        )
                    raise RemoteFetchError(
                        message,
                        reached_limit=reached_limit,
                    )

            with content_path.open("wb") as output:
                while True:
                    chunk = response.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        if reached_limit == "aggregate":
                            message = "Response exceeded the aggregate content budget."
                        else:
                            message = (
                                f"Response exceeded the {max_page_size_mib} MiB limit "
                                "while streaming."
                            )
                        raise RemoteFetchError(
                            message,
                            bytes_received=total,
                            reached_limit=reached_limit,
                        )
                    output.write(chunk)

            if total == 0:
                raise RemoteFetchError("Final HTML response body is empty.")

            return RemotePage(
                content_path=content_path,
                source_url=response.geturl(),
                encoding=response.headers.get_content_charset(),
                body_bytes=total,
            )
    except RemoteFetchError:
        raise
    except urllib.error.HTTPError as error:
        raise RemoteFetchError(
            f"Final response returned HTTP {error.code}.",
            bytes_received=total,
        ) from error
    except Exception as error:
        raise RemoteFetchError(
            f"Malformed or unavailable response: {error}",
            bytes_received=total,
        ) from error
