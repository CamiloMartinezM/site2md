"""Download a release archive, check its SHA-256 against the pinned one, and only then unpack it.

Usage: python install_archive.py URL SHA256 DESTINATION

The harness runs this as an `install` command for a tool that is not a Python package.
"""

from __future__ import annotations

import hashlib
import io
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

USER_AGENT = "site2md-benchmark/1 (https://github.com/CamiloMartinezM/site2md)"
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
TIMEOUT_SECONDS = 60


def _download(url: str) -> bytes:
    """Fetch the archive into memory with a timeout and a size limit, so that it is hashed as unpacked."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_ARCHIVE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as error:
        raise SystemExit(f"error: could not download {url}: {error}") from error
    if len(body) > MAX_ARCHIVE_BYTES:
        raise SystemExit(f"error: {url} is larger than {MAX_ARCHIVE_BYTES} bytes")
    return body


def main(arguments: list[str]) -> int:
    """Install the archive that the arguments name, and return the exit status."""
    if len(arguments) != 3:
        raise SystemExit("usage: install_archive.py URL SHA256 DESTINATION")
    url, pinned, destination = arguments
    body = _download(url)
    digest = hashlib.sha256(body).hexdigest()
    if digest != pinned:
        raise SystemExit(
            f"error: {url} has SHA-256 {digest}, but {pinned} is pinned. "
            "Nothing was unpacked: the release may have changed, or the download is corrupt"
        )
    # extractall drops absolute paths and ".." parts, so a member cannot leave the destination.
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        archive.extractall(Path(destination))
    print(f"Checked SHA-256 {digest} and unpacked {url} into {destination}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
