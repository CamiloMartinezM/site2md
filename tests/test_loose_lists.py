"""Installed-command tests for lists whose items hold paragraphs."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tests.cli_test_support import InstalledCliTestCase, RecordingServer

PAGE_START = "<html><body><main>\n"
PAGE_END = "</main></body></html>\n"
# A doctype inside the content makes the converter parse the content a second time (ADR 0005).
SECOND_PARSE_MARKER = "<!DOCTYPE html>\n"

LISTS_PAGE = """<p>A loose list:</p>
<ol>
<li><p>First point, in a paragraph of its own.</p>
</li>
<li><p>Second point, in a paragraph of its own.</p>
</li>
</ol>
<p>A tight list:</p>
<ol>
<li>First point.</li>
<li>Second point.</li>
</ol>
<p>An item with two paragraphs:</p>
<ul>
<li><p>Opening paragraph.</p><p>Closing paragraph.</p></li>
<li><p>Next item.</p></li>
</ul>
<p>A loose list with a tight list inside:</p>
<ul>
<li><p>Parent one.</p>
<ul>
<li>Child a.</li>
<li>Child b.</li>
</ul>
</li>
<li><p>Parent two.</p>
</li>
</ul>
<p>After the lists.</p>
"""
LISTS_MARKDOWN = """A loose list:

1. First point, in a paragraph of its own.

2. Second point, in a paragraph of its own.

A tight list:

1. First point.
2. Second point.

An item with two paragraphs:

* Opening paragraph.

  Closing paragraph.

* Next item.

A loose list with a tight list inside:

* Parent one.

  + Child a.
  + Child b.

* Parent two.

After the lists."""

# One paragraph in any item makes the whole list loose, and each list is decided by itself.
DECIDED_PER_LIST_PAGE = """<p>A paragraph in the first item:</p>
<ul>
<li><p>Paragraph first.</p></li>
<li>Plain second.</li>
<li>Plain third.</li>
</ul>
<p>A paragraph in the last item:</p>
<ul>
<li>Plain first.</li>
<li>Plain second.</li>
<li><p>Paragraph last.</p></li>
</ul>
<p>A loose list inside a tight list:</p>
<ul>
<li>Outer one
<ol>
<li><p>Inner a.</p></li>
<li><p>Inner b.</p></li>
</ol>
</li>
<li>Outer two</li>
</ul>
<p>A paragraph that is not a direct child of its item:</p>
<ul>
<li><div><p>Wrapped.</p></div></li>
<li><div><p>Wrapped too.</p></div></li>
</ul>
<p>A loose list with text straight after it:</p>
<ul><li><p>Before text.</p></li><li><p>Last item.</p></li></ul>Text straight after the list.
"""
DECIDED_PER_LIST_MARKDOWN = """A paragraph in the first item:

* Paragraph first.

* Plain second.

* Plain third.

A paragraph in the last item:

* Plain first.

* Plain second.

* Paragraph last.

A loose list inside a tight list:

* Outer one
  1. Inner a.

  2. Inner b.
* Outer two

A paragraph that is not a direct child of its item:

* Wrapped.
* Wrapped too.

A loose list with text straight after it:

* Before text.

* Last item.

Text straight after the list."""

START_PAGE = """<p>A list that starts at 3:</p>
<ol start="3">
<li><p>Third.</p></li>
<li><p>Fourth.</p></li>
</ol>
<p>A tight list that starts at 7:</p>
<ol start="7">
<li>Seventh.</li>
<li>Eighth.</li>
</ol>
<p>A start that is no number:</p>
<ol start="x">
<li><p>One.</p></li>
<li><p>Two.</p></li>
</ol>
"""
START_MARKDOWN = """A list that starts at 3:

3. Third.

4. Fourth.

A tight list that starts at 7:

7. Seventh.
8. Eighth.

A start that is no number:

1. One.

