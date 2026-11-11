"""Installed-command and extraction tests for TeX formulas in page text."""

from __future__ import annotations

import unittest

from tests.formula_test_support import (
    PAGE_END,
    PAGE_START,
    SECOND_PARSE_MARKER,
    PageBuildTestCase,
    read_document,
)

FORMULA_PARAGRAPHS = r"""<p>A vector $x_{i}\in\mathbb{R}^{n}$ and its largest entry $y_{\mathrm{max}} = \max_i y_i$.</p>
<p>Display maths: $$a_1 * b_2 = c_3$$ and also \(x_i * y_i\) and \[s_n = \sum_{k=1}^{n} a_k\]</p>
<p>Sphinx writes <span class="math notranslate nohighlight">\(a_i * b_i\)</span> in a page.</p>
<p>Outside maths, snake_case and 2 * 3 are plain text.</p>
<p>It costs $5 for one and $10 for two_pack items.</p>
"""
FORMULA_MARKDOWN = r"""A vector $x_{i}\in\mathbb{R}^{n}$ and its largest entry $y_{\mathrm{max}} = \max_i y_i$.

Display maths: $$a_1 * b_2 = c_3$$ and also \(x_i * y_i\) and \[s_n = \sum_{k=1}^{n} a_k\]

Sphinx writes \(a_i * b_i\) in a page.

Outside maths, snake\_case and 2 \* 3 are plain text.

It costs $5 for one and $10 for two\_pack items."""

# Each paragraph holds dollar signs or backslashes that are not a formula, so it is escaped as before.
PROSE_PARAGRAPHS = r"""<p>A lone $ sign, then x_1 and $ y_2 are text.</p>
<p>A space before the closing sign $x_1 $ and a digit after it $a_b$1 are text.</p>
<p>An escaped pair \$a_b\$ is text.</p>
<p>Stars *a*, under_score and 2 * 3 are text.</p>
"""
PROSE_MARKDOWN = r"""A lone $ sign, then x\_1 and $ y\_2 are text.

A space before the closing sign $x\_1 $ and a digit after it $a\_b$1 are text.

An escaped pair \$a\_b\$ is text.

Stars \*a\*, under\_score and 2 \* 3 are text."""

# One paragraph with prose and a formula in the same text node.
MIXED_PARAGRAPH = r"""<p>Before snake_case, then $a_1 * b_1$, then 2 * 3 after.</p>
"""
MIXED_MARKDOWN = r"""Before snake\_case, then $a_1 * b_1$, then 2 \* 3 after."""


class FormulaConversionTests(PageBuildTestCase):
    """Convert pages that hold TeX through the installed command."""

    def test_local_build_keeps_the_characters_of_a_formula(self) -> None:
        markdown = self.build_local(PAGE_START + FORMULA_PARAGRAPHS + PAGE_END)

        self.assertEqual(
            markdown,
            f"\n\n<!-- Source: index.html -->\n\n{FORMULA_MARKDOWN}\n\n---\n\n",
        )

    def test_remote_build_keeps_the_characters_of_a_formula(self) -> None:
        source, markdown = self.build_remote(PAGE_START + FORMULA_PARAGRAPHS + PAGE_END)

        self.assertEqual(markdown, f"\n\n<!-- Source: {source} -->\n\n{FORMULA_MARKDOWN}\n\n---\n\n")

    def test_both_routes_of_the_converter_keep_the_characters_of_a_formula(self) -> None:
        page = PAGE_START + SECOND_PARSE_MARKER + FORMULA_PARAGRAPHS + PAGE_END

        local_markdown = self.build_local(page)
        source, remote_markdown = self.build_remote(page)

        self.assertEqual(
            local_markdown,
            f"\n\n<!-- Source: index.html -->\n\n{FORMULA_MARKDOWN}\n\n---\n\n",
        )
        self.assertEqual(
            remote_markdown, f"\n\n<!-- Source: {source} -->\n\n{FORMULA_MARKDOWN}\n\n---\n\n"
        )

    def test_text_that_is_not_a_formula_is_escaped_as_before(self) -> None:
        for marker in ("", SECOND_PARSE_MARKER):
            with self.subTest(second_parse=bool(marker)):
                markdown = self.build_local(PAGE_START + marker + PROSE_PARAGRAPHS + PAGE_END)

                self.assertEqual(
                    markdown, f"\n\n<!-- Source: index.html -->\n\n{PROSE_MARKDOWN}\n\n---\n\n"
                )

    def test_prose_around_a_formula_in_one_text_node_is_escaped_as_before(self) -> None:
        markdown = self.build_local(PAGE_START + MIXED_PARAGRAPH + PAGE_END)

        self.assertEqual(markdown, f"\n\n<!-- Source: index.html -->\n\n{MIXED_MARKDOWN}\n\n---\n\n")


