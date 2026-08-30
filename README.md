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
- **Remote URLs** - Fetch and convert one server-rendered HTML page without following its links.

Remote conversion processes the HTML returned by the server. It doesn't run JavaScript, so it doesn't include content that requires client-side rendering.

---

## ✨ Features

### Core Features
- **One-Command Conversion** - From URL to single `.md` file in one go.
- **Safe Page Mode** - Fetches only the requested remote page and keeps its links usable.
- **Intelligent Cleaning** - Automatically strips navigation bars, footers, and scripts using `BeautifulSoup`.
- **Markdownify Integration** - High-quality HTML-to-Markdown conversion.
- **Concatenation** - Merges local HTML files into one document with page separators.
- **Structured Extraction** - Runs an explicitly selected Extractor over converted Markdown and emits validated, deterministic JSON with source provenance.
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

# Keep temporary remote page data after success or failure
site2md build https://example.com --keep-temp

# Inspect installed structured-data Extractors without running provider code
site2md extractors

# Extract deterministic JSON from converted Markdown
site2md extract site2md.scrapethissite.countries converted.md
cat converted.md | site2md extract site2md.scrapethissite.countries -

# Atomically replace a JSON output file after successful extraction
site2md extract site2md.scrapethissite.countries converted.md --output records.json
```

Without `--output`, `extract` writes only the JSON document to standard output. Warnings are included in that document and repeated concisely on standard error. Markdown input must be UTF-8. Extraction and output failures leave standard output empty, and an existing output file is replaced only after the complete JSON document has been serialized and flushed successfully.

Extractor IDs are exact and case-sensitive; `site2md` never guesses which Extractor to use. `extractors` lists installed providers from their static metadata without importing their code. Extractors are trusted, in-process Python plug-ins: they are not sandboxed, and interface version 1 does not provide per-run configuration. Install or remove third-party provider packages with normal Python package tooling. See the [Extractor provider guide](docs/extractor-providers.md) for the complete contract.

Extraction is synchronous and whole-document based. It adds no Markdown size limit; memory use grows with the input document and extraction result.

### Build Options

- `--output`: Specify the output filename (default: `complete_manual.md`).
- `--mode page`: Explicitly select page mode for a remote URL. Page mode is the default and only available remote mode.
- `--max-page-size-mib`: Set a positive integer response-size limit for one remote page. This option applies only to remote URLs and defaults to 25 MiB.
- `--keep-temp`: Preserve temporary remote page data after success or failure. The command prints the retained path.

Remote fetches use a 30-second timeout, a `site2md/0.3.0` user agent, and no automatic retries. They accept only final, nonempty `text/html` or `application/xhtml+xml` responses with a `2xx` status code. The command follows HTTP and HTTPS redirects except for HTTPS-to-HTTP downgrades.

Remote fetch and validation failures preserve an existing output file. By default, the command removes temporary remote data after both successful and failed conversions.

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
- `marko` - For interpreting converted Markdown behind the provider interface
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
