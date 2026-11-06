"""Custom types shared across the benchmark harness."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Literal

JsonValue = None | bool | int | float | str | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
SourceKind = Literal["python", "json", "toml"]
PythonFormatter = Callable[[str], str]
