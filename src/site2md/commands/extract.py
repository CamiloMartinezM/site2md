"""Implement the extract command."""

from __future__ import annotations

import ctypes
import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import cyclopts

from site2md.extraction import ExtractionError
from site2md.extraction import extract as extract_markdown


def _extract_failure(message: str) -> NoReturn:
    """Report one concise extraction-command failure."""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


@contextmanager
def _discard_provider_output() -> Iterator[None]:
    """Keep provider writes away from the command's public output streams."""
    streams = (sys.stdout, sys.stderr)
    for stream in streams:
        stream.flush()

    redirected: list[tuple[int, int]] = []
    with tempfile.TemporaryFile() as sink:
        try:
            for stream in streams:
                descriptor = stream.fileno()
                saved_descriptor = os.dup(descriptor)
                redirected.append((descriptor, saved_descriptor))
                os.dup2(sink.fileno(), descriptor)
            yield
        finally:
            try:
                try:
                    # Windows has no CDLL(None); Python and its extensions share the UCRT there.
                    c_runtime = ctypes.CDLL("ucrtbase" if sys.platform == "win32" else None)
                    c_runtime.fflush(None)
                except (AttributeError, OSError, TypeError):  # no loadable C runtime: best effort
                    pass
                for stream in streams:
                    try:
                        stream.flush()
                    except (OSError, ValueError):
                        pass
            finally:
                # Restore even if flushing failed, or later errors would vanish into the sink.
                for descriptor, saved_descriptor in reversed(redirected):
                    os.dup2(saved_descriptor, descriptor)
                    os.close(saved_descriptor)


def _write_standard_output(contents: bytes) -> None:
    """Write all bytes and report sink failures without deferred flush errors.

    Bytes already accepted by a stream cannot be rolled back if a later write fails.
    """
    remaining = memoryview(contents)
    while remaining:
        written = os.write(sys.stdout.fileno(), remaining)
        if written == 0:
            raise OSError("standard output accepted no bytes")
        remaining = remaining[written:]


def _write_atomic(destination: Path, contents: bytes) -> None:
    """Replace a destination only after writing and flushing complete contents."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(contents)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def extract_markdown_file(
    extractor_id: str,
    markdown_path: Path | None,
    *,
    output: Path | None,
    entry_points_only: bool,
    values_only: bool,
) -> None:
    """Extract from a Markdown file, or from standard input when the path is None, and write the result.

    Every failure reports one message on standard error and exits with status 1. The extract
    command and build --extract share this, so both produce the same bytes.
    """
    try:
        if markdown_path is None:
            input_bytes = sys.stdin.buffer.read()
        else:
            input_bytes = markdown_path.read_bytes()
    except OSError as error:
        _extract_failure(f"could not read Markdown input: {error}")
    try:
        markdown = input_bytes.decode("utf-8")
    except UnicodeDecodeError:
        _extract_failure("Markdown input is not valid UTF-8")
    try:
        with _discard_provider_output():
            result = extract_markdown(
                markdown, extractor_id, entry_points_only=entry_points_only
            )
    except ExtractionError as error:
        for diagnostic in error.diagnostics:
            print(
                f"{diagnostic.severity}: {diagnostic.code}: {diagnostic.message}",
                file=sys.stderr,
            )
        raise SystemExit(1) from None
    except Exception as error:
        _extract_failure(f"extraction failed: {error}")
    try:
        serialize = result.values_to_json if values_only else result.to_json
        serialized = serialize().encode("utf-8")
    except Exception as error:
        _extract_failure(f"could not serialize extraction result: {error}")
    try:
        if output is None:
            _write_standard_output(serialized)
        else:
            _write_atomic(output, serialized)
    except OSError as error:
        _extract_failure(f"could not write extraction result: {error}")
    for diagnostic in result.payload["diagnostics"]:
        print(
            f"warning: {diagnostic['code']}: {diagnostic['message']}",
            file=sys.stderr,
        )


def extract(
    extractor_id: str,
    input_source: Annotated[
        str, cyclopts.Parameter(allow_leading_hyphen=True)
    ],
    *,
    output: Path | None = None,
    entry_points_only: bool = False,
    values_only: bool = False,
) -> None:
    """Extract structured records from a Markdown file or standard input.

    Args:
        values_only: Write only a JSON array of the record values, in record order. This drops
            the provenance, the Extractor, provider and record schema identity, the input digest
            and the source sections.
        entry_points_only: Look up the Extractor faster by skipping installed distributions
            that declare no Extractor entry point. Extract then doesn't notice a distribution
            that ships a manifest without an entry point, though site2md extractors still
            reports it.
    """
    if output is not None and not output.parent.is_dir():
        _extract_failure(f"output folder does not exist: {output.parent}")
    extract_markdown_file(
        extractor_id,
        None if input_source == "-" else Path(input_source),
        output=output,
        entry_points_only=entry_points_only,
        values_only=values_only,
    )
