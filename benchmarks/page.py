"""Download the countries page once, pin its hash, and hand out the cached copy."""

from __future__ import annotations

import datetime
import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from benchmarks._json import expect_object, expect_string
from benchmarks.errors import HarnessError
from benchmarks.files import write_atomically
from benchmarks.paths import CACHE_DIRECTORY, PAGE_PIN

PAGE_URL = "https://www.scrapethissite.com/pages/simple/"
# The local copy is served at the same path, so every tool sees the same relative URLs.
PAGE_PATH = "/pages/simple/"
USER_AGENT = "site2md-benchmark/1 (https://github.com/CamiloMartinezM/site2md)"
MAX_PAGE_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 30
CACHED_PAGE = CACHE_DIRECTORY / "page" / "simple.html"


@dataclass(frozen=True)
class PagePin:
    """The committed identity of the page copy that the reference was built from."""

    url: str
    downloaded: str
    sha256: str


def _download() -> bytes:
    """Fetch the live page once, with a timeout and a size limit."""
    request = urllib.request.Request(PAGE_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_PAGE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as error:
        raise HarnessError(f"could not download {PAGE_URL}: {error}") from error
    if len(body) > MAX_PAGE_BYTES:
        raise HarnessError(f"{PAGE_URL} is larger than {MAX_PAGE_BYTES} bytes")
    return body


def read_pin() -> PagePin:
    """Return the committed pin of the page copy."""
    try:
        data = expect_object(json.loads(PAGE_PIN.read_text(encoding="utf-8")), "page pin")
        return PagePin(
            expect_string(data["url"], "url"),
            expect_string(data["downloaded"], "downloaded"),
            expect_string(data["sha256"], "sha256"),
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HarnessError(
            f"the page copy is not pinned ({error}): run `python -m benchmarks reference` first"
        ) from error


def ensure_page() -> tuple[Path, bool]:
    """Return the cached page copy and whether it was downloaded now, after checking it against the pin."""
    pin = read_pin()
    downloaded = not CACHED_PAGE.is_file()
    if downloaded:
        write_atomically(CACHED_PAGE, _download())
    digest = hashlib.sha256(CACHED_PAGE.read_bytes()).hexdigest()
    if digest != pin.sha256:
        raise HarnessError(
            f"the page copy has SHA-256 {digest}, but {pin.sha256} is pinned: the site may have "
            "changed. Delete benchmarks/.cache/page to download it again, or run "
            "`python -m benchmarks reference` to pin the new copy and rebuild the reference"
        )
    return CACHED_PAGE, downloaded


def refresh_page() -> Path:
    """Download the page again, cache it and pin its date and hash."""
    contents = _download()
    write_atomically(CACHED_PAGE, contents)
    pin = {
        "url": PAGE_URL,
        "downloaded": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "sha256": hashlib.sha256(contents).hexdigest(),
    }
    write_atomically(PAGE_PIN, (json.dumps(pin, indent=2) + "\n").encode("utf-8"))
    return CACHED_PAGE
