"""Remote page retrieval for site2md."""

import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

RemoteMode = Literal["page"]


@dataclass(frozen=True)
class RemotePage:
    """An HTML document and the final URL from which it was fetched."""

    content_path: Path
    source_url: str
    encoding: Optional[str]


def fetch_remote(url: str, mode: RemoteMode = "page") -> RemotePage:
    """Fetch remote content using the selected implemented mode."""
    if mode == "page":
        return _fetch_page(url)
    raise ValueError(f"Unsupported remote mode: {mode}")


def _fetch_page(url: str) -> RemotePage:
    """Fetch one HTML document without following links from its content."""
    temp_dir = Path(tempfile.mkdtemp(prefix="site2md_page_"))
    content_path = temp_dir / "page.html"

    try:
        with urllib.request.urlopen(url) as response:
            content_path.write_bytes(response.read())
            return RemotePage(
                content_path=content_path,
                source_url=response.geturl(),
                encoding=response.headers.get_content_charset(),
            )
    except Exception:
        shutil.rmtree(temp_dir)
        raise
