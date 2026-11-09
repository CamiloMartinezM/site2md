# Benchmarks

How site2md compares with the tools a user might pick instead: Scrapling, crawl4ai, MarkItDown and pandoc. The method follows [uv's benchmarks](https://github.com/astral-sh/uv/blob/main/BENCHMARKS.md). Every tool must produce exactly the same output, and each tool's solution gets whatever code that takes.

The numbers come from the maintainer's Windows 11 machine, and reruns are by hand. There is no CI job.

## The page task

Extract the 250 countries from a local copy of [Scrape This Site's countries page](https://www.scrapethissite.com/pages/simple/). The output is a plain JSON array of `{"name", "capital", "population", "area_km2"}` objects in page order. It must match [`benchmarks/expected/countries.json`](benchmarks/expected/countries.json) exactly. "Exactly" means the same JSON after parsing, number types included and whitespace ignored, so `468` doesn't match `468.0`. A solution that exits with an error doesn't count as working.

- **The page copy.** The harness downloads the page once into a git-ignored cache. The copy isn't committed, because the site states no terms or licence. Its download date and SHA-256 are under [Results](#results), and a later run refuses a copy with a different hash.
- **The reference.** `benchmarks/expected/countries.json` holds the record values that site2md's built-in `site2md.scrapethissite.countries` Extractor produces from that copy. It holds country facts, not the page. Population is an integer, area is a number, and a missing capital is `null`: the page writes `None` for those.
- **The server.** The copy is served on 127.0.0.1, on a port that the system picks for each run.

## The crawl task

Start from the index of a generated local site, crawl breadth first within depth 2 and at most 20 pages, and extract the same 250 countries. The output is the same JSON array of records. It must match the reference **in any order**, because crawlers visit pages in different orders: the order doesn't matter, but every country must appear exactly once, so a repeated record fails, and number types still matter.

- **The site.** The harness generates it from the page copy. The index and 19 pages below it, within depth 2, split the 250 countries between them. Five more pages one level deeper hold decoy countries (`Decoy Country 1` and so on) that must not appear in the output. Every page except the index links back to the index. The copy's own menu links, which return 404 on a local server, are removed. Its `robots.txt` allows everything. [`benchmarks/README.md`](benchmarks/README.md) lists the pages.
- **Not timed.** Site and follow modes space child requests at least one second apart, and [there is no delay override](https://github.com/CamiloMartinezM/site2md/blob/e6c8a04beb0c386a2d07d6addaf0c9e35598d66e/docs/traversal-policy.md#L35). Against tools at their defaults, site2md would always finish a crawl last. Each crawl runs once to check its output, and nobody times it.
- **Checks.** They come from the server's request log, never from a tool's own report:
  - **Crawl output matches:** whether the output matches the reference in any order, with no repeated and no missing records. A crawl that exits with an error, or writes no output, doesn't match.
  - **Extra pages:** the pages fetched beyond one fetch of each of the 20 expected pages. A decoy, a second fetch of any page, and a path that the site doesn't have each count. `robots.txt` isn't a page.
  - **Shortest gap:** the shortest time between two consecutive child-page requests. The entry page isn't a child, so the gap between it and the first child doesn't count. The server stamps each request when it arrives, with a fine clock, so a gap under a tool's delay comes from the tool: one that times its delay with a coarse clock can start a request a little early.
- **Tools without a crawler** show "no crawler" in the crawl columns.

## Method

- **Time.** `hyperfine --warmup 3` with its default run count and a fresh process per run. It times the same solution that the line count counts, end to end, with the page served locally. The table shows the mean ± standard deviation.
- **Line counts.** The non-blank, non-comment lines of every file a user would write for the solution, using the shortest solution that works. The page task and the crawl task are counted separately, and "Lines" is the page task's count.
  - Python is formatted with `ruff format` (88 columns), and imports count.
  - A shell command counts as one line. Python inside a shell command counts as its formatted lines.
  - JSON is formatted with two-space indentation, and TOML has one key per line.
  - A command-line program qualifies only if it runs without a browser.
  - Installing a tool, or site2md's benchmark Extractor, isn't counted.
  - Lines needed only because the page is served from 127.0.0.1, such as a port in an allowed-domains list, aren't counted. A footnote under the table names them.
- **Install size.** The size on disk of the installed packages, and their number, in a fresh environment. It is the smallest install that runs every task the tool appears in, without a browser. site2md's benchmark Extractor is installed after the measurement. For pandoc, it is the unpacked archive.
- **Environments.** Each tool runs in its own uv environment on Python 3.12, at an exact pinned version.

## The chart

The chart at the top of the [README](README.md) shows time only if site2md has the lowest mean time among the tools whose output matches the reference. Otherwise it shows install size. The rule was fixed before any numbers. A tool whose output doesn't match has no bar, and its row in the README's table says so. The chart is two SVGs, `docs/benchmark-light.svg` and `docs/benchmark-dark.svg`, and the README shows the one that matches the reader's theme.

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
| site2md | 0.4.6 | yes | 870 ms ± 14 ms | 54 | 11.5 MB | 20 | yes | 0 | 1.017 s | 54 |
| Scrapling | 0.5.1 | yes | 338 ms ± 9 ms | 12 [^1] | 242.9 MB [^2] | 23 | yes [^3] | 0 | 0.000 s [^4] | 19 [^1] |
| crawl4ai | 0.9.5 | yes | 1.04 s ± 0.01 s | 24 [^5] [^1] | 554.8 MB [^6] | 96 | yes [^7] | 0 | 0.000 s [^8] | 38 [^1] |
| MarkItDown | 0.1.9 | yes | 632 ms ± 16 ms | 10 [^1] | 94.8 MB | 19 | no crawler | no crawler | no crawler | no crawler |
| pandoc | 3.13 | yes | 250 ms ± 7 ms | 12 [^1] | 239.6 MB [^9] | 0 | no crawler | no crawler | no crawler | no crawler |

[^1]: Not counted: `import sys`. The harness passes the local server's 127.0.0.1 URL on the command line, and this code only reads it. A solution for the live site writes the URL inline.
[^2]: The `fetchers` extra also installs Playwright and Patchright, which take 110 MB each because each bundles a Node driver. No browser is downloaded.
[^3]: Scrapling's spiders have no depth limit, and the `max_pages` of its Markdown spider limits what it converts, not what it fetches. The spider therefore carries each page's depth in its requests and keeps its own set of the pages it has queued. Without them it fetches the five decoy pages.
[^4]: At its defaults a spider fetches up to four pages at once and adds no delay, and it doesn't request robots.txt unless asked to, so several requests reach the server together.
[^5]: crawl4ai's `crwl` command line does the task in one line, but it always starts a browser, so that line isn't counted. The count is for the Python solution, which uses the HTTP-only crawler strategy.
[^6]: crawl4ai requires Playwright and Patchright even for its HTTP-only strategy, so no smaller install exists. They take 110 MB each because each bundles a Node driver. No browser is downloaded.
[^7]: crawl4ai's breadth-first crawl never marks the entry page as visited, so every page that links back to it queues it again. A filter keeps it out. Without the filter the entry page is fetched twice, and the second fetch uses one of the 20 pages, so a country page is left out.
[^8]: At its defaults crawl4ai runs up to five fetches at once, with a random delay of 0.1 to 0.4 s per host that doesn't carry over from one level to the next, so some requests reach the server together.
[^9]: The unpacked archive: `pandoc.exe`, its manual and its licence files. pandoc is not a Python package, so its package count reads 0.

### Solutions

- **site2md**: `build` converts the page, `extract` runs a minimal Extractor written for this benchmark, and one last step writes the record values. The crawl runs `build` in site mode with `--max-pages 20 --max-depth 2` and reuses the same Extractor across the document's source sections. Both commands run in their opt-in fast modes, `build --no-progress` and `extract --entry-points-only`. site2md is installed from its release tag, because the PyPI name belongs to a different project.
- **Scrapling**: Scrapling's HTTP fetcher gets the page and CSS selectors read each country. The `fetchers` extra is the smallest one that provides the fetcher, and no browser is downloaded or started. The crawl is a spider that reads the same selectors on every page it follows and writes the records with its own JSON export.
- **crawl4ai**: Its HTTP-only crawler strategy fetches the page and its CSS extraction strategy reads each country as text, then a short loop converts the numbers and the missing capital. The crawl is its breadth-first deep crawl with the same extraction strategy. No browser is downloaded or started. Its home folder, where it keeps logs and a robots.txt cache, is moved into the benchmark's cache.
- **MarkItDown**: `MarkItDown().convert` fetches the page and converts it to Markdown, and a regular expression parses the Markdown into the records. It has no crawler.
- **pandoc**: `pandoc -f html -t gfm` fetches the page and converts it to Markdown, and a regular expression parses the Markdown into the records. It has no crawler. pandoc is not a Python package: the harness unpacks the official Windows release archive and puts its folder first on PATH, so a pandoc installed on the machine never runs. The pandoc project publishes no checksum, so the pinned SHA-256 is the digest that GitHub shows for the release asset, which matches the first download.

### Versions and raw results

| Tool | Version | Date | Raw results |
|---|---|---|---|
| site2md | 0.4.6 | 2026-11-09 | [site2md.json](benchmarks/results/site2md.json) |
| Scrapling | 0.5.1 | 2026-11-09 | [scrapling.json](benchmarks/results/scrapling.json) |
| crawl4ai | 0.9.5 | 2026-11-09 | [crawl4ai.json](benchmarks/results/crawl4ai.json) |
| MarkItDown | 0.1.9 | 2026-11-09 | [markitdown.json](benchmarks/results/markitdown.json) |
| pandoc | 3.13 | 2026-11-09 | [pandoc.json](benchmarks/results/pandoc.json) |
<!-- benchmarks:generated:end -->

## Rerun

You need [uv](https://docs.astral.sh/uv/), a Python 3.12 that uv can find (`uv python install 3.12`), and [hyperfine](https://github.com/sharkdp/hyperfine) 2 or later. On Windows, install hyperfine with `winget install sharkdp.hyperfine`. If it's missing, the harness stops and says so.

Run these commands from the repository root with Python 3.10 or later. The harness uses only the standard library.

- `python -m benchmarks run site2md` measures one tool, checks its output against the reference, writes `benchmarks/results/site2md.json` and refreshes the generated part of this file. Any folder name in `benchmarks/tools` works in place of `site2md`. If the output differs from the reference, the command says where and exits with status 1.
- `python -m benchmarks render` rebuilds the generated part of this file, the chart and the table in the README, and the two charts in `docs/` from every results file, without running anything. `run` ends with the same step. After a merge conflict in any of them, rerun it.
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
