"""Installed-command tests for formulas that a page holds as rendered output: MathJax, KaTeX and MathML."""

from __future__ import annotations

import unittest

from tests.formula_test_support import (
    PAGE_END,
    PAGE_START,
    SECOND_PARSE_MARKER,
    PageBuildTestCase,
    read_document,
)

# Each paragraph is cut down by hand to the parts that matter from what the library writes.
ISSUE_PARAGRAPHS = """<p>MathJax 3: a vector <mjx-container class="MathJax" jax="CHTML"><mjx-math class="MJX-TEX" aria-hidden="true"><mjx-msub><mjx-mi class="mjx-i"><mjx-c class="mjx-c1D465 TEX-I"></mjx-c></mjx-mi><mjx-script><mjx-mi class="mjx-i"><mjx-c class="mjx-c1D456 TEX-I"></mjx-c></mjx-mi></mjx-script></mjx-msub></mjx-math><mjx-assistive-mml unselectable="on" display="inline"><math xmlns="http://www.w3.org/1998/Math/MathML"><msub><mi>x</mi><mi>i</mi></msub><mo>∈</mo><msup><mi mathvariant="double-struck">R</mi><mi>n</mi></msup></math></mjx-assistive-mml></mjx-container> in the text.</p>
<p>MathML: a half is <math xmlns="http://www.w3.org/1998/Math/MathML"><mfrac><mn>1</mn><mn>2</mn></mfrac></math> and a root is <math xmlns="http://www.w3.org/1998/Math/MathML"><msqrt><mi>x</mi></msqrt></math>.</p>
<p>KaTeX: the entry <span class="katex"><span class="katex-mathml"><math xmlns="http://www.w3.org/1998/Math/MathML"><semantics><mrow><msub><mi>x</mi><mi>i</mi></msub></mrow><annotation encoding="application/x-tex">x_{i}</annotation></semantics></math></span><span class="katex-html" aria-hidden="true"><span class="base"><span class="mord"><span class="mord mathnormal">x</span><span class="msupsub"><span class="vlist-t"><span class="vlist-r"><span class="vlist"><span><span class="sizing reset-size6 size3 mtight"><span class="mord mathnormal mtight">i</span></span></span></span></span></span></span></span></span></span></span> once.</p>
<p>MathJax 2: the entry <span class="MathJax_Preview"></span><span class="MathJax" id="MathJax-Element-1-Frame"><nobr aria-hidden="true"><span class="math"><span class="mrow"><span class="msubsup"><span class="mi">x</span><span class="mi">i</span></span></span></span></nobr><span class="MJX_Assistive_MathML"><math xmlns="http://www.w3.org/1998/Math/MathML"><msub><mi>x</mi><mi>i</mi></msub></math></span></span><script type="math/tex" id="MathJax-Element-1">x_{i}</script> once.</p>
"""
ISSUE_MARKDOWN = r"""MathJax 3: a vector $x_{i}∈\mathbb{R}^{n}$ in the text.

MathML: a half is $\frac{1}{2}$ and a root is $\sqrt{x}$.

KaTeX: the entry $x_{i}$ once.

MathJax 2: the entry $x_{i}$ once."""

