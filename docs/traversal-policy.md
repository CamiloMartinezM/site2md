# Traversal policy

`site2md build` has three explicit remote modes. Page mode is the default and fetches only the requested page. Follow mode fetches the entry page and one hop of links selected from that page. Site mode performs a same-origin breadth-first traversal. Build and extract remain separate workflows: traversal produces one converted document, and `site2md extract` can later interpret that document while preserving each source section's provenance.

Only server-returned anchor links are traversal candidates. The tool does not fetch images, scripts, styles, documents, forms, sitemaps, browser-rendered links, or links created by JavaScript. It does not rewrite fetched-page links into internal document anchors.

## Scope and ordering

The **entry page** is the requested remote page. Its final URL establishes the **traversal origin**: the normalized scheme, host, and port that every child must retain before and after redirects. The entry page is always the first source section.

In follow mode, each repeatable `--follow-selector` is a CSS **link selector** that must match anchors directly. Matching anchors form one union in entry-document order. Eligible query-bearing and `rel="nofollow"` anchors are included because the selection is explicit. Followed pages never contribute more targets.

In site mode, anchors are discovered breadth first from the original returned HTML. Links keep document order within each depth. `rel="nofollow"` links and query-bearing links are excluded by default; `--include-query` explicitly admits query-bearing links. An HTML `base` element affects relative-link resolution in both traversal modes. Canonical-link metadata does not change identity or scope.

A **traversal target** is a unique, eligible child URL admitted for processing. URL identity removes fragments, normalizes scheme and host case, removes default ports, and turns an empty path into `/`. Path meaning is preserved. When queries are included, their content and ordering are preserved. A final redirect URL becomes the page's identity and source attribution, so aliases do not create duplicate source sections.

## Budgets and accounting

A **traversal budget** combines page count, traversal depth, and aggregate content. Defaults are:

- 50 admitted pages, including the entry page and failed, disallowed, or redirect-duplicate child targets.
- Depth three in site mode, with the entry page at depth zero. Follow mode is fixed at one hop.
- 25 MiB for each page response in every remote mode.
- 250 MiB of aggregate page-body content in follow and site modes.
- 512 KiB for `robots.txt`, accounted separately from page content.

Every received page-body byte counts toward the aggregate limit, including redirect bodies, partial responses, and content later discarded. Page, depth, and aggregate limits stop the affected discovery successfully. Incomplete child content is discarded, and the command reports the reached limit.

`--max-pages`, `--max-depth`, `--max-page-size-mib`, and `--max-total-size-mib` require positive integers. Page mode rejects traversal-only options. Follow mode requires at least one selector and rejects site-only options. Site mode rejects follow selectors. Local input rejects all remote-only options. Invalid combinations fail before network access.

## Robots policy and pacing

Before requesting children, traversal retrieves `/robots.txt` for the traversal origin with the versioned user agent. A successful policy is enforced. An unavailable `4xx` policy permits traversal; a server error, network failure, or oversized policy stops child traversal because policy is uncertain. The entry page remains a direct user request.

Child requests are sequential. The delay is the greatest of one second, an applicable `crawl-delay`, or the interval implied by an applicable `request-rate`. There is no delay override. Use traversal only where the site's robots policy and terms permit it; policy denial is expected enforcement and must not be bypassed.

## Outcomes and debugging

Expected child retrieval, robots, media-type, size, redirect-boundary, or conversion failures produce concise warnings. Traversal continues within its remaining budgets and writes the successful source sections in deterministic order. The final summary reports fetched, skipped, failed, and reached-limit counts.

Entry-page failure, invalid or empty follow selection, invalid configuration, interruption, unexpected internal failure, and output failure are fatal. Fatal outcomes preserve an existing destination. Successful bounded output replaces the destination atomically.

Temporary traversal data is removed by default after success or failure. `--keep-temp` retains fetched HTML, available partial child responses, converted page fragments, the assembled document, and `index.json`. The JSON index records attempted URLs, available files, statuses, and details for human debugging. It is not a stable manifest and has no compatibility guarantees.
