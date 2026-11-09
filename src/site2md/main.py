"""Main entry point for the site2md CLI."""

from __future__ import annotations

import sys

import cyclopts

app = cyclopts.App(name="site2md")

# Import paths, not functions, so that a command loads only the modules it uses. Before cyclopts 4.4.0
# a run still imported the other commands. Each `help` repeats its function's docstring summary,
# because the command list is drawn without importing the module.
app.command(
    "site2md.commands.extract:extract",
    name="extract",
    help="Extract structured records from a Markdown file or standard input.",
)
app.command(
    "site2md.commands.extractors:extractors",
    name="extractors",
    help="List installed Extractors using static provider metadata.",
)
app.command(
    "site2md.commands.build:build",
    name="build",
    help="Build a single Markdown file from a local HTML directory or remote page.",
    help_epilogue=(
        "Page mode rejects traversal-only options. Follow mode requires at least "
        "one --follow-selector. Follow mode rejects --max-depth and --include-query. "
        "Site mode rejects --follow-selector. Local input rejects every remote-only "
        "option. Incompatible options and non-positive budgets fail before any "
        "network request."
    ),
)


def main() -> int:
    """Run the CLI with POSIX-compatible command-usage exit status."""
    try:
        app(exit_on_error=False)
    except cyclopts.CycloptsError:
        if sys.argv[1:2] in (["extract"], ["extractors"]):
            return 2
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
