# Site conversion

Site conversion turns a local HTML tree or remote web content into one Markdown document.

## Language

**Page mode**:
A remote conversion scope containing only the HTML document returned for the requested URL. It does not follow links found in that document.
_Avoid_: Single-page crawl, mirror

**Follow mode**:
A future remote conversion scope containing an initial page and an explicitly selected set of linked pages.
_Avoid_: Detail mode, recursive mode

**Site mode**:
A future remote conversion scope containing pages discovered through a bounded traversal of a website.
_Avoid_: Mirror mode, unlimited crawl

**Remote page**:
An HTML document fetched from a URL together with its final source URL, which provides the base for resolving relative links.
_Avoid_: Downloaded file, scraped page
