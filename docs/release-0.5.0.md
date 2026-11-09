# site2md 0.5.0

Version 0.5.0 adds a standalone executable for Windows and Linux, and two opt-in options that let one process convert a page and extract its records. The Python package stays the normal install, and its defaults don't change.

- **A standalone executable.** Every GitHub release from 0.5.0 on carries `site2md-<version>-windows-x86_64.zip` and `site2md-<version>-linux-x86_64.tar.gz`, with a `SHA256SUMS` file.
  - Each archive unpacks to one folder. Put that folder on `PATH`, as the README's [Installation](../README.md#-installation) section shows.
  - The executable needs neither Python nor pip, and it starts faster than a Python environment.
  - It is a PyInstaller onedir build on Python 3.12. [ADR 0004](adr/0004-ship-a-pyinstaller-onedir-executable-alongside-the-package.md) records why. There is no macOS build, so macOS users keep the package ([#75](https://github.com/CamiloMartinezM/site2md/issues/75), [#76](https://github.com/CamiloMartinezM/site2md/issues/76)).
- **Extractor providers for the executable.** The executable ignores `PYTHONPATH`, and reads `SITE2MD_PROVIDER_PATH` instead.
  - The variable holds folders, separated as in `PATH`, with providers installed by `pip install --target … --no-deps`. The package doesn't read it.
  - Inside the executable, a provider can use only the standard-library modules that the bundle includes, needs compiled code built for Python 3.12 on the same platform, and can't replace a library that the bundle already has.
  - Anyone who hits one of these limits uses the package. The [provider guide](extractor-providers.md#using-a-provider-with-the-executable) has the details.
- **`build --extract`.** `site2md build INPUT --output page.md --extract ID` saves the converted document as before. Then, in the same process, it runs the Extractor on exactly the saved Markdown ([#74](https://github.com/CamiloMartinezM/site2md/issues/74)).
  - The result goes to standard output, and build's own messages to standard error. With `--extract-output PATH`, the result replaces that file atomically instead.
  - `--entry-points-only` and `--values-only` work as they do on `extract`.
  - If the Extractor is missing or fails, the Markdown is kept. The command exits 1 and names the file, so `site2md extract` can be rerun on it.
  - On the benchmark page, one `build --extract … --entry-points-only --values-only` step took 648 ms on Windows, against 887 ms for 0.4.6's three steps.
- **`extract --values-only`.** This writes a JSON array of the record values instead of the extraction result ([#73](https://github.com/CamiloMartinezM/site2md/issues/73)).
  - It drops the provenance, the Extractor, provider and schema identity, the input digest, the source sections, the format version and the diagnostics. Warnings still go to standard error.
  - It is off by default.

The [0.4.0 release notes](release-0.4.0.md) still describe the remote modes and their limits. Publishing to PyPI or another package registry remains a separate maintainer action.
