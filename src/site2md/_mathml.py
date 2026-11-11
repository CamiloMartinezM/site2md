"""TeX for a `<math>` element: the author's source where the page holds it, else TeX built from the MathML."""

from __future__ import annotations

import re

from bs4 import NavigableString, Tag

_TOKEN_NAMES = frozenset({"mi", "mn", "mo", "mtext"})
# How many children each element takes. `mrow`, `msqrt` and `math` take any number.
_ARITIES = {"msub": 2, "msup": 2, "msubsup": 3, "mfrac": 2, "mroot": 2}
# TeX's own characters, and the invisible operators that MathJax 3 writes after a function name.
_TEX_ESCAPES = str.maketrans(
    {
        "{": r"\{",
        "}": r"\}",
        "#": r"\#",
        "%": r"\%",
        "&": r"\&",
        "_": r"\_",
        "$": r"\$",
        "⁡": None,
        "⁢": None,
        "⁣": None,
        "⁤": None,
    }
)
# These start a TeX command or a space there, and writing them as TeX needs a choice that a rule can't make.
_NO_RULE_CHARACTERS = re.compile(r"[\\^~]")
# MathML trims the text of a token and joins its inner whitespace, and these are the characters it means.
_MATHML_WHITESPACE = re.compile(r"[ \t\r\n]+")


def _token(element: Tag) -> str | None:
    """Return the TeX of an `mi`, `mn`, `mo` or `mtext`, or None when it has no rule."""
    variant = element.get("mathvariant")
    # Only double-struck letters have a rule: any other variant would change how the formula looks.
    if element.find(True) is not None or (
        variant is not None and not (variant == "double-struck" and element.name == "mi")
    ):
        return None
    text = _MATHML_WHITESPACE.sub(" ", element.get_text().strip(" \t\r\n"))
    if _NO_RULE_CHARACTERS.search(text):
        return None
    tex = text.translate(_TEX_ESCAPES)
    if not tex:
        return ""
    if element.name == "mtext":
        return f"\\text{{{tex}}}"
    if variant is not None:
        return f"\\mathbb{{{tex}}}"
    # A name such as `sin` is upright, a single letter is not.
    return f"\\mathrm{{{tex}}}" if element.name == "mi" and len(text) > 1 else tex


def _convert(element: Tag) -> str | None:
    """Return the TeX of a MathML element, or None when it or anything inside it has no rule."""
    if element.name in _TOKEN_NAMES:
        return _token(element)
    children: list[Tag] = []
    for child in element.children:
        if isinstance(child, Tag):
            children.append(child)
        elif isinstance(child, NavigableString) and child.strip():
            return None
    if element.name == "semantics":
        # The first child is the presentation MathML, and the others annotate it.
        return _convert(children[0]) if children else ""
    parts: list[str] = []
    for child_tag in children:
        tex = _convert(child_tag)
        if tex is None:
            return None
        parts.append(tex)
    if element.name in {"math", "mrow"}:
        return "".join(parts)
    if element.name == "msqrt":
        return f"\\sqrt{{{''.join(parts)}}}"
    if _ARITIES.get(element.name) != len(parts):
        return None
    arguments = [f"{{{part}}}" for part in parts]
    if element.name == "mfrac":
        return f"\\frac{arguments[0]}{arguments[1]}"
    if element.name == "mroot":
        return f"\\sqrt[{parts[1]}]{arguments[0]}"
    # A base that is more than one token needs braces, so that the script is not read as belonging to its last one.
    base = parts[0] if children[0].name in _TOKEN_NAMES else arguments[0]
    if element.name == "msub":
        return f"{base}_{arguments[1]}"
    if element.name == "msup":
        return f"{base}^{arguments[1]}"
    return f"{base}_{arguments[1]}^{arguments[2]}"


def math_to_tex(math: Tag) -> str | None:
    """Return the TeX of a `<math>` element, or None when the page has no TeX for it and MathML has no rule."""
    source = math.find("annotation", attrs={"encoding": "application/x-tex"})
    if isinstance(source, Tag) and source.get_text().strip():
        return source.get_text().strip()
    return _convert(math)
