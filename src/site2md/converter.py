"""Module for converting HTML content to Markdown."""

import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from markdownify import markdownify as md

from site2md.downloader import RemotePage


def convert_html_to_markdown(html_path: Path) -> str:
    """Convert a local HTML file to a Markdown string."""
    try:
        html_content = html_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html_content, "html.parser")
        return _convert_soup_to_markdown(soup, html_path.name)
    except Exception as error:
        print(f"Error converting {html_path}: {error}", file=sys.stderr)
        return f"\n\n<!-- Error converting {html_path.name} -->\n\n"


def convert_remote_page_to_markdown(page: RemotePage) -> str:
    """Convert a remote page while retaining usable remote references."""
    try:
        soup = BeautifulSoup(
            page.content_path.read_bytes(),
            "html.parser",
            from_encoding=page.encoding,
        )
        _resolve_remote_references(soup, page.source_url)
        return _convert_soup_to_markdown(soup, page.source_url)
    except Exception as error:
        print(f"Error converting {page.source_url}: {error}", file=sys.stderr)
        return f"\n\n<!-- Error converting {page.source_url} -->\n\n"


def _resolve_remote_references(soup: BeautifulSoup, source_url: str) -> None:
    """Resolve relative links and images using HTML base URL rules."""
    base_url = source_url
    base_tag = soup.find("base", href=True)
    if base_tag:
        base_href = base_tag.get("href")
        if isinstance(base_href, str):
            base_url = urljoin(source_url, base_href)

    for attribute in ("href", "src"):
        for tag in soup.find_all(attrs={attribute: True}):
            value = tag.get(attribute)
            if isinstance(value, str):
                tag[attribute] = _resolve_reference(value, base_url)


def _resolve_reference(reference: str, base_url: str) -> str:
    """Resolve one web reference without changing local or non-HTTP references."""
    if not reference or reference.startswith("#"):
        return reference

    parsed = urlsplit(reference)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return reference
    return urljoin(base_url, reference)


def _convert_soup_to_markdown(soup: BeautifulSoup, source: str) -> str:
    """Clean parsed HTML and add its source attribution to Markdown output."""
    for selector in [
        "nav",
        ".bd-sidebar",
        ".bd-header",
        ".bd-footer",
        ".skip-link",
        ".pst-scroll-pixel-helper",
        ".pst-async-banner-revealer",
        "script",
        "style",
        "noscript",
        ".headerlink",
    ]:
        for tag in soup.select(selector):
            tag.decompose()

    main_content = (
        soup.select_one("main")
        or soup.select_one("article")
        or soup.select_one(".bd-content")
        or soup.body
    )
    text = str(main_content) if main_content else str(soup)
    markdown = md(text, heading_style="atx")
    return f"\n\n<!-- Source: {source} -->\n\n" + markdown
