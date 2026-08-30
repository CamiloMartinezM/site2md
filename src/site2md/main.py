"""Main entry point for the site2md CLI."""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import cyclopts
from rich.console import Console
from rich.progress import Progress

from site2md.converter import convert_html_to_markdown, convert_remote_page_to_markdown
from site2md.downloader import (
    DEFAULT_MAX_PAGE_SIZE_MIB,
    RemoteFetchError,
    RemoteMode,
    fetch_remote,
)
from site2md.extraction import ExtractionError, list_extractors
from site2md.extraction import extract as extract_markdown
from site2md.finder import find_html_files
from site2md.merger import merge_markdowns

app = cyclopts.App(name="site2md")
console = Console()


@app.command(name="extract")
def extract(
    extractor_id: str,
    input_source: Annotated[
        str, cyclopts.Parameter(allow_leading_hyphen=True)
    ],
    *,
    output: Path | None = None,
) -> None:
    """Extract structured records from a Markdown file or standard input."""
    try:
        if input_source == "-":
            input_bytes = sys.stdin.buffer.read()
        else:
            input_bytes = Path(input_source).read_bytes()
    except OSError as error:
        _extract_failure(f"could not read Markdown input: {error}")
    try:
        markdown = input_bytes.decode("utf-8")
    except UnicodeDecodeError:
        _extract_failure("Markdown input is not valid UTF-8")
    try:
        with _discard_provider_output():
            result = extract_markdown(markdown, extractor_id)
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
        serialized = result.to_json().encode("utf-8")
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
                ctypes.CDLL(None).fflush(None)
            except (AttributeError, OSError):
                pass
            for stream in streams:
                try:
                    stream.flush()
                except (OSError, ValueError):
                    pass
            for descriptor, saved_descriptor in reversed(redirected):
                os.dup2(saved_descriptor, descriptor)
                os.close(saved_descriptor)


def _write_standard_output(contents: bytes) -> None:
    """Write complete bytes without deferring errors to interpreter shutdown."""
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


def main() -> int:
    """Run the CLI with POSIX-compatible command-usage exit status."""
    try:
        app(exit_on_error=False)
    except cyclopts.CycloptsError:
        if sys.argv[1:2] == ["extract"]:
            return 2
        return 1
    return 0


@app.command(name="extractors")
def extractors() -> None:
    """List installed Extractors using static provider metadata."""
    headers = (
        "ID",
        "Status",
        "Provider",
        "Extractor version",
        "Record schema",
        "Details",
    )
    rows: list[tuple[str, ...]] = []
    for info in list_extractors():
        provider = f"{info.provider_distribution} {info.provider_version}"
        record_schema = ""
        if info.record_schema_id is not None:
            record_schema = info.record_schema_id
            if info.record_schema_version is not None:
                record_schema += f" {info.record_schema_version}"
        rows.append(
            (
                info.id,
                info.status,
                provider,
                info.implementation_version or "",
                record_schema,
                info.detail,
            )
        )
    widths = tuple(
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    )
    lines = [
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rows
    )
    console.print("\n".join(lines), markup=False, soft_wrap=True)


@app.command(name="build")
def build(
    input_source: str,
    *,
    output: Path = Path("complete_manual.md"),
    keep_temp: bool = False,
    mode: RemoteMode = "page",
    max_page_size_mib: int | None = None,
) -> None:
    """Build a single Markdown file from a local HTML directory or remote page.

    Args:
        input_source: Directory containing HTML files or an HTTP(S) URL.
        output: Path where the result Markdown should be saved.
        keep_temp: If True, temporary remote page data is not deleted.
        mode: Scope used to fetch remote content. Only page mode is available.
        max_page_size_mib: Positive MiB limit for one remote page (default: 25).
    """
    temp_download_dir: Path | None = None
    markdown_contents: list[str] = []
    is_remote = input_source.startswith(("http://", "https://"))

    try:
        if max_page_size_mib is not None and max_page_size_mib <= 0:
            console.print("[red]Error:[/red] --max-page-size-mib must be a positive integer.")
            sys.exit(1)

        if not is_remote and max_page_size_mib is not None:
            console.print("[red]Error:[/red] --max-page-size-mib can only be used with remote URLs.")
            sys.exit(1)

        effective_max_page_size_mib = max_page_size_mib or DEFAULT_MAX_PAGE_SIZE_MIB

        if is_remote:
            console.print(f"[cyan]Fetching page {input_source}...[/cyan]")
            try:
                remote_page = fetch_remote(
                    input_source,
                    mode,
                    max_page_size_mib=effective_max_page_size_mib,
                    keep_temp=keep_temp,
                )
            except (RemoteFetchError, ValueError) as error:
                console.print(f"[red]Error fetching remote page:[/red] {error}")
                sys.exit(1)

            temp_download_dir = remote_page.content_path.parent
            console.print("Found [bold]1[/bold] HTML file.")
            with Progress() as progress:
                task = progress.add_task("[cyan]Converting HTML to Markdown...", total=1)
                try:
                    markdown = convert_remote_page_to_markdown(remote_page)
                except Exception as error:
                    console.print(f"[red]Error converting remote page:[/red] {error}")
                    sys.exit(1)
                markdown_contents.append(markdown)
                progress.advance(task)
        else:
            input_dir = Path(input_source)
            if not input_dir.exists():
                console.print(f"[red]Error:[/red] Input '{input_dir}' does not exist.")
                sys.exit(1)

            console.print(f"[bold green]Scanning[/bold green] {input_dir} for HTML files...")
            html_files = find_html_files(input_dir)
            if not html_files:
                console.print("[yellow]No HTML files found.[/yellow]")
                sys.exit(0)

            console.print(f"Found [bold]{len(html_files)}[/bold] HTML files.")
            with Progress() as progress:
                task = progress.add_task(
                    "[cyan]Converting HTML to Markdown...", total=len(html_files)
                )
                for html_file in html_files:
                    markdown_contents.append(convert_html_to_markdown(html_file))
                    progress.advance(task)

        console.print(
            f"[bold green]Merging[/bold green] {len(markdown_contents)} files into {output}..."
        )
        merge_markdowns(markdown_contents, output)
        console.print(
            f"[bold white on green]Success![/bold white on green] Markdown created at {output}"
        )
    finally:
        if temp_download_dir and not keep_temp:
            console.print(f"[dim]Cleaning up temporary files at {temp_download_dir} ...[/dim]")
            shutil.rmtree(temp_download_dir)
        elif temp_download_dir:
            console.print(f"[dim]Temporary files kept at {temp_download_dir}[/dim]")


if __name__ == "__main__":
    raise SystemExit(main())
