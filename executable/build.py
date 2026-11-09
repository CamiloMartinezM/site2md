"""Build the standalone executable: a PyInstaller onedir folder at dist/site2md."""

from __future__ import annotations

from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "build" / "pyinstaller"


def main() -> None:
    """Freeze the site2md installed in this environment with the measured set of flags."""
    PyInstaller.__main__.run(
        [
            str(ROOT / "executable" / "entry.py"),
            "--name",
            "site2md",
            "--onedir",  # onefile would unpack itself at every start
            "--noupx",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(WORK),
            "--specpath",
            str(WORK),
            # Extractor discovery reads the distribution metadata and the data files that it lists.
            "--copy-metadata",
            "site2md",
            "--collect-data",
            "site2md",
            # Both import modules by name at run time: Extractor entry points and the CLI's command paths.
            "--collect-submodules",
            "site2md",
            # marko imports its gfm extension by name, so extraction fails without it.
            "--collect-submodules",
            "marko",
        ]
    )


if __name__ == "__main__":
    main()
