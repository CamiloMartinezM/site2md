# Coding standards

These rules cover site2md's Python code in `src/` and `tests/`. `ruff check` and `mypy` enforce some of them. Review checks the rest.

## House rules

### 1. Lay out modules in a fixed order

Whenever possible, a module reads top to bottom in this order:

1. The module docstring, then `from __future__ import annotations`.
2. Imports. Ruff sorts them into groups: standard library, third party, then site2md.
   - A function-level import is allowed when it keeps a slow module out of the runs that don't use it. Add a one-line comment that says why.
3. Module constants, such as `USER_AGENT`.
4. Types, but only those that can't live in the types module (rule 2).
5. Classes.
6. Private helpers, whose names start with `_` or `__`.
7. Public functions.
8. The `if __name__ == "__main__":` block, if there is one.

Don't interleave the groups. For example, `src/site2md/downloader.py` currently alternates between private and public functions:

```python
def _fetch_page(...) -> RemotePage: ...
def url_origin(url: str) -> tuple[str, str, int]: ...
def _request_delay(policy: urllib.robotparser.RobotFileParser) -> float: ...
```

The preferred layout puts every private helper before the public functions:

```python
class TraversalRequestPolicy: ...

def _fetch_page(...) -> RemotePage: ...
def _request_delay(policy: urllib.robotparser.RobotFileParser) -> float: ...

def url_origin(url: str) -> tuple[str, str, int]: ...
def fetch_remote(...) -> RemotePage: ...
```

Within a group, order definitions the way a reader meets them, for example in the order they are called.

### 2. Keep custom types in one module

Package-wide custom types live in `src/site2md/_types.py`, and other modules import them from there. Custom types are type aliases, `Literal` aliases, `TypeVar`s, `NewType`s, `TypedDict`s and `Protocol`s. Examples are `RemoteMode` and `RemoteBuildStage`.

The leading underscore marks the module as internal, and it avoids shadowing the standard library's `types` module.

There are two exceptions:

- **`site2md.extractors.v1`** keeps its own types. It is the versioned provider contract, and providers import `JsonValue`, `SourceSpan` and the rest from it (ADR 0002).
- **Test-only types** live in `tests/cli_test_support.py`, next to the helpers that use them. A `test_*.py` name would make unittest collect the file as tests.

### 3. Don't suppress linters

- **No `# noqa` comments.** Fix the code instead.
  - If a rule is wrong for the whole project, ignore it in `pyproject.toml`, with a comment that says why.
- **`# type: ignore` only with an error code**, such as `# type: ignore[import-untyped]`, and only in two cases:
  - the cause is outside site2md, such as a dependency without type stubs;
  - a test breaks a type on purpose to check that site2md rejects the value at runtime, for example by assigning to a frozen field.
- **For our own data, fix the types:** narrow them, use a `TypedDict`, or `cast` with a one-line reason.

### 4. Ship only code that passes ruff, mypy and the tests

Run CI's commands on the whole repository before pushing, not only on the files you touched. Lint uses Python 3.14, as CI does:

```
ruff check
mypy src tests
python -m unittest discover -s tests
```

Fix every error rather than silencing it (rule 3). A narrow run can miss errors: raising `requires-python` once switched on pyupgrade rules everywhere. CI repeats the tests on Linux with Python 3.10 and the lowest declared dependency versions, on Linux with Python 3.14, and on Windows with Python 3.14. Merge only when all of them pass.

## Python practices

### Typing

- **Annotate every function signature**, and any module-level variable whose type isn't obvious.
- **Generics and unions:** use built-in generics and `X | None`. For parameters, use `collections.abc` types (`Mapping`, `Sequence`, `Iterable`). For return values, use concrete types.
- **Avoid `Any`.** Describe JSON-shaped data with `JsonValue` or a `TypedDict`.
- **Value objects** are frozen dataclasses, as in `site2md.extractors.v1` and `RemoteBuildRequest`.

### Python versions and dependencies

- **The floor is Python 3.10.** Don't use features from 3.11 or later without a fallback. Examples are `tomllib`, `except*`, `typing.Self`, `typing.override` and `enum.StrEnum`.
  - For `Self`, import it from `typing_extensions` under `TYPE_CHECKING`, as `tests/cli_test_support.py` does.
- **The standard library comes first.** A new runtime dependency needs a reason that neither the standard library nor an existing dependency covers.
- **Declare the lowest version you have tested.** CI installs exactly that floor on Python 3.10.

### Names