# A display formula is written between $$ and $$ in a paragraph of its own.
DISPLAY_PARAGRAPHS = """<p>MathJax 3 display:</p>
<mjx-container class="MathJax" jax="CHTML" display="true"><mjx-math class="MJX-TEX" display="true" aria-hidden="true"><mjx-mi class="mjx-i"><mjx-c class="mjx-c1D44E TEX-I"></mjx-c></mjx-mi></mjx-math><mjx-assistive-mml unselectable="on" display="block"><math xmlns="http://www.w3.org/1998/Math/MathML"><mi>a</mi><mo>=</mo><mfrac><mn>1</mn><mn>2</mn></mfrac></math></mjx-assistive-mml></mjx-container>
<p>MathML display:</p>
<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><msup><mi>x</mi><mn>2</mn></msup></math>
<p>KaTeX display:</p>
<p><span class="katex-display"><span class="katex"><span class="katex-mathml"><math xmlns="http://www.w3.org/1998/Math/MathML"><semantics><mrow><msup><mi>y</mi><mn>2</mn></msup></mrow><annotation encoding="application/x-tex">y^{2} * z_{1}</annotation></semantics></math></span><span class="katex-html" aria-hidden="true"><span class="base"><span class="mord mathnormal">y</span></span></span></span></span></p>
<p>MathJax 2 display:</p>
<span class="MathJax_Preview"></span><div class="MathJax_Display" style="text-align: center;"><span class="MathJax" id="MathJax-Element-2-Frame"><nobr aria-hidden="true"><span class="math"><span class="mi">s</span></span></nobr><span class="MJX_Assistive_MathML"><math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><msub><mi>s</mi><mi>n</mi></msub></math></span></span></div><script type="math/tex; mode=display" id="MathJax-Element-2">
s_n = \\sum_{k=1}^{n} a_k
</script>
<p>After.</p>
"""
DISPLAY_MARKDOWN = r"""MathJax 3 display:

$$a=\frac{1}{2}$$

MathML display:

$$x^{2}$$

KaTeX display:

$$y^{2} * z_{1}$$

MathJax 2 display:

$$s_n = \sum_{k=1}^{n} a_k$$

After."""

# MathML with a rule for every element, so that the page's own TeX isn't needed.
MATHML_PARAGRAPHS = """<p>Roots <math><mroot><mrow><mi>x</mi><mo>+</mo><mn>1</mn></mrow><mn>3</mn></mroot></math> and <math><msqrt><mi>x</mi><mo>+</mo><mn>1</mn></msqrt></math>, scripts <math><msubsup><mi>a</mi><mi>i</mi><mn>2</mn></msubsup></math>, a nest <math><msup><mrow><mi>a</mi><mo>+</mo><mi>b</mi></mrow><mn>2</mn></msup></math>.</p>
<p>A word <math><mi>f</mi><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><mtext>if</mtext><mi>x</mi></math>, a name <math><mi>sin</mi><mo>&#x2061;</mo><mi>x</mi></math>, a set <math><mo>{</mo><mi>a</mi><mo>%</mo><mo>&amp;</mo><mo>_</mo><mo>$</mo><mo>}</mo></math> and a layout with whitespace <math>
  <mrow>
    <mi> y </mi>
    <mo>=</mo>
    <mn>2</mn>
  </mrow>
</math>.</p>
<p>Empty<math></math> and<script type="math/tex"> </script> are left out.</p>
"""
MATHML_MARKDOWN = r"""Roots $\sqrt[3]{x+1}$ and $\sqrt{x+1}$, scripts $a_{i}^{2}$, a nest ${a+b}^{2}$.

A word $f(x)=\text{if}x$, a name $\mathrm{sin}x$, a set $\{a\%\&\_\$\}$ and a layout with whitespace $y=2$.

Empty and are left out."""

