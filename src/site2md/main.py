"""Main entry point for the site2md CLI."""

from __future__ import annotations

import gc
import importlib
import sys
import types
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, get_args

from site2md._types import RemoteMode

# How a plain command line gives each kind of parameter its value. The keys are the annotations
# as the commands write them: a parameter with any other annotation is left to cyclopts.
_PLAIN_VALUES: dict[str, Callable[[str], object]] = {
    "str": str,
    "str | None": str,
    "Path": Path,
    "Path | None": Path,
    "int | None": int,
    "list[str] | None": str,
    "RemoteMode": str,
}


class _DeferredModule(types.ModuleType):
    """Stand in for a module until an attribute of it is read, and import it then."""

    def __getattr__(self, name: str) -> object:
        # Reached only for names this placeholder lacks, so the module loads on its first real use.
        if sys.modules.get(self.__name__) is self:
            del sys.modules[self.__name__]
        module = importlib.import_module(self.__name__)
        self.__dict__.update(module.__dict__)
        return getattr(module, name)


def _plain_arguments(
    command: Callable[..., None], tokens: Sequence[str]
) -> dict[str, Any] | None:
    """Bind a plain command line to a command's parameters, or return None to leave it to cyclopts.

    Plain means one positional value, `--name value`, `--flag` and `--no-flag`, with no option
    repeated unless it takes a list. Everything else, such as `--name=value`, `--help`, a missing
    value or one that is not valid, goes to cyclopts, which also words the error messages.
    """
    annotations = command.__annotations__
    positional = command.__code__.co_varnames[: command.__code__.co_argcount]
    # Any, because the values are bound by name at run time, as cyclopts binds them.
    bound: dict[str, Any] = {}
    remaining = iter(tokens)
    for token in remaining:
        value: Any
        if not token.startswith("-"):
            name, value = positional[0] if positional else "", token
        elif not token.startswith("--") or "_" in token:
            return None
        else:
            name, value = token[2:].replace("-", "_"), True
            if name.startswith("no_") and annotations.get(name[3:]) == "bool":
                name, value = name[3:], False
            elif annotations.get(name) != "bool":
                value = next(remaining, "")
                if value.startswith("-"):
                    return None
        annotation = annotations.get(name)
        if annotation != "bool":
            if (
                annotation not in _PLAIN_VALUES
                or not value
                or (annotation == "int | None" and not (value.isascii() and value.isdigit()))
                or (annotation == "RemoteMode" and value not in get_args(RemoteMode))
            ):
                return None
            value = _PLAIN_VALUES[annotation](value)
        if annotation == "list[str] | None":
            bound.setdefault(name, []).append(value)
        elif name in bound:
            return None
        else:
            bound[name] = value
    return bound if all(name in bound for name in positional) else None


def _run_with_cyclopts() -> int:
    """Run the CLI through cyclopts with POSIX-compatible command-usage exit status."""
    # Imported here so that a plain build command line never loads cyclopts.
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
            "Site mode rejects --follow-selector. --browser needs page mode. --wait-for needs --browser. Local input rejects every "
            "remote-only option. --extract-output, --entry-points-only and --values-only require "
            "--extract. Incompatible options and non-positive budgets fail before any "
            "network request."
        ),
    )
    try:
        app(exit_on_error=False)
    except cyclopts.CycloptsError:
        if sys.argv[1:2] in (["extract"], ["extractors"]):
            return 2
        return 1
    return 0


def main() -> int:
    """Run the CLI with POSIX-compatible command-usage exit status."""
    # A run builds a few large trees and exits, so collecting often costs time and frees little.
    gc.set_threshold(100_000, 10, 10)
    if "soupsieve" not in sys.modules:
        # Beautiful Soup imports Soup Sieve, which compiles its grammar for 20 ms; only follow mode uses it.
        sys.modules["soupsieve"] = _DeferredModule("soupsieve")
    try:
        if sys.argv[1:2] == ["build"]:
            # Imported here so that the other commands never load build's modules.
            from site2md.commands.build import build

            arguments = _plain_arguments(build, sys.argv[2:])
            if arguments is not None:
                build(**arguments)
                return 0
        return _run_with_cyclopts()
    finally:
        # Interpreter shutdown would otherwise walk every object once more.
        gc.freeze()


if __name__ == "__main__":
    raise SystemExit(main())
