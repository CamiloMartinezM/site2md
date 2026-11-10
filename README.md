# 📄 site2md

<div align="center">

![Tests](./docs/tests.svg)
![Coverage](./docs/coverage.svg)
![Version](https://img.shields.io/badge/version-0.6.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-brightgreen.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

**HTML to Markdown Converter** ✨

*Convert a local HTML tree or bounded remote web content into a Markdown document for LLM ingestion, offline reading, or archiving.*

<!-- benchmarks:chart:start -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/benchmark-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/benchmark-light.svg">
  <img alt="Bar chart of each tool's install size and the time it takes to extract the countries." src="docs/benchmark-light.svg">
</picture>

*Install size and time to extract the 250 countries from a local copy of [Scrape This Site's countries page](https://www.scrapethissite.com/pages/simple/) as JSON, for each tool as its project ships it, without a browser. [Details](BENCHMARKS.md).*
<!-- benchmarks:chart:end -->

[Installation](#-installation) • [Features](#-features) • [Usage](#-usage) • [Remote modes](#choose-a-remote-mode) • [Examples](#-examples) • [Benchmarks](#-benchmarks)

</div>

## 📦 Installation

### Standalone Executable (Windows/Linux) 🚀

The executable starts faster than a Python environment and needs neither Python nor pip. It is a second download next to the package, which stays the default install. Download the archive for your system from the [latest release](https://github.com/CamiloMartinezM/site2md/releases/latest). `<version>` below is the release's version, such as `0.6.0`.

- `site2md-<version>-windows-x86_64.zip` for Windows.
- `site2md-<version>-linux-x86_64.tar.gz` for Linux, built on Ubuntu 22.04, so it needs glibc 2.35 or newer.

There is no macOS executable, because Gatekeeper blocks unsigned programs. macOS users install the package, as below.

Unpack the archive. It holds one folder with the archive's name. Keep the executable and its `_internal` folder together in that folder, and put the folder on your `PATH`. These commands do that for the current session. To keep it, add the folder to your shell profile or to Windows' environment variables.

```bash
# Linux
tar -xzf site2md-<version>-linux-x86_64.tar.gz
export PATH="$PWD/site2md-<version>-linux-x86_64:$PATH"
```

```powershell
# Windows PowerShell
Expand-Archive site2md-<version>-windows-x86_64.zip .
$env:Path = "$PWD\site2md-<version>-windows-x86_64;$env:Path"
```

Check it with `site2md --version`. The release also holds a `SHA256SUMS` file for the archives: run `sha256sum --check --ignore-missing SHA256SUMS` on Linux, or compare the output of `Get-FileHash <archive>` with its line on Windows.

The executable ignores `PYTHONPATH`, so it can't see Extractor providers that pip installed elsewhere. Install each provider into a folder of its own with `pip install --target <folder> <provider>`, and name the folder in `SITE2MD_PROVIDER_PATH`. Several folders are separated as in `PATH`: `:` on Linux and `;` on Windows.

```bash
SITE2MD_PROVIDER_PATH=providers site2md extractors
```

A provider can use only the standard-library modules that the executable includes, and it can't replace a library that the executable already has. [Extractor providers](docs/extractor-providers.md#using-a-provider-with-the-executable) lists these limits and says when to pass `--no-deps`. Anyone who hits a limit uses the package.

### Quick Install (Linux/macOS) ⚡

```bash
chmod +x install.sh
./install.sh
```

### Manual Install from Source 📦

```bash
# Clone the repository
git clone https://github.com/CamiloMartinezM/site2md.git
cd site2md

# Install
pip install .
```

### Development Install 🏗 ️

```bash
# Install with editable mode
pip install -e .
```

---

## 🌐 Supported Inputs

- **Local Directories** - Convert and concatenate a folder of HTML files you already have.
- **Remote URLs** - Convert one server-rendered HTML page, explicitly follow selected same-origin links by one hop, or traverse a bounded same-origin site.

Remote conversion processes the HTML returned by the server. It doesn't run JavaScript, so it doesn't include content that requires client-side rendering. With `--browser`, page mode reads the page from a browser that is already installed instead, so content that a script adds is there ([below](#read-a-page-that-a-script-fills-in)).

---

## ✨ Features

### Core Features
- **One-Command Conversion** - From URL to single `.md` file in one go.
- **Safe Page Mode** - Fetches only the requested remote page and keeps its links usable.
- **Explicit Follow Mode** - Converts a page plus a bounded, selector-chosen set of same-origin child pages without recursive discovery.
- **Bounded Site Mode** - Discovers same-origin pages breadth first under explicit depth, page-count, content, query, robots, and pacing limits.
- **Intelligent Cleaning** - Automatically strips navigation bars, footers, and scripts using `BeautifulSoup`.
- **Markdownify Integration** - High-quality HTML-to-Markdown conversion.
- **Concatenation** - Merges local HTML files into one document with page separators.
- **Structured Extraction** - Runs an explicitly selected plug-in parser, called an Extractor, over converted Markdown and emits schema-validated, deterministic JSON with source provenance.
- **Progress Tracking** - Beautiful CLI with rich progress bars and status updates.
- **Zero bloat** - No heavy browser engines required (unlike PDF converters). `--browser` uses a Chrome, Edge or Chromium that you already have, and site2md never installs or downloads one.

### Why use site2md?
- **LLM Ready** - Create massive context files for RAG (Retrieval-Augmented Generation) applications.
- **Offline Reading** - Read documentation on your e-reader or Markdown view.
- **Archiving** - Save a local HTML collection or one remote page in a readable text format.

---

## 🚀 Usage

### Build Markdown

```bash
# Convert a local directory
site2md build ./input_folder --output manual.md

# Fetch and convert one remote page
site2md build https://example.com/article --output article.md

# Skip the progress bar, for scripts and benchmarks
site2md build https://example.com/article --output article.md --no-progress
```

If you omit `--output`, `site2md build` writes `complete_manual.md`.

`site2md build` draws a progress bar in every mode. `--no-progress` skips it and changes nothing else: the output file, the other messages and the exit status stay the same. It also keeps Rich's progress module from loading, which saves about 20 ms per page build. When the messages don't go to a terminal either, as in a script or a pipe, `build` prints the same lines without loading Rich at all, which saves about 35 ms more.

Remote input accepts three explicit modes. `page` is the default. `site2md` doesn't infer a broader mode from another option.

### Choose a remote mode

| Mode | Fetch scope | Use it for | Main boundary |
| --- | --- | --- | --- |
| `page` (default) | Only the requested page | An article, saved search, or other exact URL | No linked pages are fetched |
| `follow` | The entry page and selected links from that page | A listing page plus chosen detail pages | One hop, same origin, and explicit CSS selectors |
| `site` | The entry page and discovered links | A bounded documentation site or other small site | Same-origin breadth-first traversal with depth, page, and content limits |

All modes process the HTML that the server returns. They don't run JavaScript or use a browser session, so client-rendered content isn't included. Only page mode can read a page from a browser, with `--browser`, and from a signed-in session that a browser left in a folder, with `--browser-profile`.

#### Use page mode

Page mode fetches only the URL that you pass. You don't need to specify `--mode page` because it is the default.

```bash
site2md build https://example.com/article --output article.md
site2md build https://example.com/article --mode page --output article.md

# Override the default 25 MiB response limit
site2md build https://example.com/article \
  --max-page-size-mib 10 --output article.md
```

Use page mode when the URL already represents the content that you need. Links in the converted Markdown remain usable, but `site2md` doesn't fetch their destinations.

#### Read a page that a script fills in

Some pages arrive empty and fill themselves in with a script, so a plain build saves their frame and reports success. `--browser` loads the page in a Chrome, Edge or Chromium that is already installed, lets the page's scripts run, and converts what the browser then shows. It is for page mode and an `http://` or `https://` URL only.

```bash
site2md build https://example.com/app --browser --output app.md

# Use one particular browser instead of looking for one
SITE2MD_BROWSER="/opt/google/chrome/chrome" site2md build https://example.com/app --browser --output app.md
```

- **Which browser.** The program in `SITE2MD_BROWSER`, if it is set. Otherwise Chrome, then Edge, then Chromium, where each system installs them (on Windows, by their `App Paths` registry keys). site2md installs and downloads no browser, and without one the build fails with one line that names the variable.
- **When the page is read.** After 10 seconds of the page's own time: the browser fast-forwards the page's timers and holds its clock still while a request is under way, so a page that waits two seconds before it asks for its data doesn't cost two seconds. No option sets that budget.
- **What stays as in a plain fetch.** Only a final `2xx` response of type `text/html` or `application/xhtml+xml` is converted, by its `Content-Type` header. Redirects are followed and an HTTPS-to-HTTP downgrade is refused. The 30-second timeout runs from starting the browser to reading the page, and `--max-page-size-mib` limits the page as the browser shows it. The address that the browser ends on is the source, so the source marker and the links are those of a plain build. The same failure gives the same line, and an existing output file stays as it was.
- **What the browser loads.** Everything that the page asks for, as any browser does: its scripts, style sheets, fonts, images and data, from the page's host and from others, and the page's icon. Nothing is blocked, and nothing checks `robots.txt`: as in every page-mode build, the page is a direct request, and these requests belong to it. A plain build makes one request.
- **What it says.** The User-Agent is the browser's own, `HeadlessChrome` included, followed by ` site2md/<version>`.
- **What it doesn't do.** It doesn't hide that the browser is automated, and it doesn't answer a browser check, a CAPTCHA or any other defence of a site: a denial isn't a reason to bypass the restriction. The browser keeps its sandbox, and site2md never passes `--no-sandbox`, so where a browser can't start its sandbox the build fails with the browser's reason. Downloads are refused and dialogs are dismissed. It doesn't click, type or scroll, and it doesn't read frames or shadow roots. Content that the page hides with CSS still comes out.
- **The profile.** Each build uses a new temporary profile, which is removed afterwards with every browser process, also after a failure or an interruption. `--keep-temp` never keeps it. A page that only signed-in visitors get needs `--browser-profile` ([below](#read-a-page-that-only-signed-in-visitors-get)).
- **Platforms.** It works on Windows and Linux. The browser takes its commands over a pipe that only site2md and the browser hold, and no port is opened. macOS isn't promised.

The page's markup comes out of the browser as text, so the page is stored as UTF-8 whatever its `<meta charset>` says. With `--keep-temp`, `page.html` may therefore still name another charset.

Use it only on sites whose terms allow automated access.

#### Read a page that only signed-in visitors get

`--browser-profile FOLDER` makes the browser use a folder that you name as its profile instead of a temporary one, and the folder stays afterwards. If a session is in it, `--browser` reads the page as the signed-in visitor sees it. It needs `--browser`, and it is rejected without it.

```bash
# Once: start the same browser with the folder, sign in to the site, and close the browser
chrome --user-data-dir=/path/to/profile https://example.com/sign-in

# Then, for as long as the session lasts
site2md build https://example.com/members --browser --browser-profile /path/to/profile --output members.md
```

- **The sign-in is yours.** site2md has no window of its own for signing in, and it doesn't attach to a browser that is already running. You start the same browser with `--user-data-dir=FOLDER`, sign in, and close it. Only what the browser keeps after it closes is in the folder: a session that ends with the browser isn't, and neither is one that the site ends after a while.
- **A folder that exists.** The folder must exist, and the build fails before any request when it doesn't, so that a typo can't start a new profile that reads the page as a stranger.
- **Not your everyday profile.** The folder can't be the profile that your browser uses every day. Since version 136, Chrome refuses remote debugging on its default profile, so use a folder of its own.
- **Not open elsewhere.** A folder that another browser has open fails with one line. Close that browser first.
- **It stays as it is.** site2md never removes, empties or copies anything out of the folder, also not after a failure or an interruption, and not with `--keep-temp`: the workspace that it keeps holds the page and its Markdown, and nothing from the folder. The browser changes the folder as it runs, as it does for any profile.
- **Treat the folder like a password.** It holds the session of your account, so don't share it, and don't commit it.

Use it only on sites whose terms allow automated access. A session is an account's, and the account's terms apply to what you do with it.

#### Use follow mode

Follow mode is designed for a listing or index page whose selected detail pages belong in the same Markdown document. Each `--follow-selector` value is a CSS selector that must match `<a href="...">` elements in the entry page's original HTML.

```bash
site2md build https://example.com/results --mode follow \
  --follow-selector "a.result" \
  --follow-selector "a.featured" \
  --max-pages 20 \
  --max-total-size-mib 100 \
  --output results.md
```

Follow mode applies these rules:

- At least one selector is required. Multiple selectors form one union in entry-document order.
- Only unique same-origin HTTP and HTTPS links are eligible.
- The entry page appears first, followed by successful matches in document order.
- The traversal is one hop. Links on followed pages don't add more targets.
- Explicitly selected query-bearing links and `rel="nofollow"` links remain eligible.
- `--max-pages 20` counts the entry page, so the command admits at most 19 unique child targets.

An invalid selector or a selection with no eligible links is fatal. `site2md` makes no child requests and preserves an existing output file.

#### Use site mode

Site mode discovers same-origin links breadth first. The entry page is depth zero, and links retain document order within each depth.

```bash
site2md build https://example.com/docs/ --mode site \
  --max-pages 20 \
  --max-depth 2 \
  --max-total-size-mib 100 \
  --output docs.md
```

Site mode skips query-bearing links by default. This blocks a common source of combinatorial expansion, including filters, sorting links, and calendars encoded in query strings. Page, depth, and content limits remain hard boundaries for other link patterns. If a site requires query-bearing pages, opt in explicitly and keep restrictive traversal budgets:

```bash
site2md build https://example.com/catalog --mode site \
  --include-query --max-pages 10 --max-depth 1 \
  --output catalog.md
```

Site mode also skips `rel="nofollow"` links. It doesn't discover forms, sitemaps, assets, or links created by JavaScript.

### Control remote traversal

The following options define the remote scope and resource limits:

| Option | Modes | Default | Effect |
| --- | --- | --- | --- |
| `--follow-selector SELECTOR` | `follow` | Required | Selects entry-page anchors; repeat it to form a union |
| `--max-pages COUNT` | `follow`, `site` | `50` | Limits the entry page plus every unique child admitted for processing |
| `--max-depth DEPTH` | `site` | `3` | Limits breadth-first discovery; the entry page is depth zero |
| `--include-query` | `site` | Off | Includes discovered URLs that contain query strings |
| `--max-page-size-mib SIZE` | All remote modes | `25` | Limits each HTML page response |
| `--browser` | `page` | Off | Reads the page from an installed browser after its scripts have run ([above](#read-a-page-that-a-script-fills-in)) |
| `--browser-profile FOLDER` | `page`, with `--browser` | A temporary profile | Uses an existing folder as the browser's profile, and leaves it in place, so that the page is read with the session in it ([above](#read-a-page-that-only-signed-in-visitors-get)) |
| `--max-total-size-mib SIZE` | `follow`, `site` | `250` | Limits all received page-body content, including partial or discarded responses |
| `--keep-temp` | All remote modes | Off | Retains the remote-build workspace after success or failure |

All numeric limits require positive integers. Page mode rejects traversal-only options. Follow mode rejects `--max-depth` and `--include-query`. Site mode rejects `--follow-selector`. `--browser` needs page mode. `--browser-profile` needs `--browser` and an existing folder. Local input rejects remote-only options. Invalid combinations fail before a network request.

Before requesting child pages, follow and site modes retrieve and enforce `robots.txt` with a separate 512 KiB limit. Child requests are sequential and spaced by at least one second, or by a longer applicable crawl delay or request-rate interval. A `4xx` response for `robots.txt` permits traversal. An unreachable or oversized policy stops child traversal and produces a warning.

Remote fetches use a 30-second timeout, a versioned `site2md` user agent, and no automatic retries. They accept final, nonempty `text/html` or `application/xhtml+xml` responses with a `2xx` status. Redirects can use HTTP or HTTPS, but HTTPS-to-HTTP downgrades are rejected. Child redirects must remain on the traversal origin.

Use traversal only when the website's robots policy and terms permit automated access. Policy denial is an expected boundary and isn't a reason to bypass the restriction.

### Understand traversal output and failures

Follow and site modes produce one Markdown document. The entry page appears first, followed by successful child pages in deterministic order. Source markers and section separators preserve each page's provenance. To extract structured data, pass the completed multi-source document to `site2md extract` in a separate command, or add `--extract` to `build` ([below](#convert-and-extract-in-one-command)).

Expected child failures produce warnings and don't discard pages that were already converted. Reaching a page, depth, or aggregate-content limit also completes successfully with a bounded partial document. Entry-page failures, invalid follow selections, interruptions, unexpected failures, and output failures are fatal and preserve an existing destination.

With `--keep-temp`, the retained workspace contains fetched HTML, available partial child data, converted fragments, the assembled document, and `index.json`. The index maps attempted URLs to their status and available files for debugging. Its format is unstable and has no compatibility guarantees.

By default, `site2md` removes temporary remote data after successful and failed conversions. See the [traversal policy](docs/traversal-policy.md) for the complete URL identity, ordering, resource-accounting, and failure contract.

### Extract structured data

```bash
# Inspect installed Extractors without running provider code
site2md extractors

# Extract deterministic JSON from a converted document
site2md extract site2md.scrapethissite.countries converted.md
cat converted.md | site2md extract site2md.scrapethissite.countries -

# Atomically replace a JSON output file after successful extraction
site2md extract site2md.scrapethissite.countries converted.md --output records.json

# Look up the Extractor faster by skipping distributions without an entry point
site2md extract site2md.scrapethissite.countries converted.md --entry-points-only

# Write only the record values, without the provenance and the rest of the result
site2md extract site2md.scrapethissite.countries converted.md --values-only
```

Without `--output`, `extract` writes only the JSON document to standard output. Warnings are included in that document and repeated concisely on standard error. Markdown input must be UTF-8. Failures before standard-output emission leave standard output empty. If an output stream accepts a prefix and then fails, that prefix cannot be rolled back; the command exits with status `1` and the stream can contain incomplete JSON. An existing output file is replaced only after the complete JSON document has been serialized and flushed successfully.

`--values-only` writes a JSON array of the record values instead of the extraction result. The array keeps record order and uses the same serialization as the result: UTF-8, a two-space indent, non-ASCII characters kept, and a trailing newline. The option drops the provenance, the Extractor, provider and record schema identity, the input digest, and the source sections, so the output no longer says which Extractor produced it or from which input. Warnings then appear only on standard error, and a failure still writes nothing.

Extractor IDs are exact and case-sensitive; `site2md` never guesses which Extractor to use. `extractors` lists installed providers from their static metadata without importing their code. Extractors are trusted, in-process Python plug-ins: they are not sandboxed, and interface version 1 does not provide per-run configuration. Install or remove third-party provider packages with normal Python package tooling. See the [Extractor provider guide](docs/extractor-providers.md) for the complete contract.

By default, `extract` inspects every installed distribution, so a distribution that ships a provider manifest without an entry point is still noticed: if it claims the requested Extractor ID, `extract` reports a conflict or an unavailable Extractor instead of running. `--entry-points-only` skips distributions that declare no `site2md.extractors.v1` entry point, which makes the lookup faster. With it, `extract` doesn't notice a distribution that ships a manifest without an entry point, though `site2md extractors` still reports it. When every provider declares its entry point, the output is identical with and without the option.

#### Convert and extract in one command

```bash
# Save the converted document, then print the extraction result
site2md build https://example.com/countries --output countries.md   --extract site2md.scrapethissite.countries

# Write only the record values to a file instead
site2md build ./input_folder --output manual.md   --extract site2md.scrapethissite.countries --extract-output records.json --values-only
```

`build --extract ID` saves the converted document as usual, then runs the Extractor on exactly the saved Markdown in the same process. That saves starting a second Python process. It works for local input and in every remote mode, and the result matches what `site2md extract ID FILE` writes for the saved file, byte for byte. `--entry-points-only` and `--values-only` work as they do on `extract`.

Without `--extract-output`, the result goes to standard output. `--extract-output PATH` replaces a file atomically instead, as `extract --output` does. With `--extract`, build's own messages and its progress bar go to standard error, so standard output holds only the JSON. `--extract-output`, `--entry-points-only` and `--values-only` need `--extract`, and `--extract-output` can't name the same file as `--output`. These mistakes, and an `--extract-output` folder that doesn't exist, fail before any request.

`build` doesn't check first that the Extractor exists. A mistyped ID costs a fetch or a crawl, but loses nothing, because the converted document is saved first. If the Extractor is missing or fails, the Markdown stays where it was saved and the command exits with status `1`. It reports the error and any diagnostics as `extract` does, then names the Markdown file, so that you can rerun `site2md extract` on it. A local folder without HTML files also exits with status `1` under `--extract`, because there is no document to extract from. Without `--extract`, `build` behaves as before and doesn't load the extraction code.

Extraction is synchronous and whole-document based. It adds no Markdown size limit; memory use grows with the input document and extraction result.

### Private Extractors

To keep a local Extractor out of normal Git commits, create its standalone provider project in `src/site2md/extractors/private/`. Git ignores the entire directory, so normal commits and fresh clones do not include its contents.

Use a flat package layout:

```text
src/site2md/extractors/private/
├── pyproject.toml
├── site2md_private_extractors/
└── tests/
```

The private `pyproject.toml` defines the provider distribution, entry point, and static manifest without adding private metadata to the public project configuration. Install the provider in the same Python environment as `site2md`:

```bash
python -m pip install -e src/site2md/extractors/private
site2md extractors
```

The `private` directory controls what Git tracks. It does not add runtime isolation; private Extractors use the same trusted, in-process execution model as other providers.

---

## 💡 Examples

### Parse Scrape This Site Country Data

The built-in country Extractor turns repeated country sections from the [Scrape This Site countries practice page](https://www.scrapethissite.com/pages/simple/) into structured records.

```bash
site2md build https://www.scrapethissite.com/pages/simple/ --output countries.md
site2md extract site2md.scrapethissite.countries countries.md --output countries.json
```

#### Raw Converted Markdown

The converted Markdown keeps the page's readable headings and labels:

```markdown
### Andorra

**Capital:** Andorra la Vella
**Population:** 84000
**Area (km2):** 468.0
```

#### Parsed JSON

The Extractor converts numbers to JSON-native types, and `site2md` validates each record. `countries.json` also contains Extractor metadata, diagnostics, and source provenance. Its first record has this `value`:

```json
{
  "name": "Andorra",
  "capital": "Andorra la Vella",
  "population": 84000,
  "area_km2": 468.0
}
```

---

## 📊 Benchmarks

site2md against the tools you might pick instead. Every tool extracts the same 250 countries from a local copy of the [Scrape This Site countries page](https://www.scrapethissite.com/pages/simple/) and must produce exactly the same JSON. Each tool's solution gets whatever code that takes, and its lines are the non-blank, non-comment lines a user would write, imports included. Time is the page task, as the mean ± standard deviation over fresh processes. The crawl starts from a generated local site and is checked once, never timed, because site2md spaces its requests at least one second apart and has no override. [BENCHMARKS.md](BENCHMARKS.md) has the method, the versions, the raw results, how to rerun them and the tools left out.

<!-- benchmarks:table:start -->
| Tool | Time | Lines (page) | Lines (crawl) | Install size |
|---|---|---|---|---|
| site2md | 349 ms ± 8 ms | 49 | 49 | 11.5 MB |
| site2md executable | 264 ms ± 8 ms | 49 | 49 | 27.2 MB [^1] |
| Scrapling | 334 ms ± 6 ms | 12 [^2] | 19 [^3] [^2] | 242.8 MB [^4] |
| crawl4ai | 1.07 s ± 0.04 s | 24 [^5] [^2] | 38 [^6] [^2] | 554.8 MB [^7] |
| MarkItDown | 635 ms ± 18 ms | 10 [^2] | – [^8] | 94.8 MB |
| pandoc | 254 ms ± 12 ms | 12 [^2] | – [^8] | 239.6 MB [^9] |

[^1]: The unpacked archive: `site2md.exe`, which holds site2md and its pure-Python libraries, and the `_internal` folder, which holds the Python 3.12 runtime, OpenSSL and the compiled modules. It is a bundle, not a set of pip packages, so its package count reads 0.
[^2]: Not counted: `import sys`. The harness passes the local server's 127.0.0.1 URL on the command line, and this code only reads it. A solution for the live site writes the URL inline.
[^3]: Scrapling's spiders have no depth limit, and the `max_pages` of its Markdown spider limits what it converts, not what it fetches. The spider therefore carries each page's depth in its requests and keeps its own set of the pages it has queued. Without them it fetches the five decoy pages.
[^4]: The `fetchers` extra also installs Playwright and Patchright, which take 110 MB each because each bundles a Node driver. No browser is downloaded.
[^5]: crawl4ai's `crwl` command line does the task in one line, but it always starts a browser, so that line isn't counted. The count is for the Python solution, which uses the HTTP-only crawler strategy.
[^6]: crawl4ai's breadth-first crawl never marks the entry page as visited, so every page that links back to it queues it again. A filter keeps it out. Without the filter the entry page is fetched twice, and the second fetch uses one of the 20 pages, so a country page is left out.
[^7]: crawl4ai requires Playwright and Patchright even for its HTTP-only strategy, so no smaller install exists. They take 110 MB each because each bundles a Node driver. No browser is downloaded.
[^8]: No crawler.
[^9]: The unpacked archive: `pandoc.exe`, its manual and its licence files. pandoc is not a Python package, so its package count reads 0.
<!-- benchmarks:table:end -->

---

## 📚 Documentation

The tool is self-documenting via the CLI. Release-specific behavior and limits are recorded in the [0.6.0](docs/release-0.6.0.md), [0.5.0](docs/release-0.5.0.md) and [0.4.0](docs/release-0.4.0.md) release notes and the [0.4.1](docs/release-0.4.1.md), [0.4.2](docs/release-0.4.2.md), [0.4.3](docs/release-0.4.3.md), [0.4.4](docs/release-0.4.4.md), [0.4.5](docs/release-0.4.5.md) and [0.4.6](docs/release-0.4.6.md) patch notes.

```bash
site2md --help
site2md build --help
site2md extract --help
site2md extractors --help
```

---

## 🔧 Requirements

### Required
- **Python 3.10** or higher

Remote page conversion doesn't require `wget` or a browser engine. Only `--browser` needs a Chrome, Edge or Chromium, which you install yourself.

### Dependencies (Installed automatically)
- `cyclopts` - For the CLI interface
- `markdownify` - For conversion
- `beautifulsoup4` - For HTML parsing
- `soupsieve` - For CSS follow-selector matching
- `rich` - For terminal output
- `marko` - For interpreting converted documents behind the provider interface
- `jsonschema` - For validating provider schemas and extracted records
- `packaging` - For validating provider versions

---

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest new features
- Submit pull requests

---

## 📜 License

This project is licensed under the [MIT License](LICENSE).

---

## ⚖️ Disclaimer

This tool is for educational and personal archiving purposes. Please respect copyright laws and the terms of service of the websites you download from.

---

<div align="center">

If this tool helped you, consider giving it a ⭐ on [GitHub](https://github.com/CamiloMartinezM/site2md)

</div>
