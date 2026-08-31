"""Orchestrate one remote build from request through atomic destination replacement."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from site2md.converter import convert_remote_page_to_markdown
from site2md.downloader import (
    DEFAULT_MAX_PAGE_SIZE_MIB,
    RemoteFetchError,
    RemoteMode,
    fetch_remote,
)

RemoteBuildStage = Literal[
    "validation",
    "fetch",
    "conversion",
    "destination",
    "cleanup",
]


@dataclass(frozen=True)
class RemoteBuildRequest:
    """All caller-supplied information needed to build one remote document."""

    entry_url: str
    destination: Path
    mode: RemoteMode = "page"
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
    max_page_size_mib = _validate_request(request)
    workspace = Path(tempfile.mkdtemp(prefix="site2md_remote_"))
    staged_destination: Path | None = None

    try:
        try:
            page = fetch_remote(
                request.entry_url,
                request.mode,
                max_page_size_mib=max_page_size_mib,
                content_path=workspace / "page.html",
            )
        except RemoteFetchError as error:
            raise RemoteBuildError(str(error), stage="fetch") from error

        try:
            markdown = convert_remote_page_to_markdown(page)
            converted_path = workspace / "converted.md"
            converted_path.write_text(
                f"{markdown}\n\n---\n\n",
                encoding="utf-8",
            )
        except Exception as error:
            raise RemoteBuildError(str(error), stage="conversion") from error

        try:
            staged_destination = _stage_destination(
                converted_path,
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
            fetched=1,
            skipped=0,
            failed=0,
            warnings=(),
            reached_limits=(),
            retained_workspace=workspace if request.keep_temp else None,
        )
    except RemoteBuildError as error:
        if request.keep_temp:
            error.retained_workspace = workspace
        raise
    finally:
        if staged_destination is not None:
            try:
                staged_destination.unlink(missing_ok=True)
            except OSError:
                pass
        if not request.keep_temp and workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)


def _validate_request(request: RemoteBuildRequest) -> int:
    """Validate page-mode options before creating storage or making a request."""
    parsed_url = urlsplit(request.entry_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise RemoteBuildError(
            "Remote input must be an HTTP(S) URL.",
            stage="validation",
        )
    if request.mode != "page":
        raise RemoteBuildError(
            f"Unsupported remote mode: {request.mode}",
            stage="validation",
        )

    max_page_size_mib = request.max_page_size_mib or DEFAULT_MAX_PAGE_SIZE_MIB
    if request.max_page_size_mib is not None and request.max_page_size_mib <= 0:
        raise RemoteBuildError(
            "--max-page-size-mib must be a positive integer.",
            stage="validation",
        )
    return max_page_size_mib


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