- **Use the terms in `GLOSSARY.md`**, and avoid the synonyms it lists. For example, write "Extractor", not "parser" or "scraper", and "record", not "item".
- **Make names say what a thing holds or does.** Avoid unexplained abbreviations. Booleans read as predicates, such as `is_remote` or `keep_temp`.
- **Constants** use `UPPER_SNAKE_CASE`, and private names start with `_`.

### Functions and modules

- **Give each function one job.** Keep the CLI layer thin: `main.py` registers the commands, and each module in `src/site2md/commands/` parses its arguments, calls into a module, prints and exits.
  - `main.py` also binds a plain `build` command line itself, so that such a run never loads cyclopts (ADR 0005). It reads the parameters from `build`'s signature, and leaves a command line to cyclopts when it uses a parameter whose annotation it doesn't know.
- **Make options keyword-only** by placing them after `*`, especially booleans and limits, as `_fetch_page(url, *, max_page_size_mib, ...)` does.
- **Keep decisions apart from I/O** where that's practical, so the logic can be tested without files or a network.

### Errors

- **Check inputs and destinations before expensive or remote work.** A run must not fetch a page that it then can't save (#33).
  - `build --extract` deliberately doesn't check the Extractor ID first, because the converted document is saved before extraction (spec #72, Decisions).
- **Catch the narrowest exception you can handle.**
  - A broad `except Exception` belongs only at a boundary that turns any failure into a reported error, as `extract` does.
  - Never swallow an exception and carry on to a success message (#32).
- **Report expected failures cleanly:** one line, exit status 1, no traceback. Let unexpected errors propagate.
- **Name what failed** in error messages, whether a path, a URL or an Extractor ID. Follow the existing style: `Error: Input '…' does not exist.`

### Files, paths and platforms

- **Use `pathlib.Path`** for paths.
- **Pass `encoding="utf-8"` to all text I/O:** `open`, `read_text`, `write_text`, and `subprocess.run` when you use `text=True`. Windows otherwise uses its ANSI code page.
- **Write outputs atomically.** Write a temporary file in the destination folder, flush it, then call `os.replace` or `Path.replace`. Never use `Path.rename`, which fails on Windows when the target exists (#19).
- **Code and tests must run on Windows and Linux:**
  - console scripts end in `.exe` on Windows;
  - text streams write `\r\n` there;
  - `ctypes.CDLL(None)` doesn't work there (#23).
- **Use context managers** for files, temporary folders, servers and sockets.

### Network

- **Every request needs limits:** a timeout, a size limit, and the versioned `site2md/<version>` User-Agent.
- **Honor robots.txt and the request delay** wherever a mode requires it (see `docs/traversal-policy.md`). Never retry in a loop, and never work around a site's restrictions.
- **Treat fetched content as untrusted data.**

### Security

- **Never run external data:** no `shell=True`, `eval` or `exec`, and no `pickle` on external data.
- **Keep secrets out** of code, logs and the User-Agent.

### Docstrings and comments

- **Every module, public class and public function has a docstring.** It is one line in the imperative mood ("Return …", "Build …"). Add detail only when the behaviour isn't clear from the signature.
  - Test methods are the exception: their names describe the behaviour they check.
- **Comments explain why, not what.** Keep them to one line, and don't commit commented-out code.

### Console output

- **`build` reports through the rich console.** Pass `soft_wrap=True` when a message contains a path, so the path stays whole on one line (#21).
  - With `--extract`, the console writes to standard error, so that standard output holds only the JSON.
  - Without a terminal and without a progress bar, the console prints the same lines without loading Rich (ADR 0005). A message whose style isn't in `_STYLE_TAGS` still goes through Rich, so add a new style there.
- **`extract` writes only the JSON document to standard output.** Diagnostics go to standard error.

## Tests

- **Use `unittest`.** Test modules are named `tests/test_*.py`. Shared helpers live in modules without the `test_` prefix.
- **Test behaviour at public seams:** the installed `site2md` command (`InstalledCliTestCase`) or `site2md.extraction.extract`. Don't test private helpers, and don't mock internals.
- **Keep tests offline.** Serve pages from the local `RecordingServer`. Live checks run only when `SITE2MD_LIVE_TESTS=1` is set.
- **Write fixtures by hand.** Don't copy them from live sites.
- **Take expected values from an independent source,** such as a literal or a worked example. Never recompute them the way the code does.
- **Start every bug fix with a failing regression test.** Watch it fail for the bug's reason, pass with the fix, and fail again when the fix is reverted.
- **Validate a path before deleting it.** Never call `shutil.rmtree` on a path you haven't checked is absolute and expected (#21).
