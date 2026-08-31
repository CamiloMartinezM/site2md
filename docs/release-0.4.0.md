# site2md 0.4.0

Version 0.4.0 adds explicit follow and site modes while preserving page mode as the default. Follow mode selects a one-hop set of same-origin links with CSS selectors. Site mode discovers same-origin pages breadth first under query, robots, pacing, page-count, depth, per-page, and aggregate-content bounds. Expected child failures produce visible warnings and a useful bounded result.

See the [traversal policy](traversal-policy.md) for the complete contract and responsible-use guidance.

This release does not provide persistent cache, resume or checkpoints, concurrency, sitemap discovery, path include/exclude patterns, browser rendering, authentication, automatic retries, stable traversal manifests, or cross-origin child traversal. Publishing to PyPI or another package registry remains a separate maintainer action.
