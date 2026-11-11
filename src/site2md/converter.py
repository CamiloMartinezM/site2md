"""Module for converting HTML content to Markdown."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from bs4.element import PreformattedString
from markdownify import MarkdownConverter

from site2md._formulas import FORMULA
from site2md._mathml import math_to_tex
from site2md.downloader import RemotePage

_EXCLUDED_TAG_NAMES = frozenset({"nav", "script", "style", "noscript"})
_EXCLUDED_CLASS_NAMES = frozenset(
    {
        "bd-sidebar",
        "bd-header",
        "bd-footer",
        "skip-link",
        "pst-scroll-pixel-helper",
        "pst-async-banner-revealer",
        "headerlink",
    }
)
# Some html.parser versions read the text of these elements raw, so it changes when it is parsed twice.
_RAW_TEXT_TAG_NAMES = frozenset({"iframe", "noembed", "noframes", "plaintext", "xmp"})
# The wrappers of a rendered formula, whose MathML says what their hidden visual copy shows again.
_FORMULA_CLASS_NAMES = frozenset({"katex", "MathJax"})
# MathJax 2 keeps the author's TeX in a script of this type, and a display formula says so in its mode.
_TEX_SCRIPT_TYPE = re.compile(r"\s*math/tex\s*(?:;\s*mode\s*=\s*(display))?\s*", re.IGNORECASE)


class _Tag(Tag):
    """A tag that finds a parent by name without a search filter: markdownify asks at every element."""

    def find_parent(self, name: Any = None, attrs: Any = {}, **kwargs: Any) -> Tag | None:
        if type(name) is str and not attrs and not kwargs:
            parent = self.parent
            while parent is not None and parent.name != name:
                parent = parent.parent
            return parent
        return super().find_parent(name, attrs, **kwargs)


class _Converter(MarkdownConverter):
    """A converter that writes formulas as TeX, and a loose list with blank lines between its items."""

    def __init__(self, **options: Any) -> None:
        super().__init__(**options)
        # The last item of each loose list, by the id of its list, so that a list is read once and not at every item.
        self._last_items_of_loose_lists: dict[int, Tag | None] = {}

    def convert_li(self, el: Tag, text: str | None, parent_tags: set[str]) -> str:
        """Write a list item, and a blank line after it unless it is the last of a loose list."""
        item: str = super().convert_li(el, text, parent_tags)  # type: ignore[misc]
        parent = el.parent
        if parent is None:
            return item
        last_item = self._last_item_of_loose_list(parent)
        # Identity, not equality: comparing two tags compares their whole content.
        return item + "\n" if last_item is not None and last_item is not el else item

    def _last_item_of_loose_list(self, list_tag: Tag) -> Tag | None:
        """Return the last item of a list where an item has a paragraph as a direct child, else None."""
        key = id(list_tag)
        if key not in self._last_items_of_loose_lists:
            items = [c for c in list_tag.children if isinstance(c, Tag) and c.name == "li"]
            is_loose = any(isinstance(c, Tag) and c.name == "p" for item in items for c in item.children)
            self._last_items_of_loose_lists[key] = items[-1] if is_loose else None
        return self._last_items_of_loose_lists[key]

    def escape(self, text: str, parent_tags: set[str]) -> str:
        """Escape the text of a node except its formulas, where `_` and `*` are TeX and not Markdown."""
        # The stub of markdownify 1.2 leaves out `escape`, which every supported version has.
        escape_prose = super().escape  # type: ignore[misc]
        # Every formula holds a dollar sign or a backslash, and most text holds neither.
        if "$" not in text and "\\" not in text:
            return escape_prose(text, parent_tags)
        escaped: list[str] = []
        end = 0
        for formula in FORMULA.finditer(text):
            escaped.append(escape_prose(text[end : formula.start()], parent_tags))
            escaped.append(formula.group())
            end = formula.end()
        escaped.append(escape_prose(text[end:], parent_tags))
        return "".join(escaped)

    def convert_math(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        """Write a MathML formula as TeX, or keep it as the page's element when there is no TeX for it."""
        is_display = el.get("display") == "block" or el.find_parent(class_="katex-display")
        return _write_math(el, is_display=bool(is_display))

    def convert_mjx_container(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        """Write a MathJax 3 formula from its assistive MathML, the only text it has."""
        math = el.find("math")
        if not isinstance(math, Tag):
            return text
        return _write_math(math, is_display=el.get("display") == "true")

    def convert_script(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        """Write a MathJax 2 source as a formula, and nothing for any other script."""
        script_type = _tex_script_type(el)
        # `_clean_soup` removes every other script, but a tree that is parsed a second time is not cleaned again.
        if script_type is None:
            return ""
        return _write_tex(el.get_text().strip(), is_display=bool(script_type.group(1)))


def _parse(markup: str | bytes, encoding: str | None = None) -> BeautifulSoup:
    """Parse HTML with the standard-library parser."""
    return BeautifulSoup(
        markup, "html.parser", from_encoding=encoding, element_classes={Tag: _Tag}
    )


def _resolve_reference(reference: str, base_url: str) -> str:
    """Resolve one web reference without changing local or non-HTTP references."""
    if not reference or reference.startswith("#"):
        return reference

    parsed = urlsplit(reference)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return reference
    return urljoin(base_url, reference)


def _tex_script_type(script: Tag) -> re.Match[str] | None:
    """Return the match of a MathJax 2 source's type, or None for any other script."""
    script_type = script.get("type")
    return _TEX_SCRIPT_TYPE.fullmatch(script_type) if isinstance(script_type, str) else None


def _mathjax_output_before(script: Tag) -> list[Tag]:
    """Return what MathJax 2 wrote for a source: its preview and its rendered frame, right before the script."""
    written: list[Tag] = []
    sibling = script.find_previous_sibling(True)
    while isinstance(sibling, Tag) and any(
        name.startswith("MathJax") for name in sibling.attrs.get("class", ())
    ):
        written.append(sibling)
        sibling = sibling.find_previous_sibling(True)
    return written


def _write_tex(tex: str, *, is_display: bool) -> str:
    """Write TeX between dollar signs, and a display formula in a paragraph of its own."""
    if not tex:
        return ""
    return f"\n\n$${tex}$$\n\n" if is_display else f"${tex}$"


def _write_math(math: Tag, *, is_display: bool) -> str:
    """Write a `<math>` element as a formula, or as the page's element when it has no TeX."""
    tex = math_to_tex(math)
    return str(math) if tex is None else _write_tex(tex, is_display=is_display)


def _clean_soup(soup: BeautifulSoup, source_url: str | None = None) -> None:
    """Remove elements excluded from generated Markdown, and resolve a remote page's references.

    A source URL makes relative links and images absolute, using HTML base URL rules.
    """
    # One pass over the tags: every find_all call would walk the whole tree again.
    base_url = source_url
    base_found = False
    references: list[tuple[Tag, str, str]] = []
    excluded: list[Tag] = []
    for tag in soup.find_all(True):
        attributes = tag.attrs
        if source_url is not None:
            for attribute in ("href", "src"):
                value = attributes.get(attribute)
                if isinstance(value, str):
                    references.append((tag, attribute, value))
                    if attribute == "href" and tag.name == "base" and not base_found:
                        base_found = True
                        base_url = urljoin(source_url, value)
        classes = attributes.get("class", ())
        if tag.name in _EXCLUDED_TAG_NAMES or not _EXCLUDED_CLASS_NAMES.isdisjoint(classes):
            if tag.name == "script" and _tex_script_type(tag):
                # The source is the formula and convert_script writes it, so what MathJax drew goes.
                excluded.extend(_mathjax_output_before(tag))
            else:
                excluded.append(tag)
        elif classes and not _FORMULA_CLASS_NAMES.isdisjoint(classes) and tag.find("math"):
            # The copy that the library hides from assistive technology shows what its MathML says.
            excluded.extend(
                child
                for child in tag.children
                if isinstance(child, Tag) and child.get("aria-hidden") == "true"
            )
    if base_url is not None:
        for tag, attribute, value in references:
            tag[attribute] = _resolve_reference(value, base_url)
    for tag in excluded:
        tag.decompose()


def _settle(content: Tag) -> bool:
    """Join neighbouring text nodes, and return whether the content's serialized form parses to the same tree.

    0.5.0 rendered every page from its serialized form, so this is what keeps the Markdown the same.
    """
    split: list[NavigableString] = []
    for node in content.descendants:
        if isinstance(node, Tag):
            # Before 4.15, Beautiful Soup can leave a self-closing void element open, with content inside.
            if node.contents and (node.name in _RAW_TEXT_TAG_NAMES or node.can_be_empty_element):
                return False
        elif isinstance(node, PreformattedString):
            # A doctype is written with a line break after it, and a declaration comes back as a comment.
            if not isinstance(node, Comment):
                return False
        elif (
            isinstance(node, NavigableString)
            and isinstance(node.previous_sibling, NavigableString)
            and not isinstance(node.previous_sibling, PreformattedString)
        ):
            # A removed element, or an end tag without a start tag, leaves two text nodes side by side.
            split.append(node)
    for text in split:
        before = text.previous_sibling
        # Always text: it is the neighbour found above, or what the previous round joined.
        if isinstance(before, NavigableString):
            text.extract()
            before.replace_with(NavigableString(before + text))
    return True


def _render_markdown(soup: BeautifulSoup, content: Tag, source: str) -> str:
    """Convert the cleaned content of a tree and prepend its source attribution."""
    if _settle(content):
        if content is not soup:
            content.extract()
            soup.clear()
            soup.append(content)
    else:
        soup = _parse(str(content))
    return f"\n\n<!-- Source: {source} -->\n\n" + md(soup)


def _convert_soup_to_markdown(soup: BeautifulSoup, source: str) -> str:
    """Clean parsed HTML and add its source attribution to Markdown output."""
    _clean_soup(soup)
    main_content = (
        soup.find("main")
        or soup.find("article")
        or soup.find(class_="bd-content")
        or soup.body
        or soup
    )
    # A search by name or class finds tags only.
    return _render_markdown(soup, cast(Tag, main_content), source)


def md(soup: BeautifulSoup) -> str:
    """Render a parsed tree as Markdown."""
    # Keeps the name of the markdownify function it replaced, which the tests swap to make a conversion fail.
    return _Converter(heading_style="atx").convert_soup(soup)


def convert_html_to_markdown(html_path: Path) -> str:
    """Convert a local HTML file to a Markdown string."""
    try:
        soup = _parse(html_path.read_text(encoding="utf-8"))
        return _convert_soup_to_markdown(soup, html_path.name)
    except Exception as error:
        print(f"Error converting {html_path}: {error}", file=sys.stderr)
        return f"\n\n<!-- Error converting {html_path.name} -->\n\n"


def convert_remote_page_to_markdown(page: RemotePage) -> str:
    """Convert a remote page while retaining usable remote references."""
    soup = _parse(page.content, page.encoding)
    _clean_soup(soup, page.source_url)
    return _render_markdown(soup, soup.body or soup, page.source_url)
