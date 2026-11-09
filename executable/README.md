# The standalone executable

A PyInstaller onedir build of site2md on Python 3.12, for Windows x86_64 and Linux x86_64. ADR 0004 records why. The package stays the default install.

## Build

From the repository root, with [uv](https://docs.astral.sh/uv/) installed:

```shell
uv run --no-project --python 3.12 --with . --with-requirements executable/requirements.txt executable/build.py
```

The command freezes the site2md in the working tree with the PyInstaller version that `requirements.txt` pins, and writes the onedir folder `dist/site2md`. The folder holds `site2md.exe` on Windows or `site2md` on Linux, and an `_internal` folder that must stay beside it. A build takes about 15 seconds. `build/pyinstaller` holds its intermediate files. Both folders are ignored by git.

## Smoke test

```shell
uv run --no-project --python 3.12 --with . --with pip executable/smoke.py dist/site2md
```

The smoke test builds the HTML fixture in `smoke_fixtures/site` and extracts it with the built-in Extractor, with the executable and with the package, and compares the outputs byte for byte. It then installs the provider in `smoke_fixtures/provider` with `pip install --target`, names that folder in `SITE2MD_PROVIDER_PATH`, compares that extraction with the package's, and checks that `site2md extractors` lists both Extractors. It exits with status 1 and one line per problem when anything differs.

## Files

- `entry.py` is the script that PyInstaller freezes. It reads `SITE2MD_PROVIDER_PATH` and then runs the CLI. Only the executable reads the variable.
- `build.py` holds the PyInstaller flags. Each one has a comment that says what breaks without it.
- `smoke.py` and `smoke_fixtures/` are the smoke test and its synthetic fixtures.

CI runs both commands on Windows and on the oldest Ubuntu runner that GitHub offers (`.github/workflows/checks.yml`).
