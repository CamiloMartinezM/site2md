# Benchmarks

How site2md compares with the tools a user might pick instead: Scrapling, crawl4ai, MarkItDown and pandoc. The method follows [uv's benchmarks](https://github.com/astral-sh/uv/blob/main/BENCHMARKS.md). Every tool must produce exactly the same output, and each tool's solution gets whatever code that takes.

The numbers come from the maintainer's Windows 11 machine, and reruns are by hand. There is no CI job.

## The page task

Extract the 250 countries from a local copy of [Scrape This Site's countries page](https://www.scrapethissite.com/pages/simple/). The output is a plain JSON array of `{"name", "capital", "population", "area_km2"}` objects in page order. It must match [`benchmarks/expected/countries.json`](benchmarks/expected/countries.json) exactly. "Exactly" means the same JSON after parsing, number types included and whitespace ignored, so `468` doesn't match `468.0`. A solution that exits with an error doesn't count as working.

- **The page copy.** The harness downloads the page once into a git-ignored cache. The copy isn't committed, because the site states no terms or licence. Its download date and SHA-256 are under [Results](#results), and a later run refuses a copy with a different hash.
- **The reference.** `benchmarks/expected/countries.json` holds the record values that site2md's built-in `site2md.scrapethissite.countries` Extractor produces from that copy. It holds country facts, not the page. Population is an integer, area is a number, and a missing capital is `null`: the page writes `None` for those.
- **The server.** The copy is served on 127.0.0.1, on a port that the system picks for each run.

## Method

- **Time.** `hyperfine --warmup 3` with its default run count and a fresh process per run. It times the same solution that the line count counts, end to end, with the page served locally. The table shows the mean ± standard deviation.
- **Line counts.** The non-blank, non-comment lines of every file a user would write for the solution, using the shortest solution that works.
  - Python is formatted with `ruff format` (88 columns), and imports count.
  - A shell command counts as one line. Python inside a shell command counts as its formatted lines.
  - JSON is formatted with two-space indentation, and TOML has one key per line.
  - A command-line program qualifies only if it runs without a browser.
  - Installing a tool, or site2md's benchmark Extractor, isn't counted.
  - Lines needed only because the page is served from 127.0.0.1, such as a port in an allowed-domains list, aren't counted. A footnote under the table names them.
- **Install size.** The size on disk of the installed packages, and their number, in a fresh environment. It is the smallest install that runs every task the tool appears in, without a browser. site2md's benchmark Extractor is installed after the measurement. For pandoc, it is the unpacked archive.
- **Environments.** Each tool runs in its own uv environment on Python 3.12, at an exact pinned version.

## Results

<!-- benchmarks:generated:start -->
### Page copy

The page copy was downloaded on 2026-11-06. Its SHA-256 is `4c68c2a54000607a0fa51ea5a57a20bbe4324dee74c442559185a1da364bd87b`.

### Machine and software

- OS: Windows 11
- Python in the tool environments: 3.12.14
- hyperfine: 2.0.0
- uv: 0.12.21
- ruff, which formats the Python before its lines are counted: 0.17.4

### Times, lines and install size

| Tool | Version | Output matches | Time | Lines | Install size | Packages | Crawl output matches | Extra pages | Shortest gap | Crawl lines |
|---|---|---|---|---|---|---|---|---|---|---|
| site2md | 0.4.3 | yes | 1.78 s ± 0.22 s | 54 | 11.5 MB | 20 | no crawler | no crawler | no crawler | no crawler |

### Solutions

- **site2md**: `build` converts the page, `extract` runs a minimal Extractor written for this benchmark, and one last step writes the record values. site2md is installed from its release tag, because the PyPI name belongs to a different project.

### Versions and raw results

| Tool | Version | Date | Raw results |
|---|---|---|---|
| site2md | 0.4.3 | 2026-11-06 | [site2md.json](benchmarks/results/site2md.json) |
<!-- benchmarks:generated:end -->

## Rerun

You need [uv](https://docs.astral.sh/uv/), a Python 3.12 that uv can find (`uv python install 3.12`), and [hyperfine](https://github.com/sharkdp/hyperfine) 2 or later. On Windows, install hyperfine with `winget install sharkdp.hyperfine`. If it's missing, the harness stops and says so.

Run these commands from the repository root with Python 3.10 or later. The harness uses only the standard library.

- `python -m benchmarks run site2md` measures one tool, checks its output against the reference, writes `benchmarks/results/site2md.json` and refreshes the generated part of this file. Any folder name in `benchmarks/tools` works in place of `site2md`. If the output differs from the reference, the command says where and exits with status 1.
- `python -m benchmarks render` rebuilds the generated part of this file from every results file, without running anything. After a merge conflict in this file, rerun it.
- `python -m benchmarks reference` downloads the page afresh, pins its date and hash, and rebuilds the reference records. It is needed only when the page changes. Spot-check the records by hand before you commit them.

A run writes only into the git-ignored `benchmarks/.cache`, and its servers use whatever port is free, so runs in separate checkouts can overlap. [`benchmarks/README.md`](benchmarks/README.md) explains the harness and how to add a tool.

## Excluded tools

- **trafilatura:** its extraction drops all 250 countries, even with `favor_recall=True`.
- **Firecrawl, Jina Reader:** hosted services that need API keys and can't reach a local server.
- **Docling:** a document converter; web pages need a special slim install.
- **html-to-markdown:** a small user base.
- **spider:** writes JSON lines, and its Python package is unmaintained.
- **Crawlee:** no Markdown output.
- **mdream, defuddle:** Node.js tools. mdream has a small user base, and defuddle handles single pages only.

## Caveats

Windows starts processes and loads files more slowly than Linux, so absolute times are higher, and tools that import many modules may lose more.

The results record the operating system and software versions, not the hardware.
