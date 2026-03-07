# 📄 site2md

<div align="center">

![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-brightgreen.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

**Professional Website to Markdown Converter** ✨

*A powerful, feature-rich tool to convert entire websites into a single Markdown document for LLM ingestion, offline reading, or archiving.*


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

- **Static Websites** - Documentation sites, blogs, portfolios.
- **Local Directories** - Convert a folder of HTML files you already have.
- **Remote URLs** - Automatically mirrors files using `wget` before conversion.

---

## ✨ Features

### Core Features
- **One-Command Conversion** - From URL to single `.md` file in one go.
- **Smart Mirroring** - Uses `wget` robustly to download all page requisites locally.
- **Intelligent Cleaning** - Automatically strips navigation bars, footers, and scripts using `BeautifulSoup`.
- **Markdownify Integration** - High-quality HTML-to-Markdown conversion.
- **Concatenation** - Merges hundreds of pages into one seamless manual with page separators.
- **Progress Tracking** - Beautiful CLI with rich progress bars and status updates.
- **Zero bloat** - No heavy browser engines required (unlike PDF converters).

### Why use site2md?
- **LLM Ready** - Create massive context files for RAG (Retrieval-Augmented Generation) applications.
- **Offline Reading** - Read documentation on your e-reader or Markdown view.
- **Archiving** - Snapshot an entire website into a readable text format.

---

## 🚀 Usage

### Command Line Mode

```bash
# Download and convert from a URL
site2md build https://yasa-sleep.org/index.html --output manual.md

# Convert a local directory
site2md build ./input_folder --output manual.md

# Keep temporary download files (for debugging)
site2md build https://example.com --keep-temp
```

### Options

- `--output`: Specify the output filename (default: `complete_manual.md`).
- `--keep-temp`: Don't delete the folder downloaded by `wget`.

---

## 📚 Documentation

The tool is self-documenting via the CLI.

```bash
site2md --help
site2md build --help
```

---

## 🔧 Requirements

### Required
- **Python 3.10** or higher
- **wget** (accessible in system PATH) - Required for URL mirroring.
  - **Linux**: Usually pre-installed or `sudo apt install wget`
  - **macOS**: `brew install wget`

### Dependencies (Installed automatically)
- `cyclopts` - For the CLI interface
- `markdownify` - For conversion
- `beautifulsoup4` - For HTML parsing
- `rich` - For the beautiful terminal UI

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

**Made with ❤️ with [Google Antigravity](https://antigravity.google/)**

If this tool helped you, consider giving it a ⭐ on [GitHub](https://github.com/CamiloMartinezM/site2md)

</div>
