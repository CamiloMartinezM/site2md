"""Extract records from a Markdown file or standard input and write the result."""

from __future__ import annotations

import ctypes
import os
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

from site2md.extraction import ExtractionError
from site2md.extraction import extract as extract_markdown


class FileExtractionError(Exception):
    """Report a failed extraction as the lines that tell the user why."""

    def __init__(self, lines: Sequence[str]) -> None:
        super().__init__("\n".join(lines))
        self.lines = tuple(lines)


def _fail(message: str) -> NoReturn:
    """Raise a failure that reports one concise message."""
    raise FileExtractionError([f"error: {message}"])


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
) -> list[str]:
    """Extract from a Markdown file, or from standard input when the path is None, and write the result.

    Return the warning lines to print on standard error. Raise FileExtractionError, whose lines
    the caller prints, when any step fails. The extract command and build --extract share this,
    so both produce the same bytes.
    """
    try:
        if markdown_path is None:
            input_bytes = sys.stdin.buffer.read()
        else:
            input_bytes = markdown_path.read_bytes()
    except OSError as error:
        _fail(f"could not read Markdown input: {error}")
    try:
        markdown = input_bytes.decode("utf-8")
    except UnicodeDecodeError:
        _fail("Markdown input is not valid UTF-8")
    try:
        with _discard_provider_output():
            result = extract_markdown(
                markdown, extractor_id, entry_points_only=entry_points_only
            )
    except ExtractionError as error:
        raise FileExtractionError(
            [
                f"{diagnostic.severity}: {diagnostic.code}: {diagnostic.message}"
                for diagnostic in error.diagnostics
            ]
        ) from None
    except Exception as error:
        _fail(f"extraction failed: {error}")
    try:
        serialize = result.values_to_json if values_only else result.to_json
        serialized = serialize().encode("utf-8")
    except Exception as error:
        _fail(f"could not serialize extraction result: {error}")
    try:
        if output is None:
            _write_standard_output(serialized)
        else:
            _write_atomic(output, serialized)
    except OSError as error:
        _fail(f"could not write extraction result: {error}")
    return [
        f"warning: {diagnostic['code']}: {diagnostic['message']}"
        for diagnostic in result.payload["diagnostics"]
    ]
