"""Implement the build command."""

from __future__ import annotations

import importlib
import os
import re
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from site2md._types import RemoteMode
from site2md.converter import convert_html_to_markdown
from site2md.finder import find_html_files
from site2md.merger import merge_markdowns
from site2md.remote_build import RemoteBuildError, RemoteBuildRequest, build_remote

if TYPE_CHECKING:
    from rich.console import Console

# The styles in build's messages. Away from a terminal, Rich prints a message without them.
_STYLE_TAGS = re.compile(r"\[/?(?:bold|red|yellow|dim|bold green|bold white on green)\]")
# Rich replaces a name between two colons with an emoji when it knows the name.
_EMOJI_CODE = re.compile(r":\S*?:")


class _BuildConsole:
    """Print build's messages through Rich, or without loading it where Rich only drops the styles.

    That is where there is no terminal and no progress bar. A message that Rich would also wrap,
    or change in any other way, still goes through Rich, so the lines are the same either way.
    """

    def __init__(self, *, use_stderr: bool, with_progress: bool) -> None:
        self._use_stderr = use_stderr
        # Both variables can make Rich treat a pipe or a file as a terminal.
        self._is_plain = not with_progress and not {"FORCE_COLOR", "TTY_COMPATIBLE"} & os.environ.keys()
        self._rich: Console | None = None

    @property
    def rich(self) -> Console:
        """Return the Rich console, created at its first use."""
        if self._rich is None:
            # Imported here so that a build that prints only plain lines never loads Rich.
            from rich.console import Console

            self._rich = Console(stderr=self._use_stderr)
        return self._rich

    def print(self, message: str, *, soft_wrap: bool = False) -> None:
        """Print one message, which may hold Rich markup."""
        stream = sys.stderr if self._use_stderr else sys.stdout
        if self._is_plain and not _is_terminal(stream):
            line = _plain_line(message, soft_wrap=soft_wrap)
            if line is not None:
                stream.write(f"{line}\n")
                stream.flush()
                return
        self.rich.print(message, soft_wrap=soft_wrap)


def _is_terminal(stream: TextIO) -> bool:
    """Return whether a stream writes to a terminal."""
    if not stream.isatty():
        return False
    if sys.platform == "win32":
        # The null device says that it is a terminal on Windows, but it has no size.
        try:
            os.get_terminal_size(stream.fileno())
        except OSError:
            return False
        except ValueError:  # not a standard stream, so there is no way to tell
            pass
    return True


def _plain_line(message: str, *, soft_wrap: bool) -> str | None:
    """Return the line that Rich prints for a message away from a terminal, or None if only Rich can tell."""
    tags = _STYLE_TAGS.findall(message)
    line = _STYLE_TAGS.sub("", message)
    if (
        "\\[" in message  # an escaped bracket
        or "[" in line  # markup other than build's styles, perhaps in a path or a URL
        or len(tags) % 2
        or any(closing != f"[/{opening[1:]}" for opening, closing in zip(tags[::2], tags[1::2]))
        or not (line.isascii() and line.isprintable())  # wide and control characters
        or _EMOJI_CODE.search(line)
    ):
        return None
    if not soft_wrap:
        # Rich wraps at COLUMNS, or else at the width of a terminal on a standard stream, or else at
        # 80 columns. On an old Windows console it wraps up to two columns earlier.
        columns = os.environ.get("COLUMNS", "")
        if columns.isdigit():
            width = int(columns)
        else:
            width = 80
            for descriptor in (0, 1, 2):
                try:
                    width = min(width, os.get_terminal_size(descriptor).columns or 80)
                except (OSError, ValueError):
                    pass
        if len(line) > (width or 80) - 2:
            return None
    return line


def _preload_extraction() -> None:
    """Import the extraction modules ahead of their use, on a thread of its own."""
    # build imports the module again when it extracts, and that import reports a failure.
    with suppress(Exception):
        importlib.import_module("site2md.file_extraction")


