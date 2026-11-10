# Speed research for 0.6.0

The question was how to make `build` faster than it was in 0.5.0, compared with the tools in [BENCHMARKS.md](../BENCHMARKS.md), without losing a feature or changing what a build produces. This note records what was measured: where 0.5.0 spent its time, what shipped in 0.6.0, what was measured and left out, and what is left.

## Result

| | 0.5.0 | 0.6.0 |
|---|---|---|
| The page task, package | 626 ms ± 17 ms | 354 ms ± 10 ms |
| The page task, executable | 508 ms ± 15 ms | 267 ms ± 9 ms |
| The same build without `--extract`, package | 493 ms ± 16 ms | 232 ms ± 13 ms |
| The same build without `--extract`, executable | 397 ms ± 15 ms | 176 ms ± 7 ms |

The page task is the benchmark's step: `site2md build <url> --no-progress --output page.md --extract benchmark.countries --entry-points-only --values-only > output.json`. The numbers are the mean ± standard deviation of 60 runs per cell for the page task and 40 for the build alone, on the Windows 11 machine of the published benchmarks, with Python 3.12. The cells of each pair of rows ran interleaved, and every round of the page task matched `benchmarks/expected/countries.json`.

In the published table pandoc takes 254 ms and Scrapling 334 ms. In this session they took 245 to 252 ms and 331 ms. So the executable is now ahead of Scrapling and about 15 ms behind pandoc, and the package is about 20 ms behind Scrapling. The published table is measured from a release, and its rerun from the 0.6.0 release gave 349 ms ± 8 ms for the package and 264 ms ± 8 ms for the executable, against 625 ms ± 10 ms and 497 ms ± 17 ms for 0.5.0. Nothing was measured on Linux.

## Method

- **Time.** hyperfine with a fresh process per run, and the page served on 127.0.0.1 by the harness's `FixtureServer`, as `python -m benchmarks run` does. To compare versions, their runs alternate in rounds of ten, so that a change in the machine's load reaches all of them, and each round's output is compared with the reference. A saving below about 3 ms can't be told from noise this way.
- **Stages.** `python -X importtime` for the imports, and timers around the functions of one real run for the rest.
- **Same output.** Every change was held to 0.5.0's output, checked in four ways:
  - **The converter.** 0.5.0's converter and the new one converted 9,014 documents, each as a local file, as a remote page and as a remote page with no declared encoding: 27,042 comparisons. The documents are the benchmark page and its crawl pages, every HTML literal in `tests/`, 70 saved public pages, and copies of all of them with a random span cut, dropped or repeated. Nothing differs on Python 3.12 and 3.14 with Beautiful Soup 4.15.0. On Python 3.10 with the declared floors (Beautiful Soup 4.12.0, markdownify 1.0.0), one page nested too deeply to convert fails in both versions, with a `RecursionError` whose wording differs. Nothing else differs.
  - **The command line.** Of 36,173 `build` command lines, `main` binds 2,665 itself, and cyclopts 5.4.0 and 4.4.0 bind every one of those to the same values.
  - **The whole command.** On the benchmark page and on two live HTTPS pages, the Markdown, the messages and the extraction result are the same bytes as 0.5.0's, apart from the provider version that the extraction result names. The crawl task still passes its checks.
  - **The tests.** Each fast path has installed-command tests that fail when its fallback is removed. Nine such mutations were tried, and each one failed a test.

The harnesses for the first two checks were throwaway scripts and aren't committed, as for [#59](https://github.com/CamiloMartinezM/site2md/pull/59).

## Where 0.5.0 spent its time

One page build with the package took about 625 ms. Roughly:

| Stage | Time |
|---|---|
| Imports | 229 ms: cyclopts 59, the extraction modules 57, Beautiful Soup 44 (Soup Sieve 22 of it), urllib 33, Rich 28 |
| Parsing the page twice | 52 ms and 45 ms |
| Writing the tree back to HTML between the two parses | 14 ms |
| Reading `page.html` back after writing it | 32 ms |
| Reading the Markdown back, twice | 8 ms each |
| markdownify | 25 ms, half of it in `find_parent("pre")`, which it calls at every element |
| marko, for the Extractor | 40 ms |
| Checking the records' source spans | 8 ms, with the section bounds worked out again for every span |
| The request | 12 to 20 ms, 8 of them to load the system certificates for an HTTP URL |
| The messages | 9 ms |

The rest is the interpreter's start and exit.

## What shipped

Each saving was measured on its own, with the package unless the row says otherwise. They overlap a little, so they don't add up exactly.

| Change | Saves |
|---|---|
| Render the Markdown from the first parse tree | 64 ms |
| Pass the page and the Markdown on in memory instead of reading files back | 47 ms |
| Print plain messages without Rich | 37 ms |
| Bind a plain command line without cyclopts | 26 ms |
| Import Soup Sieve at its first use | 22 ms |
| Answer markdownify's `find_parent` by walking up the tree | 13 ms |
| Clean the tree and resolve its references in one pass | 12 ms |
| Collect garbage less often | 12 ms |
| Skip the collector's last pass at exit (`gc.freeze`) | 10 ms |
| Import the extraction modules on a thread while the build waits for the network and the disk | 9 ms |
| Create the HTTPS handler at the first HTTPS request | 8 ms |
| Work out the section bounds once per extraction | 7 ms |
| Leave `multiprocessing` out of the executable | 7 ms, executable only |

