# site2md 0.4.2

Version 0.4.2 makes `site2md extract` work on Windows, corrects the declared Python and dependency minimums, and keeps long paths and error messages on one line.

- On Windows, every `site2md extract` run exited with status 1 and printed nothing. It now writes its JSON result, and native output from Extractors still stays out of it ([#23](https://github.com/CamiloMartinezM/site2md/issues/23)).
- site2md 0.4.0 and 0.4.1 needed cyclopts 4.1 and therefore Python 3.10, and their converter needed markdownify 1.0 to keep `<br>` lines in one paragraph. The package now declares Python 3.10 or later, `cyclopts>=4.1.0`, and `markdownify>=1.0.0`. On Python 3.9, installation is now refused instead of succeeding and then crashing at import ([#24](https://github.com/CamiloMartinezM/site2md/issues/24), [#28](https://github.com/CamiloMartinezM/site2md/issues/28)).
- When output is captured, `site2md build` keeps the retained-workspace path and remote-build error messages on one line, so the path can be copied in one piece ([#21](https://github.com/CamiloMartinezM/site2md/issues/21)).

The [0.4.0 release notes](release-0.4.0.md) still describe the remote modes and their limits. Publishing to PyPI or another package registry remains a separate maintainer action.
