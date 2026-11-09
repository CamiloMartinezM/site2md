# site2md 0.4.5

Version 0.4.5 makes `site2md build` and `site2md extract` faster without changing their output, and it raises the cyclopts floor to 4.4.0.

- **Faster extraction.** `extract` worked out each source span's line number by rescanning the document from its start, so its cost grew with the number of spans times the document's length. It now computes the line offsets once per document. On the benchmark's 250-country page, `extract` went from 1.11 s to 0.44 s ([#54](https://github.com/CamiloMartinezM/site2md/issues/54)).
- **Faster start-up.** Each command now imports only the modules it uses. `build` no longer loads the extraction stack, and `extract` and `extractors` no longer load the converter or the remote builder. That saves about 127 ms across `build` and `extract` ([#55](https://github.com/CamiloMartinezM/site2md/issues/55)).
  - This needs cyclopts 4.4.0 or later, because earlier releases still import every registered command, so the declared floor is now `cyclopts>=4.4.0`.
- **Faster conversion.** The converter now finds the elements it removes with BeautifulSoup filters instead of CSS selectors, which makes `build` on the benchmark page about 14% faster ([#56](https://github.com/CamiloMartinezM/site2md/issues/56)). Follow mode's `--follow-selector` still takes CSS selectors.

For the same input, the output is byte-identical to 0.4.4.

The [0.4.0 release notes](release-0.4.0.md) still describe the remote modes and their limits. Publishing to PyPI or another package registry remains a separate maintainer action.