2. Two."""

# No item holds a paragraph, so this page converts to the bytes that 0.6.0 wrote for it.
TIGHT_PAGE = """<p>Tight and nested:</p>
<ul>
<li>Fruit
<ol start="3">
<li>Apple</li>
<li>Pear
<ul><li>Green</li><li>Yellow</li></ul>
</li>
</ol>
</li>
<li>Vegetables</li>
</ul>
<ol start="7"><li>Seventh.</li><li>Eighth.</li></ol>
<p>End.</p>
"""
TIGHT_MARKDOWN = """Tight and nested:

* Fruit
  3. Apple
  4. Pear
     + Green
     + Yellow
* Vegetables

7. Seventh.
8. Eighth.

End."""


class LooseListTests(InstalledCliTestCase):
    """Convert pages that hold lists through the installed command."""

    def build_local(self, page: str) -> str:
        """Build a folder with one page, and return the Markdown that it writes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "pages"
            root.mkdir()
            (root / "index.html").write_text(page, encoding="utf-8")
            output = Path(temp_dir) / "out.md"

            result = self.run_site2md("build", root, "--output", output, "--no-progress")

            self.assertEqual(result.returncode, 0, result.stderr)
            return output.read_text(encoding="utf-8")

    def build_remote(self, page: str) -> tuple[str, str]:
        """Build one remote page, and return its source URL and the Markdown that it writes."""
        routes = {"/page": (200, {"Content-Type": "text/html; charset=utf-8"}, page.encode())}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.run_site2md(
                "build", f"{server.origin}/page", "--output", output, "--no-progress"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            return f"{server.origin}/page", output.read_text(encoding="utf-8")

    def assert_both_builds_write(self, body: str, markdown: str, *, marker: str = "") -> None:
        """Assert that a local and a remote build of the page write exactly this Markdown."""
        page = PAGE_START + marker + body + PAGE_END

        local_markdown = self.build_local(page)
        source, remote_markdown = self.build_remote(page)

        self.assertEqual(local_markdown, f"\n\n<!-- Source: index.html -->\n\n{markdown}\n\n---\n\n")
        self.assertEqual(remote_markdown, f"\n\n<!-- Source: {source} -->\n\n{markdown}\n\n---\n\n")

    def test_local_build_separates_the_items_of_a_list_of_paragraphs(self) -> None:
        markdown = self.build_local(PAGE_START + LISTS_PAGE + PAGE_END)

        self.assertEqual(
            markdown, f"\n\n<!-- Source: index.html -->\n\n{LISTS_MARKDOWN}\n\n---\n\n"
        )

    def test_remote_build_separates_the_items_of_a_list_of_paragraphs(self) -> None:
        source, markdown = self.build_remote(PAGE_START + LISTS_PAGE + PAGE_END)

        self.assertEqual(markdown, f"\n\n<!-- Source: {source} -->\n\n{LISTS_MARKDOWN}\n\n---\n\n")

    def test_both_routes_of_the_converter_separate_the_items_of_a_list_of_paragraphs(self) -> None:
        self.assert_both_builds_write(LISTS_PAGE, LISTS_MARKDOWN, marker=SECOND_PARSE_MARKER)

    def test_a_list_is_loose_when_any_item_holds_a_paragraph_and_decided_by_itself(self) -> None:
        for marker in ("", SECOND_PARSE_MARKER):
            with self.subTest(second_parse=bool(marker)):
                self.assert_both_builds_write(
                    DECIDED_PER_LIST_PAGE, DECIDED_PER_LIST_MARKDOWN, marker=marker
                )

    def test_a_list_with_a_start_attribute_keeps_its_numbers(self) -> None:
        for marker in ("", SECOND_PARSE_MARKER):
            with self.subTest(second_parse=bool(marker)):
                self.assert_both_builds_write(START_PAGE, START_MARKDOWN, marker=marker)

    def test_a_page_without_a_paragraph_in_a_list_item_is_converted_as_before(self) -> None:
        for marker in ("", SECOND_PARSE_MARKER):
            with self.subTest(second_parse=bool(marker)):
                self.assert_both_builds_write(TIGHT_PAGE, TIGHT_MARKDOWN, marker=marker)
