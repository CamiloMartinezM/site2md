"""Installer integration tests for site2md."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class InstallerTests(unittest.TestCase):
    """Exercise the public installer at its process boundary."""

    def test_installer_does_not_invoke_wget(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as temp_dir:
            shim_dir = Path(temp_dir) / "bin"
            shim_dir.mkdir()
            wget_sentinel = Path(temp_dir) / "wget-invoked"

            shims = {
                "python3": "#!/bin/sh\nprintf 'Python 3.10.0\\n'\n",
                "pip3": "#!/bin/sh\nexit 0\n",
                "wget": (
                    "#!/bin/sh\n"
                    ': > "$WGET_SENTINEL"\n'
                    "printf 'GNU Wget 1.0\\n'\n"
                ),
            }
            for name, contents in shims.items():
                shim = shim_dir / name
                shim.write_text(contents, encoding="utf-8")
                shim.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{shim_dir}:/usr/bin:/bin"
            environment["WGET_SENTINEL"] = str(wget_sentinel)

            result = subprocess.run(
                ["/bin/bash", str(repository_root / "install.sh")],
                cwd=repository_root,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(
                wget_sentinel.exists(),
                f"install.sh invoked wget:\n{result.stdout}\n{result.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
