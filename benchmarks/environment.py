"""Create a tool's isolated uv environment, install it at its pinned version and measure the install."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from benchmarks._types import InstallResult
from benchmarks.catalog import Tool
from benchmarks.errors import HarnessError
from benchmarks.paths import CACHE_DIRECTORY

PYTHON_VERSION = "3.12"
HYPERFINE_HINT = (
    "hyperfine is not installed. Install it with `winget install sharkdp.hyperfine` on Windows, "
    "or see https://github.com/sharkdp/hyperfine#installation"
)
UV_HINT = "uv is not installed. See https://docs.astral.sh/uv/getting-started/installation/"


@dataclass(frozen=True)
class Environment:
    """A tool's environment: where it lives, its Python, and the variables its commands run with."""

    directory: Path
    python: Path
    scripts: Path
    python_version: str
    variables: Mapping[str, str]


def _scripts_directory(venv: Path) -> Path:
    """Return the folder of a virtual environment that holds its executables."""
    return venv / ("Scripts" if sys.platform == "win32" else "bin")


def _expand(text: str, values: Mapping[str, str]) -> str:
    """Fill the `{name}` placeholders of a command or variable, naming an unknown one."""
    try:
        return text.format_map(values)
    except KeyError as error:
        raise HarnessError(f"unknown placeholder {error} in '{text}'") from error


def _child_variables() -> dict[str, str]:
    """Return the variables for every child process: all writes land in the cache, none leak in."""
    temporary = CACHE_DIRECTORY / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    variables = {
        name: value
        for name, value in os.environ.items()
        if name.upper() not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    variables.update(
        {
            "UV_CACHE_DIR": str(CACHE_DIRECTORY / "uv"),
            # Copies, so the size on disk is the install's own and never shared with the cache.
            "UV_LINK_MODE": "copy",
            # A missing interpreter must fail rather than download into uv's own folder.
            "UV_PYTHON_DOWNLOADS": "never",
            "PYTHONIOENCODING": "utf-8",
            "TMP": str(temporary),
            "TEMP": str(temporary),
            "TMPDIR": str(temporary),
        }
    )
    return variables


def _measure(directory: Path, venv: Path, python: Path, variables: Mapping[str, str]) -> tuple[str, InstallResult]:
    """Return the Python version, and the size and packages of what the install put in place."""
    completed = subprocess.run(
        [
            str(python),
            "-c",
            "import platform, sysconfig; print(platform.python_version()); print(sysconfig.get_path('purelib'))",
        ],
        env=dict(variables),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    python_version, site_packages = completed.stdout.splitlines()
    packages = {}
    for dist_info in sorted(Path(site_packages).glob("*.dist-info")):
        name, _, version = dist_info.name.removesuffix(".dist-info").rpartition("-")
        packages[name] = version
    # Bytecode that the interpreter writes is left out, as it is not part of what was installed.
    size = sum(
        path.stat().st_size
        for path in Path(site_packages).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    # Anything else an install command unpacked into the environment, such as pandoc's archive.
    size += sum(
        path.stat().st_size
        for path in directory.rglob("*")
        if path.is_file() and venv not in path.parents
    )
    return python_version, {"size_bytes": size, "packages": packages}


def run_command(command: Sequence[str], *, variables: Mapping[str, str], cwd: Path) -> None:
    """Run a command with its output on the console, and stop the harness if it fails."""
    try:
        completed = subprocess.run(command, env=dict(variables), cwd=cwd, check=False)
    except FileNotFoundError as error:
        raise HarnessError(f"cannot run '{command[0]}': {error}") from error
    if completed.returncode != 0:
        raise HarnessError(f"command failed with exit status {completed.returncode}: {' '.join(command)}")


def run_shell_command(command: str, *, variables: Mapping[str, str], cwd: Path) -> None:
    """Run a command line through the platform shell, as hyperfine does, and stop the harness if it fails."""
    # A shell is needed for `&&` and `>`. The line is a tool's own committed steps and the local server's URL.
    completed = subprocess.run(command, shell=True, env=dict(variables), cwd=cwd, check=False)
    if completed.returncode != 0:
        raise HarnessError(
            f"the solution exited with status {completed.returncode}, so it does not count as working: {command}"
        )


def fresh_directory(path: Path) -> Path:
    """Return an empty folder at a path inside the cache, replacing whatever was there."""
    # Validate before deleting: only something below the cache may go.
    if CACHE_DIRECTORY not in path.parents:
        raise HarnessError(f"refusing to replace {path}, which is outside the cache")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def find_program(name: str, hint: str) -> str:
    """Return the path of a program on PATH, or stop with how to install it."""
    path = shutil.which(name)
    if path is None:
        raise HarnessError(hint)
    return path


def install_tool(tool: Tool) -> tuple[Environment, InstallResult]:
    """Create a fresh environment, install the tool, measure the install, then run its setup."""
    uv = find_program("uv", UV_HINT)
    directory = fresh_directory(CACHE_DIRECTORY / "envs" / tool.id)
    venv = directory / "venv"
    python = _scripts_directory(venv) / ("python.exe" if sys.platform == "win32" else "python")
    variables = _child_variables()
    run_command([uv, "venv", "--no-config", "--python", PYTHON_VERSION, str(venv)], variables=variables, cwd=directory)
    values = {
        "python": str(python),
        "environment": str(directory),
        "cache": str(CACHE_DIRECTORY),
        "tool": str(tool.directory),
    }
    if tool.requirements:
        run_command(
            [uv, "pip", "install", "--no-config", "--python", str(python), *tool.requirements],
            variables=variables,
            cwd=directory,
        )
    for command in tool.install:
        run_command([_expand(part, values) for part in command], variables=variables, cwd=directory)
    python_version, install = _measure(directory, venv, python, variables)
    for command in tool.setup:
        run_command([_expand(part, values) for part in command], variables=variables, cwd=directory)
    variables = dict(variables)
    variables["PATH"] = os.pathsep.join(
        [str(_scripts_directory(venv)), *(str(directory / part) for part in tool.path), variables.get("PATH", "")]
    )
    variables.update({name: _expand(value, values) for name, value in (tool.env or {}).items()})
    return Environment(directory, python, _scripts_directory(venv), python_version, variables), install
