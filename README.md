# 📄 site2md

<div align="center">

![Version](https://img.shields.io/badge/version-0.4.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-brightgreen.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

**HTML to Markdown Converter** ✨

*Convert a local HTML tree or bounded remote web content into a Markdown document for LLM ingestion, offline reading, or archiving.*


[Installation](#-installation) • [Features](#-features) • [Usage](#-usage) • [Remote modes](#choose-a-remote-mode) • [Examples](#-examples)

</div>

## 📦 Installation

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

Remote conversion processes the HTML returned by the server. It doesn't run JavaScript, so it doesn't include content that requires client-side rendering.

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
- **Zero bloat** - No heavy browser engines required (unlike PDF converters).

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
```

If you omit `--output`, `site2md build` writes `complete_manual.md`.

Remote input accepts three explicit modes. `page` is the default. `site2md` doesn't infer a broader mode from another option.

### Choose a remote mode

| Mode | Fetch scope | Use it for | Main boundary |
| --- | --- | --- | --- |
| `page` (default) | Only the requested page | An article, saved search, or other exact URL | No linked pages are fetched |
| `follow` | The entry page and selected links from that page | A listing page plus chosen detail pages | One hop, same origin, and explicit CSS selectors |
| `site` | The entry page and discovered links | A bounded documentation site or other small site | Same-origin breadth-first traversal with depth, page, and content limits |

All modes process the HTML that the server returns. They don't run JavaScript or use a browser session, so client-rendered content isn't included.

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
| `--max-total-size-mib SIZE` | `follow`, `site` | `250` | Limits all received page-body content, including partial or discarded responses |
| `--keep-temp` | All remote modes | Off | Retains the remote-build workspace after success or failure |

All numeric limits require positive integers. Page mode rejects traversal-only options. Follow mode rejects `--max-depth` and `--include-query`. Site mode rejects `--follow-selector`. Local input rejects remote-only options. Invalid combinations fail before a network request.

Before requesting child pages, follow and site modes retrieve and enforce `robots.txt` with a separate 512 KiB limit. Child requests are sequential and spaced by at least one second, or by a longer applicable crawl delay or request-rate interval. A `4xx` response for `robots.txt` permits traversal. An unreachable or oversized policy stops child traversal and produces a warning.

Remote fetches use a 30-second timeout, a versioned `site2md` user agent, and no automatic retries. They accept final, nonempty `text/html` or `application/xhtml+xml` responses with a `2xx` status. Redirects can use HTTP or HTTPS, but HTTPS-to-HTTP downgrades are rejected. Child redirects must remain on the traversal origin.

Use traversal only when the website's robots policy and terms permit automated access. Policy denial is an expected boundary and isn't a reason to bypass the restriction.

### Understand traversal output and failures

Follow and site modes produce one Markdown document. The entry page appears first, followed by successful child pages in deterministic order. Source markers and section separators preserve each page's provenance. To extract structured data, pass the completed multi-source document to `site2md extract` in a separate command.

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
```

Without `--output`, `extract` writes only the JSON document to standard output. Warnings are included in that document and repeated concisely on standard error. Markdown input must be UTF-8. Failures before standard-output emission leave standard output empty. If an output stream accepts a prefix and then fails, that prefix cannot be rolled back; the command exits with status `1` and the stream can contain incomplete JSON. An existing output file is replaced only after the complete JSON document has been serialized and flushed successfully.

Extractor IDs are exact and case-sensitive; `site2md` never guesses which Extractor to use. `extractors` lists installed providers from their static metadata without importing their code. Extractors are trusted, in-process Python plug-ins: they are not sandboxed, and interface version 1 does not provide per-run configuration. Install or remove third-party provider packages with normal Python package tooling. See the [Extractor provider guide](docs/extractor-providers.md) for the complete contract.

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

## 📚 Documentation

The tool is self-documenting via the CLI. Release-specific behavior and limits are recorded in the [0.4.0 release notes](docs/release-0.4.0.md).

```bash
site2md --help
site2md build --help
site2md extract --help
site2md extractors --help
```

---

## 🔧 Requirements

### Required
- **Python 3.9** or higher

Remote page conversion doesn't require `wget` or a browser engine.

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
