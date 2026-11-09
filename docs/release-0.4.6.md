# site2md 0.4.6

Version 0.4.6 adds two opt-in fast modes and drops an unneeded fsync. By default, everything behaves as before.

- **`build --no-progress`.** This skips the progress bar, and with it the loading of `rich.progress`, which saves about 20 ms per build. The progress bar stays the default ([#63](https://github.com/CamiloMartinezM/site2md/issues/63)).
- **`extract --entry-points-only`.** This looks up the Extractor only among installed distributions that declare a `site2md.extractors.v1` entry point, and skips reading every other distribution's file list. That saves about 20 ms in a small environment, and about 300 ms in one with numpy, scipy and pandas installed.
  - The trade-off: in this mode `extract` doesn't notice a distribution that ships a provider manifest without an entry point, though `site2md extractors` still reports it. The default lookup keeps the full scan ([#64](https://github.com/CamiloMartinezM/site2md/issues/64)).
- **No fsync on the debug index.** A remote build no longer forces its throwaway debug `index.json` to disk every time it updates it, which saves a few milliseconds per page. The output file is still synced to disk before it replaces the destination ([#62](https://github.com/CamiloMartinezM/site2md/issues/62)).

The [0.4.0 release notes](release-0.4.0.md) still describe the remote modes and their limits. Publishing to PyPI or another package registry remains a separate maintainer action.