class FormulaExtractionTests(unittest.TestCase):
    """Read Markdown that holds TeX through the extraction operation."""

    def test_extractor_reads_every_character_of_a_formula(self) -> None:
        line = (
            r"Star $a*b*c$, underscore $x_i + y_i$, braces $\{1,2\}$, parentheses \(m_a * m_b\), "
            r"display $$p_1 * p_2$$ and brackets \[q_n * r_n\] end."
        )

        document = read_document(f"# Formulas\n\n{line}\n")

        paragraph = document.sections[0].nodes[1]
        self.assertEqual(document.plain_text(paragraph), line)
        self.assertNotIn("emphasis", [node.kind for node in document.walk(paragraph)])

    def test_formula_is_one_text_node_with_an_exact_span(self) -> None:
        markdown = "# Formulas\n\nOne $a*b*c$ and \\(m_a * m_b\\) end.\n"

        document = read_document(markdown)

        paragraph = document.sections[0].nodes[1]
        formulas = [
            node for node in paragraph.children if node.text in {"$a*b*c$", "\\(m_a * m_b\\)"}
        ]
        self.assertEqual([node.kind for node in formulas], ["text", "text"])
        self.assertEqual(
            [document.source_text(node.span) for node in formulas],
            ["$a*b*c$", "\\(m_a * m_b\\)"],
        )
        self.assertEqual([(node.span.start_line, node.span.end_line) for node in formulas], [(3, 3)] * 2)

    def test_display_formula_over_several_lines_keeps_exact_spans_for_every_line_ending(
        self,
    ) -> None:
        for name, ending in {"lf": "\n", "crlf": "\r\n", "cr": "\r"}.items():
            with self.subTest(line_ending=name):
                markdown = ending.join(
                    ["# Formulas", "", "Before", "$$", "a_1 * b_2", "$$", "after", "", "Last."]
                )

                document = read_document(markdown)

                paragraph = document.sections[0].nodes[1]
                self.assertEqual(document.plain_text(paragraph), "Before\n$$\na_1 * b_2\n$$\nafter")
                self.assertNotIn("emphasis", [node.kind for node in document.walk(paragraph)])
                formula = next(node for node in paragraph.children if node.text.startswith("$$"))
                self.assertEqual(
                    document.source_text(formula.span), ending.join(["$$", "a_1 * b_2", "$$"])
                )
                self.assertEqual((formula.span.start_line, formula.span.end_line), (4, 6))
                last = document.sections[0].nodes[2]
                self.assertEqual((last.span.start_line, last.span.end_line), (9, 9))

    def test_text_that_is_not_a_formula_is_still_read_as_markdown(self) -> None:
        document = read_document(
            "# Prose\n\nIt costs $5 for one and $10 for *two* items, or $x_1 $ and _three_.\n"
        )

        paragraph = document.sections[0].nodes[1]
        emphasis = [node for node in document.walk(paragraph) if node.kind == "emphasis"]
        self.assertEqual([document.plain_text(node) for node in emphasis], ["two", "three"])

    def test_dollar_signs_in_code_stay_code(self) -> None:
        # The dollar sign in the second code span could close a formula that starts in the first.
        document = read_document("# Code\n\nUse `$a*b*c$` and `$HOME` or `$PATH`.\n")

        paragraph = document.sections[0].nodes[1]
        code = [node for node in paragraph.children if node.kind == "code"]
        self.assertEqual([node.text for node in code], ["$a*b*c$", "$HOME", "$PATH"])


if __name__ == "__main__":
    unittest.main()
