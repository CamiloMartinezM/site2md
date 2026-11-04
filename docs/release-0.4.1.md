# site2md 0.4.1

Version 0.4.1 fixes remote builds on Windows. In 0.4.0, every page-, follow-, and site-mode build on Windows failed with `WinError 183` when site2md rewrote its temporary debugging index, and the same error replaced the real cause of failed fetches. Remote builds now complete on Windows, and failed fetches report their actual cause. Behavior on other platforms is unchanged.

The [0.4.0 release notes](release-0.4.0.md) still describe the remote modes and their limits. See [issue #19](https://github.com/CamiloMartinezM/site2md/issues/19) for the root cause. Publishing to PyPI or another package registry remains a separate maintainer action.
