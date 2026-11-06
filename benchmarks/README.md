# Benchmark harness

The harness behind [BENCHMARKS.md](../BENCHMARKS.md). It uses only the standard library, and it never becomes a site2md dependency: the wheel packages `src/site2md` alone.

```
python -m benchmarks run <tool>   # measure one tool, write results/<tool>.json, refresh BENCHMARKS.md
python -m benchmarks render       # rebuild BENCHMARKS.md's generated part from every results file
python -m benchmarks reference    # download the page afresh, pin it, rebuild expected/countries.json
```

## Layout

| Path | Holds |
|---|---|
| `tools/<id>/` | One tool: `tool.json`, its solution files, and anything its install needs. Nothing outside this folder changes when a tool is added |
| `results/<id>.json` | That tool's committed results. One file per tool, so tools merge without conflicts |
| `expected/countries.json` | The reference records |
| `expected/page.json` | The page copy's URL, download date and SHA-256 |
| `.cache/` | Git-ignored. The page copy, the environments, uv's cache, temporary files and work folders |
| `*.py` | The harness. `catalog` loads tools and counts lines, `runner` runs a tool, `report` renders BENCHMARKS.md |

BENCHMARKS.md is the only file rendered from all the results. Rerun `python -m benchmarks render` to resolve a merge conflict in it.

## What a run does

1. Checks that hyperfine and uv are installed, and stops with how to install them if not.
2. Reuses the cached page copy, or downloads it, and checks its SHA-256 against `expected/page.json`.
3. Creates a fresh uv environment on Python 3.12, installs the tool's pinned requirements, and measures the install. Then it runs the tool's `setup` commands.
4. Serves the page on 127.0.0.1 on a free port, and runs hyperfine on the solution's steps joined with `&&`.
5. Compares the last step's output with the reference, counts the solution's lines, and writes `results/<id>.json`. Then it refreshes BENCHMARKS.md, the same as `render`. If the output differs, the file records `"matches": false`, and the command prints the first difference and exits with status 1.

Every child process gets `UV_CACHE_DIR` and the temporary-file variables pointing into `.cache`, so a run writes nowhere else. `UV_PYTHON_DOWNLOADS=never` makes a missing Python 3.12 an error instead of a download into uv's own folder; `uv python install 3.12` fixes it.

## Adding a tool

Create `tools/<id>/tool.json` and the files it names, then run `python -m benchmarks run <id>`. No harness code changes. `tools/site2md` is the worked example.

```json
{
  "name": "Display name",
  "version": "1.2.3",
  "solution": "One sentence for BENCHMARKS.md.",
  "requirements": ["package=={version}"],
  "page": {"steps": [{"run": "python solution.py {url}", "file": "solution.py"}]}
}
```

| Key | Meaning |
|---|---|
| `name`, `version`, `solution` | What BENCHMARKS.md shows. `{version}` in a requirement is replaced by `version`, so the pin lives in one place |
| `requirements` | Requirement strings for `uv pip install`. Pin each tool to an exact version. An empty list is fine |
| `install` | Optional argument lists that run after the requirements and before the install is measured. Their placeholders are `{python}`, `{environment}`, `{cache}` and `{tool}` |
| `setup` | Optional argument lists that run after the measurement, such as installing site2md's benchmark Extractor. Same placeholders |
| `path` | Optional folders of `{environment}` to put on PATH, besides the Python environment's own scripts folder |
| `env` | Optional environment variables for the solution and `setup`. Values accept the same placeholders |
| `footnotes` | Optional notes: `{"column": "time" \| "lines" \| "size", "text": "..."}`. The report numbers them and puts them under the table |
| `page.steps` | The solution, in order. See below |
| `page.files` | Other files that the solution needs and that count toward its lines, such as an Extractor |
| `page.output_file` | Optional. Where the last step writes the records. By default its standard output is saved as `output.json` |

Unknown keys are errors, and so is a file that doesn't exist.

### The solution

Each step is `{"run": "<command>"}`, typed as a user would type it. The commands run in a work folder, through the platform shell, with the environment's scripts folder first on PATH. `{url}` is the page's URL. A step may name a Python `file`, which is copied into the work folder under its own name. A shell needs `{{` and `}}` for literal braces.

The last step must produce the JSON array of records, as `{"name", "capital", "population", "area_km2"}` objects in page order, with an integer population, a number for the area and `null` for a missing capital. Write the file with UTF-8 encoding, or print ASCII-only JSON, because Windows consoles and files default to a legacy code page.

### Line counts

`python -m benchmarks` counts the solution under the rules in BENCHMARKS.md:

- A step counts one line. A step with a `file` counts that file's lines instead.
- Python is formatted with `ruff format` (88 columns, ignoring the project's settings) at the version in `line_count.py`, and then its non-blank, non-comment lines are counted. Docstrings count. JSON is re-indented with two spaces. TOML counts as written, so write one key per line.
- A line needed only because the page is served from 127.0.0.1 isn't counted. In Python and TOML, end the line with `# 127.0.0.1-only`. For a step, add `"local_only": true`. The report adds a footnote that names those lines.

### Install size

The size of the environment's site-packages, without bytecode caches, plus anything an `install` command unpacked into `{environment}` outside `venv/`. The packages are the `.dist-info` folders. A tool that is not a Python package, such as pandoc, unpacks its archive into `{environment}`, checks the archive's checksum in its own `install` command, and adds the unpacked folder to `path`. `tools/pandoc/install_archive.py` does the first two for a zip: it refuses an archive whose SHA-256 is not the pinned one before it unpacks anything.

## Tests

`tests/test_benchmark_*.py` run in CI without any benchmarked tool: the line counter, the output comparison, the hyperfine summary, the report and the fixture server. Two of them check the committed files: no results file names a path or a machine, and BENCHMARKS.md matches what `render` produces.
