"""Main entry point for the site2md CLI."""

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
from rich.console import Console
from rich.progress import Progress

from site2md.converter import convert_html_to_markdown
from site2md.downloader import RemoteMode
from site2md.extraction import ExtractionError, list_extractors
from site2md.extraction import extract as extract_markdown
from site2md.finder import find_html_files
from site2md.merger import merge_markdowns
from site2md.remote_build import RemoteBuildError, RemoteBuildRequest, build_remote

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


def main() -> int:
    """Run the CLI with POSIX-compatible command-usage exit status."""
    try:
        app(exit_on_error=False)
    except cyclopts.CycloptsError:
        if sys.argv[1:2] in (["extract"], ["extractors"]):
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
    follow_selector: list[str] | None = None,
    max_pages: int | None = None,
    max_depth: int | None = None,
    include_query: bool = False,
    max_total_size_mib: int | None = None,
    max_page_size_mib: int | None = None,
) -> None:
    """Build a single Markdown file from a local HTML directory or remote page.

    Args:
        input_source: Directory containing HTML files or an HTTP(S) URL.
        output: Path where the result Markdown should be saved.
        keep_temp: If True, temporary remote page data is not deleted.
        mode: Scope used to fetch remote content. Page mode is the default.
        follow_selector: CSS selector for anchors to follow; repeatable in follow mode.
        max_pages: Positive traversal page budget (default: 50).
        max_depth: Positive site-mode depth budget (default: 3).
        include_query: Include query-bearing links discovered in site mode.
        max_total_size_mib: Positive traversal body budget (default: 250).
        max_page_size_mib: Positive MiB limit for one remote page (default: 25).
    """
    markdown_contents: list[str] = []
    is_remote = input_source.startswith(("http://", "https://"))

    if not is_remote and (
        mode != "page"
        or follow_selector is not None
        or max_pages is not None
        or max_depth is not None
        or include_query
        or max_total_size_mib is not None
        or max_page_size_mib is not None
    ):
        console.print("[red]Error:[/red] Remote build options require an HTTP(S) URL.")
        sys.exit(1)

    if is_remote:
        with Progress() as progress:
            task = progress.add_task("[cyan]Building remote page...", total=1)
            try:
                summary = build_remote(
                    RemoteBuildRequest(
                        entry_url=input_source,
                        destination=output,
                        mode=mode,
                        follow_selectors=tuple(follow_selector or ()),
                        max_pages=max_pages,
                        max_depth=max_depth,
                        include_query=include_query,
                        max_total_size_mib=max_total_size_mib,
                        max_page_size_mib=max_page_size_mib,
                        keep_temp=keep_temp,
                    )
                )
            except RemoteBuildError as error:
                labels = {
                    "validation": "Error:",
                    "fetch": "Error fetching remote page:",
                    "conversion": "Error converting remote page:",
                    "destination": "Error writing remote output:",
                    "cleanup": "Error cleaning remote workspace:",
                    "interruption": "Remote build interrupted:",
                    "unexpected": "Unexpected remote build error:",
                }
                console.print(f"[red]{labels[error.stage]}[/red] {error}")
                if error.retained_workspace is not None:
                    console.print(
                        f"[dim]Temporary files kept at {error.retained_workspace}[/dim]"
                    )
                sys.exit(1)
            progress.advance(task)

        for warning in summary.warnings:
            console.print(f"[yellow]Warning:[/yellow] {warning}")
        for reached_limit in summary.reached_limits:
            console.print(f"[yellow]Reached limit:[/yellow] {reached_limit}")
        console.print(
            f"Fetched [bold]{summary.fetched}[/bold]; "
            f"skipped [bold]{summary.skipped}[/bold]; "
            f"failed [bold]{summary.failed}[/bold]."
        )
        if summary.retained_workspace is not None:
            console.print(f"[dim]Temporary files kept at {summary.retained_workspace}[/dim]")
        console.print(
            f"[bold white on green]Success![/bold white on green] Markdown created at {output}"
        )
        return

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


if __name__ == "__main__":
    raise SystemExit(main())
