"""Entry script of the standalone executable: add the Extractor provider folders, then run the CLI."""

from __future__ import annotations

import os
import site


def main() -> int:
    """Add the folders in SITE2MD_PROVIDER_PATH after the bundle's own, then run the CLI."""
    for folder in os.environ.get("SITE2MD_PROVIDER_PATH", "").split(os.pathsep):
        # addsitedir("") would add the working directory.
        if folder:
            site.addsitedir(folder)

    # Imported here because Extractor discovery reads sys.path, which the loop above must extend first.
    from site2md.main import main as run_cli

    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
