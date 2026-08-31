# 📄 site2md

<div align="center">

![Version](https://img.shields.io/badge/version-0.3.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-brightgreen.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

**HTML to Markdown Converter** ✨

*Convert a local HTML tree or one remote web page into a Markdown document for LLM ingestion, offline reading, or archiving.*


[Installation](#-installation) • [Features](#-features) • [Usage](#-usage) • [Examples](#-examples)

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
- **Remote URLs** - Convert one server-rendered HTML page, or explicitly follow selected same-origin links by one hop.

Remote conversion processes the HTML returned by the server. It doesn't run JavaScript, so it doesn't include content that requires client-side rendering.

---

## ✨ Features

### Core Features
- **One-Command Conversion** - From URL to single `.md` file in one go.
- **Safe Page Mode** - Fetches only the requested remote page and keeps its links usable.
- **Explicit Follow Mode** - Converts a page plus a bounded, selector-chosen set of same-origin child pages without recursive discovery.
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

### Command Line Mode

```bash
# Fetch and convert one remote page (page mode is the default)
site2md build https://yasa-sleep.org/index.html --output manual.md
site2md build https://yasa-sleep.org/index.html --mode page --output manual.md

# Convert a local directory
site2md build ./input_folder --output manual.md

# Limit the remote page response size (default: 25 MiB)
site2md build https://example.com --max-page-size-mib 10 --output page.md

# Follow selected anchors from the entry page in document order
site2md build https://example.com/results --mode follow \
  --follow-selector "a.result" --follow-selector "a.featured" \
  --max-pages 20 --max-total-size-mib 100 --output results.md

# Keep temporary remote page data after success or failure
site2md build https://example.com --keep-temp

# Inspect installed structured-data Extractors without running provider code
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

### Build Options

- `--output`: Specify the output filename (default: `complete_manual.md`).
- `--mode page`: Convert only the requested remote page. This remains the default.
- `--mode follow`: Convert the entry page and one hop of explicitly selected same-origin anchors.
- `--follow-selector`: Select anchors from the original entry HTML with a CSS selector. Repeat the option to form a union; output order follows document order, not option order. Follow mode requires at least one selector.
- `--max-pages`: Set a positive follow-mode page budget, including the entry page and every unique child admitted for processing (default: 50).
- `--max-total-size-mib`: Set a positive follow-mode aggregate HTML body budget (default: 250 MiB).
- `--max-page-size-mib`: Set a positive integer response-size limit for one remote page. This option applies only to remote URLs and defaults to 25 MiB.
- `--keep-temp`: Preserve temporary remote page data after success or failure. The command prints the retained path.

Remote fetches use a 30-second timeout, a `site2md/0.3.0` user agent, and no automatic retries. They accept only final, nonempty `text/html` or `application/xhtml+xml` responses with a `2xx` status code. The command follows HTTP and HTTPS redirects except for HTTPS-to-HTTP downgrades.

Follow mode removes URL fragments for identity, normalizes origins and default ports, preserves path and query meaning, and honors an HTML `base` element. Explicitly selected query-bearing and `rel="nofollow"` anchors remain eligible. Child pages never contribute more targets. Before children are requested, follow mode retrieves `robots.txt` with a separate 512 KiB cap, enforces the policy, and spaces sequential child requests by at least one second or the greater applicable crawl delay or request-rate interval. A missing `4xx` robots policy permits following; an unreachable or oversized policy stops child requests and writes the bounded entry-page result with a warning.

Expected child failures and reached page or aggregate limits produce warnings and a successful bounded document containing the pages converted so far. Entry, selector, interruption, unexpected, and output failures preserve an existing destination. Successful pages keep their source markers and remain valid input to `site2md extract`.

With `--keep-temp`, the retained workspace contains fetched HTML, incomplete child data when available, per-page converted fragments, the assembled document, and `index.json`. The index maps each attempted URL to its available files and status for human debugging. Its JSON format is intentionally unstable and has no compatibility guarantees.

Remote fetch and validation failures preserve an existing output file. By default, the command removes temporary remote data after both successful and failed conversions.

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

The tool is self-documenting via the CLI.

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
