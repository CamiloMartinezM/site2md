"""Implement the build command."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from rich.console import Console

from site2md._types import RemoteMode
from site2md.converter import convert_html_to_markdown
from site2md.finder import find_html_files
from site2md.merger import merge_markdowns
from site2md.remote_build import RemoteBuildError, RemoteBuildRequest, build_remote

console = Console()


@contextmanager
def _progress_bar(description: str, total: int, *, is_shown: bool) -> Iterator[Callable[[], None]]:
    """Draw a progress bar while the block runs, and yield the function that advances it."""
    if not is_shown:
        yield lambda: None
        return
    # Imported here so that --no-progress never loads rich.progress.
    from rich.progress import Progress

    with Progress() as progress:
        task = progress.add_task(description, total=total)
        yield lambda: progress.advance(task)


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
    progress: bool = True,
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
        progress: Draw a progress bar. Pass --no-progress to skip it, for scripts and benchmarks.
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

    # Check before any work, so a remote build never requests a page it cannot save.
    if not output.parent.is_dir():
        console.print(
            f"[red]Error:[/red] Output folder '{output.parent}' does not exist.",
            soft_wrap=True,
        )
        sys.exit(1)

    if is_remote:
        with _progress_bar("[cyan]Building remote page...", 1, is_shown=progress) as advance:
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
                # soft_wrap keeps messages and paths on one line, whole and copyable.
                console.print(f"[red]{labels[error.stage]}[/red] {error}", soft_wrap=True)
                if error.retained_workspace is not None:
                    console.print(
                        f"[dim]Temporary files kept at {error.retained_workspace}[/dim]",
                        soft_wrap=True,
                    )
                sys.exit(1)
            advance()

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
            console.print(
                f"[dim]Temporary files kept at {summary.retained_workspace}[/dim]",
                soft_wrap=True,
            )
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
    with _progress_bar(
        "[cyan]Converting HTML to Markdown...", len(html_files), is_shown=progress
    ) as advance:
        for html_file in html_files:
            markdown_contents.append(convert_html_to_markdown(html_file))
            advance()

    console.print(
        f"[bold green]Merging[/bold green] {len(markdown_contents)} files into {output}..."
    )
    try:
        merge_markdowns(markdown_contents, output)
    except OSError as error:
        console.print(f"[red]Error writing output:[/red] {error}", soft_wrap=True)
        sys.exit(1)
    console.print(
        f"[bold white on green]Success![/bold white on green] Markdown created at {output}"
    )
