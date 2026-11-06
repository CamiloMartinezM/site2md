"""Custom types shared across the benchmark harness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

JsonValue = None | bool | int | float | str | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