# MathML that has no rule is kept as the page wrote it: that loses nothing.
UNKNOWN_PARAGRAPHS = """<p>Kept <math xmlns="http://www.w3.org/1998/Math/MathML"><mover><mi>x</mi><mo>^</mo></mover></math> and <math><mi mathvariant="bold">v</mi></math> and <math><mo>\\</mo></math> and a layout <math><mrow><mi>a</mi>b</mrow></math> and a count <math><msub><mi>x</mi></msub></math> and a token <math><mn>1<mspace></mspace></mn></math> as written, but <math><mi>y</mi></math> is converted.</p>
<p>Container <mjx-container class="MathJax" jax="CHTML"><mjx-math aria-hidden="true"><mjx-mi><mjx-c class="mjx-c1D465"></mjx-c></mjx-mi></mjx-math><mjx-assistive-mml unselectable="on" display="inline"><math xmlns="http://www.w3.org/1998/Math/MathML"><munder><mi>x</mi><mo>_</mo></munder></math></mjx-assistive-mml></mjx-container> too.</p>
"""
UNKNOWN_MARKDOWN = (
    'Kept <math xmlns="http://www.w3.org/1998/Math/MathML"><mover><mi>x</mi><mo>^</mo></mover></math>'
    ' and <math><mi mathvariant="bold">v</mi></math> and <math><mo>\\</mo></math>'
    " and a layout <math><mrow><mi>a</mi>b</mrow></math>"
    " and a count <math><msub><mi>x</mi></msub></math>"
    " and a token <math><mn>1<mspace></mspace></mn></math> as written, but $y$ is converted.\n\n"
    'Container <math xmlns="http://www.w3.org/1998/Math/MathML"><munder><mi>x</mi><mo>_</mo></munder></math> too.'
)

# KaTeX writes the author's TeX in an annotation, which wins over the MathML next to it.
KATEX_PARAGRAPHS = """<p>Over <span class="katex"><span class="katex-mathml"><math xmlns="http://www.w3.org/1998/Math/MathML"><semantics><mrow><mover><mi>x</mi><mo>^</mo></mover></mrow><annotation encoding="application/x-tex">\\hat{x} * 2_k</annotation></semantics></math></span><span class="katex-html" aria-hidden="true"><span class="mord accent">x̂</span></span></span> end.</p>
<p>A bare annotation <math><semantics><mi>z</mi><annotation encoding="application/x-tex">
  z_0 + 1
</annotation></semantics></math> and a different one <math><semantics><mi>w</mi><annotation encoding="application/x-wolfram">w1</annotation></semantics></math>.</p>
<p>HTML only <span class="katex"><span class="katex-html" aria-hidden="true"><span class="mord mathnormal">x</span><span class="mord mathnormal">i</span></span></span> stays the text it has.</p>
"""
KATEX_MARKDOWN = r"""Over $\hat{x} * 2_k$ end.

A bare annotation $z_0 + 1$ and a different one $w$.

HTML only xi stays the text it has."""

# MathJax 2 keeps its sources in scripts, which are the formulas. Every other script is removed.
MATHJAX2_PARAGRAPHS = """<p>Unrendered <script type="math/tex">a_1 * b_2</script> end.</p>
<p><script type="math/tex; mode=display">c_3</script></p>
<script>var snake_case = 1;</script>
<script type="math/mml"><math><mi>z</mi></math></script>
<script type="text/x-mathjax-config">MathJax.Hub.Config({tex2jax: {inlineMath: [['$','$']]}});</script>
<script type="application/json">{"x_i": 1}</script>
<p>Rendered once, source removed <span class="MathJax_Preview"></span><span class="MathJax" id="MathJax-Element-3-Frame"><nobr aria-hidden="true"><span class="math"><span class="mi">x</span><span class="mn">2</span></span></nobr><span class="MJX_Assistive_MathML"><math xmlns="http://www.w3.org/1998/Math/MathML"><msup><mi>x</mi><mn>2</mn></msup></math></span></span> done.</p>
<p>Text before <span class="MathJax_Preview">kept as it is</span> the script<script type="text/javascript">snake_case();</script> after.</p>
"""
MATHJAX2_MARKDOWN = r"""Unrendered $a_1 * b_2$ end.

$$c_3$$

Rendered once, source removed $x^{2}$ done.

Text before kept as it is the script after."""

# Formulas that the page's TeX or the MathML writes must be read back whole by an Extractor.
READ_BACK_PARAGRAPH = """<p>Star <span class="katex"><span class="katex-mathml"><math><semantics><mi>a</mi><annotation encoding="application/x-tex">a*b_{i}*c</annotation></semantics></math></span><span class="katex-html" aria-hidden="true">abc</span></span> and <math><mfrac><mn>1</mn><mn>2</mn></mfrac></math> and <script type="math/tex">x_i * y_i</script> end.</p>
<p><span class="katex-display"><span class="katex"><math><semantics><mi>a</mi><annotation encoding="application/x-tex">p_1 * p_2</annotation></semantics></math></span></span></p>
"""