Four of them need a word.

- **One parse.** #59 left this out because the Markdown changed, and 0.6.0 handles each cause. A removed element, or an end tag without a start tag, leaves two text nodes side by side, so the converter joins them. A doctype or a declaration inside the content, text inside an `<iframe>` or another raw-text element, and a void element that Beautiful Soup before 4.15 left open all parse differently the second time, so the converter parses those pages twice, as before. 91 % of the saved pages take the single parse with Beautiful Soup 4.15, and 79 % with 4.12.0.
- **The extraction thread.** It is a daemon thread that only imports modules. A build that fails before it extracts exits without waiting for it. Three failing builds that exit while the thread is still importing were each run 300 times on Python 3.10, 3.12 and 3.14 and with the executable: every run gave the same output and status.
- **Memory.** A traversal now holds its converted Markdown in memory until it writes the output, where 0.5.0 copied it from the workspace files. That is about twice the size of the output file at the end. The collector also runs less often, so the tree of a page that is already converted stays in memory a little longer. Measured, the peak working set fell from 56 MiB to 45 MiB on the page task, with one tree instead of two and without cyclopts and Rich, and stayed at 48 MiB on the benchmark's 20-page crawl.
- **The exit.** After `gc.freeze`, Python no longer finalizes objects that are still in a reference cycle when the command ends. site2md closes its own files, so this reaches only an Extractor provider that relies on such a finalizer, which Python never guaranteed to run.

## What Windows adds

Three findings explain why some of these savings are so large, and they hold for any Python command-line tool on Windows with Microsoft Defender.

- **Reading a file just written is slow.** Writing the 203 KB page takes under 1 ms. Reading it back takes 32 to 55 ms, and 5 to 12 ms for 25 KB of Markdown, because the first read is when the file is scanned.
- **Every `.pyc` open costs about 0.2 ms**, every time, against 0.02 ms for a file with another extension. A run imports about 200 modules, which is 40 to 70 ms. The executable keeps its modules in one archive and doesn't pay this, which is a large part of its lead over the package.
- **The null device says it is a terminal.** hyperfine sends a command's messages there, so Rich treated a benchmark run as a terminal session. `build` asks for the terminal's size as well, which the null device doesn't have.

Two more are traps for anyone who measures. `localhost` resolves to `::1` first, and a server bound to 127.0.0.1 then costs about 2 s per request. And uv reuses its build of a local project until `pyproject.toml` changes, so `uv run --with .` built the executable from stale sources. `[tool.uv] cache-keys` in `pyproject.toml` now names the sources too.

## Measured and left out

| Experiment | Saves | Why it is left out |
|---|---|---|
| Serve the package's bytecode from copies that aren't named `.pyc` | 46 ms, package | It works around one antivirus product's rule, needs a writable store outside the package, and has to hook the import system before the first import |
| Build the executable with Nuitka instead of PyInstaller | 12 ms, executable | The bundle grows from 27.5 MB to 52 MB, the build needs a C compiler, and [ADR 0004](adr/0004-ship-a-pyinstaller-onedir-executable-alongside-the-package.md) would have to change. It would bring the executable to within a few milliseconds of pandoc |
| Connect without a timeout on Windows, then set it | 0 to 8 ms | A connect with a timeout sometimes waits for a timer tick. Avoiding that means replacing a private function of `http.client` |
| Skip the debug index when the workspace isn't kept | 4 ms | A build that is killed, or that can't remove its workspace, leaves the index behind to explain it |
| Python 3.14 in the executable | nothing | ADR 0004 chose 3.12 because it was faster, and 3.14 still isn't |
| Speed up marko's parse | not measured | The time is in marko's own scanner, so it means a change in marko |

Three bigger changes were ruled out without a prototype, because they change the output: lxml in place of `html.parser` builds different trees, a converter that streams Markdown without a tree would have to reproduce every whitespace rule of markdownify, and another Markdown parser would change the nodes that Extractors see. A process that stays warm between builds is a different product from a command.

## What is left

One page task with the package now takes about 354 ms. Roughly:

| Stage | Time |
|---|---|
| Imports | 143 ms: Beautiful Soup, markdownify and urllib 67, the extraction modules 67, `site2md.main` 9 |
| Parsing the page | 48 ms |
| marko, and the nodes built from its tree | 58 ms |
| The request | 14 ms |
| markdownify | 13 ms |
| Finding the Extractor | 6 ms |
| The debug index, three writes | 5 ms |
| The interpreter's start and exit, and the rest | 65 ms |

The executable runs the same code in 267 ms, because its imports cost less.

The three large rows are pure-Python libraries doing their work: the imports, `html.parser` with Beautiful Soup's tree builder, and marko. To make one of them faster is to change the library, to replace it, or to pay for it once instead of at every run, and the last two change the output or the product. The cheapest next steps are the two experiments above that were measured and left out: Nuitka for the executable, and the bytecode copies for the package on Windows.
