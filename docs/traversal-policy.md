# Traversal policy

`site2md build` has three explicit remote modes. Page mode is the default and fetches only the requested page. Follow mode fetches the entry page and one hop of links selected from that page. Site mode performs a same-origin breadth-first traversal. Build and extract remain separate workflows: traversal produces one converted document, and `site2md extract` can later interpret that document while preserving each source section's provenance.

Only server-returned anchor links are traversal candidates. The tool does not fetch images, scripts, styles, documents, forms, sitemaps, browser-rendered links, or links created by JavaScript. It does not rewrite fetched-page links into internal document anchors.

The one exception to the first of those sentences is page mode with `--browser`, which reads the page from an installed Chromium-based browser. That browser requests what the page asks for, as any browser does: scripts, style sheets, fonts, images, data calls, the page's icon, and documents in frames, from the page's host and from others. Nothing is blocked, and none of those requests is a traversal target: they are not checked against `robots.txt`, not paced, and not limited to an origin, because they belong to the entry page, which remains a direct user request. With `--wait-for SELECTOR` the browser doesn't fast-forward the page's time: it reads the page as soon as an element matches the CSS selector, and the build fails when none matches within the 30-second timeout. The page asks for the same things either way, and `--wait-for` is rejected without `--browser`. `--browser` is rejected in follow mode, in site mode and for local input, so no link that a script creates is ever traversed.

With `--browser-profile FOLDER`, the browser uses a folder that stays instead of a temporary profile, so that it can carry a person's session to the entry page. That changes whom the entry page's server sees, and nothing else: the requests, the limits and the restriction to page mode stay as they are with `--browser`. site2md has no window of its own for signing in. The person signs in with the same browser, started with `--user-data-dir=FOLDER`, and closes it. The folder can't be the browser's everyday profile, because Chrome refuses remote debugging there, and site2md never copies anything out of it, `--keep-temp` included. A session belongs to an account, so use the option only on sites whose terms allow automated access under that account.

## Scope and ordering

The **entry page** is the requested remote page. Its final URL establishes the **traversal origin**: the normalized scheme, host, and port that every child must retain before and after redirects. The entry page is always the first source section.

In follow mode, each repeatable `--follow-selector` is a CSS **link selector** that must match anchors directly. Matching anchors form one union in entry-document order. Eligible query-bearing and `rel="nofollow"` anchors are included because the selection is explicit. Followed pages never contribute more targets.

In site mode, anchors are discovered breadth first from the original returned HTML. Links keep document order within each depth. `rel="nofollow"` links and query-bearing links are excluded by default; `--include-query` explicitly admits query-bearing links. An HTML `base` element affects relative-link resolution in both traversal modes. Canonical-link metadata does not change identity or scope.

A **traversal target** is a unique, eligible child URL admitted for processing. URL identity removes fragments, normalizes scheme and host case, removes default ports, and turns an empty path into `/`. Path meaning is preserved. When queries are included, their content and ordering are preserved. A final redirect URL becomes the page's identity and source attribution, so aliases do not create duplicate source sections.

## Budgets and accounting

A **traversal budget** combines page count, traversal depth, and aggregate content. Defaults are:

- 50 admitted pages, including the entry page and failed, disallowed, or redirect-duplicate child targets.
- Depth three in site mode, with the entry page at depth zero. Follow mode is fixed at one hop.
- 25 MiB for each page response in every remote mode. With `--browser`, the limit applies to the page as the browser shows it.
- 250 MiB of aggregate page-body content in follow and site modes.
- 512 KiB for `robots.txt`, accounted separately from page content.

Every received page-body byte counts toward the aggregate limit, including redirect bodies, partial responses, and content later discarded. Page, depth, and aggregate limits stop the affected discovery successfully. Incomplete child content is discarded, and the command reports the reached limit.

`--max-pages`, `--max-depth`, `--max-page-size-mib`, and `--max-total-size-mib` require positive integers. Page mode rejects traversal-only options. Follow mode requires at least one selector and rejects site-only options. Site mode rejects follow selectors. `--wait-for` requires `--browser`. Local input rejects all remote-only options. Invalid combinations fail before network access.

## Robots policy and pacing

Before requesting children, traversal retrieves `/robots.txt` for the traversal origin with the versioned user agent. A successful policy is enforced. An unavailable `4xx` policy permits traversal; a server error, network failure, or oversized policy stops child traversal because policy is uncertain. The entry page remains a direct user request, and with `--browser` so do the requests that the browser makes to show it.

Child requests are sequential. The delay is the greatest of one second, an applicable `crawl-delay`, or the interval implied by an applicable `request-rate`. Each delay starts when the previous child response arrives, redirect responses included, so the server never receives two child requests closer together than the delay. There is no delay override. Use traversal only where the site's robots policy and terms permit it; policy denial is expected enforcement and must not be bypassed.

## Intermediate pages

A redirect can end at an **intermediate page**: a sign-in page, a consent page or a browser check that stands in front of the page that was requested. It isn't that page's content, so it is never converted, and site2md doesn't answer it or retry. After redirects, a response is an intermediate page when a parameter of its final URL has a value that, percent-decoded, equals the requested URL, or the requested URL's path with its query: `/login?return_to=%2Farticles%2Fone` follows a request to `/articles/one`. A fragment of the requested URL isn't compared, and a response that wasn't redirected is never one. Every other redirect, same-origin or cross-origin, is as it was: the final URL is the page's identity and source attribution.

An entry page that ends at an intermediate page is an entry-page failure in every remote mode: one line that names the requested URL and the final URL, exit status 1, and an existing destination left as it was. A child that ends at one is an expected child failure: one warning that names both URLs, counted as failed, with nothing converted and no link taken from it, and the traversal goes on. The child was requested, so it counts toward the page budget as any failed child does, its body counts toward the aggregate limit, and its response starts the next request delay. With `--browser` the requested URL is the one that was passed and the final URL is the address that the browser ends on, so a script's move to a sign-in page is refused as a redirect's is.

The rule has two limits, which are not solved here. A sign-in redirect that carries no return address isn't recognised, and its page is converted. A redirect to the real page that also carries the old address as a parameter is refused.

## Outcomes and debugging

Expected child retrieval, robots, media-type, size, redirect-boundary, intermediate-page, or conversion failures produce concise warnings. Traversal continues within its remaining budgets and writes the successful source sections in deterministic order. The final summary reports fetched, skipped, failed, and reached-limit counts.

Entry-page failure, invalid or empty follow selection, invalid configuration, interruption, unexpected internal failure, and output failure are fatal. Fatal outcomes preserve an existing destination. Successful bounded output replaces the destination atomically.

Temporary traversal data is removed by default after success or failure. `--keep-temp` retains fetched HTML, available partial child responses, converted page fragments, the assembled document, and `index.json`. The JSON index records attempted URLs, available files, statuses, and details for human debugging. It is not a stable manifest and has no compatibility guarantees.
