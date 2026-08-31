"""Orchestrate one remote build from request through atomic destination replacement."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import soupsieve
from bs4 import BeautifulSoup, Tag

from site2md.converter import convert_remote_page_to_markdown
from site2md.downloader import (
    DEFAULT_MAX_PAGE_SIZE_MIB,
    USER_AGENT,
    RemoteFetchError,
    RemoteMode,
    RemotePage,
    _TraversalRequestPolicy,
    fetch_remote,
)

RemoteBuildStage = Literal[
    "validation",
    "fetch",
    "conversion",
    "destination",
    "cleanup",
    "interruption",
    "unexpected",
]
DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_TOTAL_SIZE_MIB = 250
_BYTES_PER_MIB = 1024 * 1024


@dataclass(frozen=True)
class RemoteBuildRequest:
    """All caller-supplied information needed to build one remote document."""

    entry_url: str
    destination: Path
    mode: RemoteMode = "page"
    follow_selectors: tuple[str, ...] = ()
    max_pages: int | None = None
    max_depth: int | None = None
    include_query: bool = False
    max_total_size_mib: int | None = None
    max_page_size_mib: int | None = None
    keep_temp: bool = False


@dataclass(frozen=True)
class RemoteBuildSummary:
    """Observable outcome of a completed remote build."""

    fetched: int
    skipped: int
    failed: int
    warnings: tuple[str, ...]
    reached_limits: tuple[str, ...]
    retained_workspace: Path | None


class RemoteBuildError(RuntimeError):
    """Report a fatal remote-build stage without coupling to a console."""

    def __init__(
        self,
        message: str,
        *,
        stage: RemoteBuildStage,
        retained_workspace: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.retained_workspace = retained_workspace


def build_remote(request: RemoteBuildRequest) -> RemoteBuildSummary:
    """Build one remote document and atomically replace its destination."""
    max_page_size_mib, max_pages, max_depth, max_total_size_mib = (
        _validate_request(request)
    )
    max_total_bytes = (
        max_total_size_mib * _BYTES_PER_MIB
        if request.mode in {"follow", "site"}
        else None
    )
    workspace = Path(tempfile.mkdtemp(prefix="site2md_remote_"))
    staged_destination: Path | None = None
    entry_path = workspace / "page.html"
    index_pages: list[dict[str, object]] = [
        {
            "requested_url": request.entry_url,
            "html": entry_path.name,
            "status": "pending",
        }
    ]

    try:
        _write_debugging_index(workspace, index_pages)
        try:
            page = fetch_remote(
                request.entry_url,
                request.mode,
                max_page_size_mib=max_page_size_mib,
                max_body_bytes=max_total_bytes,
                content_path=entry_path,
            )
        except RemoteFetchError as error:
            _record_fetch_failure(index_pages[0], entry_path, error)
            _write_debugging_index(workspace, index_pages)
            raise RemoteBuildError(str(error), stage="fetch") from error
        except BaseException as error:
            _record_fatal_fetch(index_pages[0], entry_path, error)
            _write_debugging_index(workspace, index_pages)
            raise

        index_pages[0]["source_url"] = page.source_url
        index_pages[0]["body_bytes"] = page.body_bytes
        index_pages[0]["stored_bytes"] = _stored_bytes(entry_path)
        index_pages[0]["status"] = "fetched"
        _write_debugging_index(workspace, index_pages)

        try:
            markdown = convert_remote_page_to_markdown(page)
            converted_path = workspace / "converted.md"
            converted_path.write_text(
                f"{markdown}\n\n---\n\n",
                encoding="utf-8",
            )
            index_pages[0]["markdown"] = "converted.md"
            index_pages[0]["status"] = "converted"
            _write_debugging_index(workspace, index_pages)
        except Exception as error:
            raise RemoteBuildError(str(error), stage="conversion") from error

        fragments = [converted_path]
        fetched = 1
        skipped = 0
        failed = 0
        warnings: list[str] = []
        reached_limits: list[str] = []
        total_received = page.body_bytes
        if request.mode in {"follow", "site"}:
            assert max_total_bytes is not None
            seen_sources = {_normalize_url(page.source_url)}
            admitted_urls = set(seen_sources)
            admitted_count = 1
            pending: list[tuple[str, int]] = []
            page_limit_reached = False

            def admit_targets(targets: list[str], depth: int) -> None:
                """Admit unique targets without exceeding traversal budgets."""
                nonlocal admitted_count, page_limit_reached
                if page_limit_reached:
                    return
                for target in targets:
                    if target in admitted_urls:
                        continue
                    if request.mode == "site" and depth > max_depth:
                        limit = f"depth ({max_depth})"
                        if limit not in reached_limits:
                            reached_limits.append(limit)
                        continue
                    if admitted_count >= max_pages:
                        reached_limits.append(f"page count ({max_pages})")
                        page_limit_reached = True
                        break
                    admitted_urls.add(target)
                    admitted_count += 1
                    pending.append((target, depth))

            if request.mode == "follow":
                targets = _select_follow_targets(page, request.follow_selectors)
            else:
                targets = _discover_site_targets(page, request.include_query)
            admit_targets(targets, 1)
            if pending:
                policy, policy_warning = _fetch_robots_policy(page.source_url)
            else:
                policy, policy_warning = None, None
            if policy_warning is not None:
                warnings.append(policy_warning)
                skipped += len(pending)
            elif policy is not None:
                request_policy = _TraversalRequestPolicy(
                    origin=_origin(page.source_url),
                    robots=policy,
                    delay_seconds=_request_delay(policy),
                )
                for index, (target, depth) in enumerate(pending, start=1):
                    index_entry: dict[str, object] = {
                        "requested_url": target,
                        "status": "pending",
                    }
                    index_pages.append(index_entry)
                    remaining_bytes = max_total_bytes - total_received
                    if remaining_bytes <= 0:
                        skipped += 1
                        index_entry["status"] = "skipped"
                        index_entry["detail"] = "aggregate content budget reached"
                        _write_debugging_index(workspace, index_pages)
                        reached_limits.append(
                            f"aggregate content ({max_total_size_mib} MiB)"
                        )
                        break
                    child_path = workspace / f"page-{index:04}.html"
                    index_entry["html"] = child_path.name
                    _write_debugging_index(workspace, index_pages)
                    try:
                        child = fetch_remote(
                            target,
                            request.mode,
                            max_page_size_mib=max_page_size_mib,
                            max_body_bytes=remaining_bytes,
                            content_path=child_path,
                            _request_policy=request_policy,
                        )
                    except RemoteFetchError as error:
                        total_received += error.bytes_received
                        _record_fetch_failure(index_entry, child_path, error)
                        if error.policy_rejection is not None:
                            skipped += 1
                            index_entry["status"] = "skipped"
                            index_entry["detail"] = str(error)
                            warnings.append(str(error))
                            _write_debugging_index(workspace, index_pages)
                            continue
                        index_entry["status"] = "failed"
                        index_entry["detail"] = str(error)
                        _write_debugging_index(workspace, index_pages)
                        if error.reached_limit == "aggregate":
                            reached_limits.append(
                                f"aggregate content ({max_total_size_mib} MiB)"
                            )
                            warnings.append(
                                f"Discarded incomplete child {target}: {error}"
                            )
                            break
                        failed += 1
                        warnings.append(f"Could not fetch {target}: {error}")
                        if total_received >= max_total_bytes:
                            reached_limits.append(
                                f"aggregate content ({max_total_size_mib} MiB)"
                            )
                            break
                        continue
                    except BaseException as error:
                        _record_fatal_fetch(index_entry, child_path, error)
                        _write_debugging_index(workspace, index_pages)
                        raise
                    total_received += child.body_bytes
                    index_entry["source_url"] = child.source_url
                    index_entry["body_bytes"] = child.body_bytes
                    index_entry["stored_bytes"] = _stored_bytes(child_path)
                    index_entry["status"] = "fetched"
                    final_url = _normalize_url(child.source_url)
                    if _origin(final_url) != _origin(page.source_url):
                        skipped += 1
                        warnings.append(
                            f"Child redirect left the traversal origin: {child.source_url}."
                        )
                        index_entry["status"] = "skipped"
                        index_entry["detail"] = "final URL left the traversal origin"
                        _write_debugging_index(workspace, index_pages)
                        continue
                    if final_url in seen_sources:
                        skipped += 1
                        index_entry["status"] = "skipped"
                        index_entry["detail"] = "final URL duplicated an earlier source"
                        _write_debugging_index(workspace, index_pages)
                        continue
                    seen_sources.add(final_url)
                    admitted_urls.add(final_url)
                    try:
                        child_markdown = convert_remote_page_to_markdown(child)
                    except Exception as error:
                        failed += 1
                        warnings.append(f"Could not convert {target}: {error}")
                        index_entry["status"] = "failed"
                        index_entry["detail"] = f"conversion failed: {error}"
                        _write_debugging_index(workspace, index_pages)
                        continue
                    child_converted = workspace / f"converted-{index:04}.md"
                    child_converted.write_text(
                        f"{child_markdown}\n\n---\n\n",
                        encoding="utf-8",
                    )
                    index_entry["markdown"] = child_converted.name
                    index_entry["status"] = "converted"
                    _write_debugging_index(workspace, index_pages)
                    fragments.append(child_converted)
                    fetched += 1
                    if request.mode == "site":
                        admit_targets(
                            _discover_site_targets(child, request.include_query),
                            depth + 1,
                        )

        document_path = workspace / "document.md"
        with document_path.open("wb") as document:
            for fragment in fragments:
                with fragment.open("rb") as source:
                    shutil.copyfileobj(source, document)

        try:
            staged_destination = _stage_destination(
                document_path,
                request.destination,
            )
        except OSError as error:
            raise RemoteBuildError(str(error), stage="destination") from error

        if not request.keep_temp:
            try:
                shutil.rmtree(workspace)
            except OSError as error:
                message = f"Could not remove temporary workspace: {error}"
                raise RemoteBuildError(message, stage="cleanup") from error

        try:
            os.replace(staged_destination, request.destination)
        except OSError as error:
            raise RemoteBuildError(str(error), stage="destination") from error
        staged_destination = None

        return RemoteBuildSummary(
            fetched=fetched,
            skipped=skipped,
            failed=failed,
            warnings=tuple(warnings),
            reached_limits=tuple(reached_limits),
            retained_workspace=workspace if request.keep_temp else None,
        )
    except BaseException as error:
        failure = _remote_build_failure(error)
        if request.keep_temp or (
            workspace.exists() and failure.stage == "cleanup"
        ):
            failure.retained_workspace = workspace
        elif workspace.exists():
            try:
                shutil.rmtree(workspace)
            except OSError as cleanup_error:
                message = (
                    f"{failure} Additionally, could not remove temporary workspace: "
                    f"{cleanup_error}"
                )
                failure = RemoteBuildError(
                    message,
                    stage="cleanup",
                    retained_workspace=workspace,
                )
        if failure is error:
            raise
        raise failure from error
    finally:
        if staged_destination is not None:
            try:
                staged_destination.unlink(missing_ok=True)
            except OSError:
                pass


def _remote_build_failure(error: BaseException) -> RemoteBuildError:
    """Normalize every post-workspace failure for cleanup and CLI reporting."""
    if isinstance(error, RemoteBuildError):
        return error
    if isinstance(error, KeyboardInterrupt):
        return RemoteBuildError("Remote build interrupted.", stage="interruption")
    return RemoteBuildError(
        f"Unexpected remote build failure: {error}",
        stage="unexpected",
    )


def _validate_request(request: RemoteBuildRequest) -> tuple[int, int, int, int]:
    """Validate remote-mode options before storage or network access."""
    parsed_url = urlsplit(request.entry_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise RemoteBuildError(
            "Remote input must be an HTTP(S) URL.",
            stage="validation",
        )
    if request.mode not in {"page", "follow", "site"}:
        raise RemoteBuildError(
            f"Unsupported remote mode: {request.mode}",
            stage="validation",
        )

    if request.mode != "follow" and request.follow_selectors:
        raise RemoteBuildError(
            "--follow-selector can only be used with --mode follow.",
            stage="validation",
        )
    if request.mode == "page" and request.max_pages is not None:
        raise RemoteBuildError(
            "--max-pages can only be used with --mode follow or --mode site.",
            stage="validation",
        )
    if request.mode == "page" and request.max_total_size_mib is not None:
        raise RemoteBuildError(
            "--max-total-size-mib can only be used with --mode follow or --mode site.",
            stage="validation",
        )
    if request.mode != "site" and request.max_depth is not None:
        raise RemoteBuildError(
            "--max-depth can only be used with --mode site.",
            stage="validation",
        )
    if request.mode != "site" and request.include_query:
        raise RemoteBuildError(
            "--include-query can only be used with --mode site.",
            stage="validation",
        )
    if request.mode == "follow" and not request.follow_selectors:
        raise RemoteBuildError(
            "--mode follow requires at least one --follow-selector.",
            stage="validation",
        )

    max_page_size_mib = request.max_page_size_mib or DEFAULT_MAX_PAGE_SIZE_MIB
    if request.max_page_size_mib is not None and request.max_page_size_mib <= 0:
        raise RemoteBuildError(
            "--max-page-size-mib must be a positive integer.",
            stage="validation",
        )
    max_pages = request.max_pages or DEFAULT_MAX_PAGES
    if request.max_pages is not None and request.max_pages <= 0:
        raise RemoteBuildError(
            "--max-pages must be a positive integer.",
            stage="validation",
        )
    max_depth = request.max_depth or DEFAULT_MAX_DEPTH
    if request.max_depth is not None and request.max_depth <= 0:
        raise RemoteBuildError(
            "--max-depth must be a positive integer.",
            stage="validation",
        )
    max_total_size_mib = (
        request.max_total_size_mib or DEFAULT_MAX_TOTAL_SIZE_MIB
    )
    if (
        request.max_total_size_mib is not None
        and request.max_total_size_mib <= 0
    ):
        raise RemoteBuildError(
            "--max-total-size-mib must be a positive integer.",
            stage="validation",
        )
    return max_page_size_mib, max_pages, max_depth, max_total_size_mib


def _select_follow_targets(page: RemotePage, selectors: tuple[str, ...]) -> list[str]:
    """Select unique eligible anchors in entry-document order."""
    try:
        compiled = tuple(soupsieve.compile(selector) for selector in selectors)
    except soupsieve.SelectorSyntaxError as error:
        raise RemoteBuildError(
            f"Invalid follow selector: {error}",
            stage="validation",
        ) from error

    soup = BeautifulSoup(
        page.content_path.read_bytes(),
        "html.parser",
        from_encoding=page.encoding,
    )
    base_url = page.source_url
    base_tag = soup.find("base", href=True)
    if isinstance(base_tag, Tag):
        base_href = base_tag.get("href")
        if isinstance(base_href, str):
            base_url = urljoin(page.source_url, base_href)

    targets: list[str] = []
    seen: set[str] = {_normalize_url(page.source_url)}
    entry_origin = _origin(page.source_url)
    for anchor in soup.find_all("a", href=True):
        if not any(selector.match(anchor) for selector in compiled):
            continue
        href = anchor.get("href")
        if not isinstance(href, str) or not href:
            continue
        try:
            target = _normalize_url(urljoin(base_url, href))
        except ValueError:
            continue
        if _origin(target) != entry_origin or target in seen:
            continue
        seen.add(target)
        targets.append(target)

    if not targets:
        raise RemoteBuildError(
            "Follow selectors matched no eligible same-origin anchors.",
            stage="validation",
        )
    return targets


def _discover_site_targets(page: RemotePage, include_query: bool) -> list[str]:
    """Discover unique eligible site targets in source-document order."""
    soup = BeautifulSoup(
        page.content_path.read_bytes(),
        "html.parser",
        from_encoding=page.encoding,
    )
    base_url = page.source_url
    base_tag = soup.find("base", href=True)
    if isinstance(base_tag, Tag):
        base_href = base_tag.get("href")
        if isinstance(base_href, str):
            base_url = urljoin(page.source_url, base_href)

    targets: list[str] = []
    seen: set[str] = {_normalize_url(page.source_url)}
    page_origin = _origin(page.source_url)
    for anchor in soup.find_all("a", href=True):
        rel = anchor.get("rel")
        rel_values = rel if isinstance(rel, list) else str(rel or "").split()
        if any(str(value).lower() == "nofollow" for value in rel_values):
            continue
        href = anchor.get("href")
        if not isinstance(href, str) or not href:
            continue
        try:
            target = _normalize_url(urljoin(base_url, href))
        except ValueError:
            continue
        if urlsplit(target).query and not include_query:
            continue
        if _origin(target) != page_origin or target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return targets


def _normalize_url(url: str) -> str:
    """Return deterministic HTTP(S) fetch identity for one URL."""
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("URL is not HTTP(S)")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("authenticated URLs are not supported")
    port = parsed.port
    host = parsed.hostname.lower()
    display_host = f"[{host}]" if ":" in host else host
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        display_host = f"{display_host}:{port}"
    return urlunsplit((scheme, display_host, parsed.path or "/", parsed.query, ""))


def _origin(url: str) -> tuple[str, str, int]:
    """Return a normalized scheme, host, and effective port origin."""
    parsed = urlsplit(_normalize_url(url))
    default_port = 443 if parsed.scheme == "https" else 80
    assert parsed.hostname is not None
    return parsed.scheme, parsed.hostname, parsed.port or default_port


def _fetch_robots_policy(
    entry_url: str,
) -> tuple[urllib.robotparser.RobotFileParser | None, str | None]:
    """Fetch robots policy once before child traversal."""
    parsed = urlsplit(_normalize_url(entry_url))
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    request = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(512 * 1024 + 1)
            if len(body) > 512 * 1024:
                return None, "Robots policy exceeded the 512 KiB limit; child traversal stopped."
    except urllib.error.HTTPError as error:
        if 400 <= error.code < 500:
            body = b""
        else:
            return None, f"Robots policy was unavailable (HTTP {error.code}); child traversal stopped."
    except Exception as error:
        return None, f"Robots policy was unavailable ({error}); child traversal stopped."

    policy = urllib.robotparser.RobotFileParser(robots_url)
    policy.parse(body.decode("utf-8", errors="replace").splitlines())
    return policy, None


def _request_delay(policy: urllib.robotparser.RobotFileParser) -> float:
    """Return the greatest applicable publisher-aware child request delay."""
    crawl_delay = policy.crawl_delay(USER_AGENT) or policy.crawl_delay("*") or 0
    request_rate = policy.request_rate(USER_AGENT) or policy.request_rate("*")
    rate_delay = 0.0
    if request_rate is not None and request_rate.requests > 0:
        rate_delay = request_rate.seconds / request_rate.requests
    return max(1.0, float(crawl_delay), rate_delay)


def _stage_destination(source: Path, destination: Path) -> Path:
    """Write a complete destination-side temporary file without replacing output."""
    temporary_path: Path | None = None
    try:
        with source.open("rb") as source_file, tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            shutil.copyfileobj(source_file, temporary_file)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        return temporary_path
    except Exception:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _write_debugging_index(
    workspace: Path,
    pages: list[dict[str, object]],
) -> None:
    """Atomically write the human-readable, explicitly unstable workspace index."""
    payload = {
        "notice": (
            "Human-readable debugging artifact; this format has no compatibility "
            "guarantees."
        ),
        "pages": pages,
    }
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=workspace,
            prefix=".index.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
            )
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.rename(workspace / "index.json")
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _record_fetch_failure(
    index_entry: dict[str, object],
    content_path: Path,
    error: RemoteFetchError,
) -> None:
    """Record a completed retrieval failure and any retained partial data."""
    index_entry["body_bytes"] = error.bytes_received
    index_entry["stored_bytes"] = _stored_bytes(content_path)
    index_entry["status"] = "failed"
    index_entry["detail"] = str(error)


def _record_fatal_fetch(
    index_entry: dict[str, object],
    content_path: Path,
    error: BaseException,
) -> None:
    """Record interruption or unexpected retrieval failure before propagation."""
    index_entry["stored_bytes"] = _stored_bytes(content_path)
    if isinstance(error, KeyboardInterrupt):
        index_entry["status"] = "interrupted"
        index_entry["detail"] = "retrieval interrupted"
    else:
        index_entry["status"] = "failed"
        index_entry["detail"] = f"unexpected retrieval failure: {error}"


def _stored_bytes(content_path: Path) -> int:
    """Return retained artifact size without obscuring its primary failure."""
    try:
        return content_path.stat().st_size
    except OSError:
        return 0
