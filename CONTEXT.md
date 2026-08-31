# Site conversion

Site conversion turns a local HTML tree or remote web content into one Markdown document.

## Language

**Page mode**:
A remote conversion scope containing only the HTML document returned for the requested URL. It does not follow links found in that document.
_Avoid_: Single-page crawl, mirror

**Follow mode**:
A remote conversion scope containing an entry page and the unique same-origin HTTP(S) pages explicitly selected from its links. Selection is one hop; followed pages do not contribute further targets.
_Avoid_: Detail mode, recursive mode

**Site mode**:
A remote conversion scope containing an entry page and unique same-origin pages discovered from its links through a bounded traversal. Discovered query variants are excluded unless explicitly included.
_Avoid_: Mirror mode, unlimited crawl

**Entry page**:
The remote page requested to begin follow mode or site mode. Its final URL establishes the traversal origin and its source section appears first in the converted document.
_Avoid_: Initial page, root page, seed page

**Traversal origin**:
The scheme, host, and port of the entry page's final URL. Follow mode and site mode do not include child pages outside this boundary.
_Avoid_: Domain, host scope, crawl domain

**Link selector**:
A CSS selection rule that identifies entry-page anchors whose destinations become traversal targets in follow mode.
_Avoid_: Scraper selector, extraction selector

**Traversal target**:
A unique, eligible child URL admitted for processing by follow mode or site mode.
_Avoid_: Crawled link, queued page

**Traversal budget**:
The combined page-count, traversal-depth, and aggregate-content limits that bound one follow-mode or site-mode run.
_Avoid_: Crawl quota, download allowance

**Remote page**:
An HTML document fetched from a URL together with its final source URL, which provides the base for resolving relative links.
_Avoid_: Downloaded file, scraped page

**Converted document**:
The Markdown output of site conversion and the complete source from which structured records are extracted.
_Avoid_: Raw scrape, parsed page

**Extractor**:
A source-specific interpretation that derives structured records from a converted document.
_Avoid_: Parser, scraper

**Source section**:
An ordered portion of a converted document attributed to one source marker.
_Avoid_: Page, file fragment

**Record**:
One structured entity identified in a converted document according to an extractor's record schema.
_Avoid_: Item, parsed object

**Record schema**:
A versioned contract that defines the meaning and shape of records produced by an extractor.
_Avoid_: Output format, universal schema

**Extraction result**:
The structured outcome containing extractor and schema identity, source provenance, records, and diagnostics.
_Avoid_: Parsed output, JSON blob

**Record candidate**:
A document region that an extractor recognizes as representing one record before validating it against the record schema.
_Avoid_: Partial record, match

**Provenance**:
Evidence that links an extraction result and each record to the exact converted-document content and source section from which they were derived.
_Avoid_: Metadata, source name

**Diagnostic**:
A structured explanation of an extraction warning or failure, associated with the relevant document location when available.
_Avoid_: Log message, parser error

**Source marker**:
A standalone Markdown HTML comment that attributes the content following it to a source section.
_Avoid_: Page separator, delimiter

**Source span**:
An exact range of converted-document content within one source section, used to locate provenance and diagnostics.
_Avoid_: Block index, approximate location
