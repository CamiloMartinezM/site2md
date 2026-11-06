# site2md 0.4.3

Version 0.4.3 makes `site2md build` and `site2md extract` stop before doing any work when the `--output` folder does not exist. A local build that fails to write its output now reports an error instead of success.

- **Missing output folder.** When `--output` named a folder that did not exist, `site2md build` and `site2md extract` found out only when they wrote the result.
  - By then a remote build had already requested and converted its page, and `extract` had already run the Extractor.
  - The error named a hidden temporary file.
  - Both commands now check the folder first and exit 1, before any network request, HTML scan or extraction, with a message that names the missing folder ([#33](https://github.com/CamiloMartinezM/site2md/issues/33)).
- **Failed local build write.** A local `site2md build` that could not write its output printed the error, then `Success!`, and exited 0. It now prints `Error writing output: …` and exits 1 ([#32](https://github.com/CamiloMartinezM/site2md/issues/32)).

The [0.4.0 release notes](release-0.4.0.md) still describe the remote modes and their limits. Publishing to PyPI or another package registry remains a separate maintainer action.
