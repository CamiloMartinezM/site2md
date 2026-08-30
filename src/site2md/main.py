"""Main entry point for the site2md CLI."""

import shutil
import sys
from pathlib import Path
from typing import Optional

import cyclopts
from rich.console import Console
from rich.progress import Progress

from site2md.converter import convert_html_to_markdown, convert_remote_page_to_markdown
from site2md.downloader import DEFAULT_MAX_PAGE_SIZE_MIB, RemoteMode, fetch_remote
from site2md.finder import find_html_files
from site2md.merger import merge_markdowns

app = cyclopts.App(name="site2md")
console = Console()


@app.command(name="build")
def build(
    input_source: str,
    *,
    output: Path = Path("complete_manual.md"),
    keep_temp: bool = False,
    mode: RemoteMode = "page",
    max_page_size_mib: Optional[int] = None,
) -> None:
    """Build a single Markdown file from a local HTML directory or remote page.

    Args:
        input_source: Directory containing HTML files or an HTTP(S) URL.
        output: Path where the result Markdown should be saved.
        keep_temp: If True, temporary remote page data is not deleted.
        mode: Scope used to fetch remote content. Only page mode is available.
        max_page_size_mib: Positive MiB limit for one remote page (default: 25).
    """
    temp_download_dir: Optional[Path] = None
    markdown_contents: list[str] = []
    is_remote = input_source.startswith("http://") or input_source.startswith("https://")

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
            except Exception as error:
                console.print(f"[red]Error fetching remote page:[/red] {error}")
                sys.exit(1)

            temp_download_dir = remote_page.content_path.parent
            console.print("Found [bold]1[/bold] HTML file.")
            with Progress() as progress:
                task = progress.add_task("[cyan]Converting HTML to Markdown...", total=1)
                markdown_contents.append(convert_remote_page_to_markdown(remote_page))
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
    app()