@contextmanager
def _progress_bar(
    console: _BuildConsole, description: str, total: int, *, is_shown: bool
) -> Iterator[Callable[[], None]]:
    """Draw a progress bar on the console while the block runs, and yield the function that advances it."""
    if not is_shown:
        yield lambda: None
        return
    # Imported here so that --no-progress never loads rich.progress.
    from rich.progress import Progress

    with Progress(console=console.rich) as progress:
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
    browser: bool = False,
    browser_profile: Path | None = None,
    progress: bool = True,
    extract: str | None = None,
    extract_output: Path | None = None,
    entry_points_only: bool = False,
    values_only: bool = False,
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
        browser: Read the page from an installed Chrome, Edge or Chromium after its scripts have run,
            so that content a script adds is there. Page mode only. Set SITE2MD_BROWSER to the path of
            a browser to use that one.
        browser_profile: With --browser, use this existing folder as the browser's profile and leave it
            as the browser leaves it, to read a page that only signed-in visitors get. Start the same
            browser once with --user-data-dir=FOLDER, sign in to the site and close the browser; later
            builds have that session. site2md has no window of its own for signing in. The folder can't
            be the browser's everyday profile, which Chrome refuses to debug, and no other browser may
            have it open. Nothing is ever copied out of it, also not with --keep-temp. Use it only on
            sites whose terms allow automated access.
        progress: Draw a progress bar. Pass --no-progress to skip it, for scripts and benchmarks.
        extract: Extractor ID. After saving the Markdown, run this Extractor on exactly the
            saved file in the same process, and write the extraction result to standard output.
            Build's own messages and progress bar then go to standard error. If the Extractor
            is missing or fails, the Markdown stays and the command exits 1.
        extract_output: With --extract, replace this file atomically with the extraction result
            instead of writing it to standard output.
        entry_points_only: With --extract, look up the Extractor faster, as extract does.
        values_only: With --extract, write only a JSON array of the record values, as extract
            does.
    """
    console = _BuildConsole(use_stderr=extract is not None, with_progress=progress)
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
        or browser
        or browser_profile is not None
    ):
        console.print("[red]Error:[/red] Remote build options require an HTTP(S) URL.")
        sys.exit(1)

    if extract is None and (extract_output is not None or entry_points_only or values_only):
        console.print(
            "[red]Error:[/red] --extract-output, --entry-points-only and --values-only "
            "require --extract."
        )
        sys.exit(1)

    # Check before any work, so a remote build never requests a page it cannot save.
    if not output.parent.is_dir():
        console.print(
            f"[red]Error:[/red] Output folder '{output.parent}' does not exist.",
            soft_wrap=True,
        )
        sys.exit(1)
    if extract_output is not None and not extract_output.parent.is_dir():
        console.print(
            f"[red]Error:[/red] Extract output folder '{extract_output.parent}' does not exist.",
            soft_wrap=True,
        )
        sys.exit(1)
    # Replacing the Markdown with the result would destroy the document that extract must find.
    if extract_output is not None and extract_output.resolve() == output.resolve():
        console.print(
            "[red]Error:[/red] --extract-output must differ from --output, "
            "which holds the Markdown.",
            soft_wrap=True,
        )
        sys.exit(1)

    if extract is not None:
        # The extraction modules take tens of milliseconds to load, which fits into the time
        # that the build spends waiting for the network and the disk.
        threading.Thread(target=_preload_extraction, daemon=True).start()

    if is_remote:
        with _progress_bar(console, "[cyan]Building remote page...", 1, is_shown=progress) as advance:
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
                        browser=browser,
                        browser_profile=browser_profile,
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
        document = summary.document
    else:
        input_dir = Path(input_source)
        if not input_dir.exists():
            console.print(f"[red]Error:[/red] Input '{input_dir}' does not exist.")
            sys.exit(1)

        console.print(f"[bold green]Scanning[/bold green] {input_dir} for HTML files...")
        html_files = find_html_files(input_dir)
        if not html_files:
            console.print("[yellow]No HTML files found.[/yellow]")
            # With --extract, a success status would send a script an empty result.
            sys.exit(0 if extract is None else 1)

        console.print(f"Found [bold]{len(html_files)}[/bold] HTML files.")
        with _progress_bar(
            console, "[cyan]Converting HTML to Markdown...", len(html_files), is_shown=progress
        ) as advance:
            for html_file in html_files:
                markdown_contents.append(convert_html_to_markdown(html_file))
                advance()

        console.print(
            f"[bold green]Merging[/bold green] {len(markdown_contents)} files into {output}..."
        )
        try:
            document = merge_markdowns(markdown_contents, output)
        except OSError as error:
            console.print(f"[red]Error writing output:[/red] {error}", soft_wrap=True)
            sys.exit(1)
        console.print(
            f"[bold white on green]Success![/bold white on green] Markdown created at {output}"
        )

    if extract is None:
        return
    # Imported here so that plain build never loads the extraction modules.
    from site2md.file_extraction import FileExtractionError, write_extraction

    try:
        warnings = write_extraction(
            extract,
            document,
            output=extract_output,
            entry_points_only=entry_points_only,
            values_only=values_only,
        )
    except FileExtractionError as error:
        for line in error.lines:
            print(line, file=sys.stderr)
        console.print(
            f"[red]Error:[/red] The converted document is kept at '{output}'. "
            "Rerun site2md extract on it once the problem is fixed.",
            soft_wrap=True,
        )
        sys.exit(1)
    for line in warnings:
        print(line, file=sys.stderr)