class RenderedFormulaTests(PageBuildTestCase):
    """Convert pages with rendered formulas through the installed command, down both routes of the converter."""

    def assert_converts(self, paragraphs: str, markdown: str) -> None:
        """Check that a local build, with and without a second parse, writes this Markdown."""
        for marker in ("", SECOND_PARSE_MARKER):
            with self.subTest(second_parse=bool(marker)):
                built = self.build_local(PAGE_START + marker + paragraphs + PAGE_END)

                self.assertEqual(built, f"\n\n<!-- Source: index.html -->\n\n{markdown}\n\n---\n\n")

    def test_every_formula_of_the_issue_is_written_once_with_its_structure(
        self,
    ) -> None:
        self.assert_converts(ISSUE_PARAGRAPHS, ISSUE_MARKDOWN)

    def test_remote_build_writes_the_formulas_the_same_way(self) -> None:
        for marker in ("", SECOND_PARSE_MARKER):
            with self.subTest(second_parse=bool(marker)):
                source, built = self.build_remote(PAGE_START + marker + ISSUE_PARAGRAPHS + PAGE_END)

                self.assertEqual(
                    built,
                    f"\n\n<!-- Source: {source} -->\n\n{ISSUE_MARKDOWN}\n\n---\n\n",
                )

    def test_display_formulas_are_in_a_paragraph_of_their_own(self) -> None:
        self.assert_converts(DISPLAY_PARAGRAPHS, DISPLAY_MARKDOWN)

    def test_mathml_without_tex_becomes_tex(self) -> None:
        self.assert_converts(MATHML_PARAGRAPHS, MATHML_MARKDOWN)

    def test_mathml_without_a_rule_is_kept_as_the_pages_element(self) -> None:
        self.assert_converts(UNKNOWN_PARAGRAPHS, UNKNOWN_MARKDOWN)

    def test_katex_writes_the_tex_of_its_annotation_once(self) -> None:
        self.assert_converts(KATEX_PARAGRAPHS, KATEX_MARKDOWN)

    def test_mathjax_2_writes_the_tex_of_its_script_and_every_other_script_is_removed(
        self,
    ) -> None:
        self.assert_converts(MATHJAX2_PARAGRAPHS, MATHJAX2_MARKDOWN)

    def test_mathjax_3_without_assistive_mathml_stays_absent(self) -> None:
        # The limit that the README names: such a page holds no text for the formula at all.
        paragraph = (
            '<p>Drawn <mjx-container class="MathJax" jax="SVG"><svg width="1ex" height="1ex">'
            '<g><path d="M0 0L1 1"></path></g></svg></mjx-container>here.</p>\n'
        )

        self.assert_converts(paragraph, "Drawn here.")

    def test_an_extractor_reads_a_converted_formula_whole(self) -> None:
        built = self.build_local(PAGE_START + READ_BACK_PARAGRAPH + PAGE_END)
        # The Extractor's test helper wants a first node in the first section, so the source marker goes.
        body = built.removeprefix("\n\n<!-- Source: index.html -->\n\n").removesuffix("\n\n---\n\n")

        document = read_document(f"# Formulas\n\n{body}\n")

        nodes = [node for top in document.sections[0].nodes[1:] for node in document.walk(top)]
        self.assertNotIn("emphasis", [node.kind for node in nodes])
        texts = [node.text for node in nodes if node.kind == "text"]
        for formula in (
            r"$a*b_{i}*c$",
            r"$\frac{1}{2}$",
            r"$x_i * y_i$",
            r"$$p_1 * p_2$$",
        ):
            self.assertEqual(texts.count(formula), 1, formula)


if __name__ == "__main__":
    unittest.main()
