"""Narrow parsed JSON to the shapes the harness expects, naming what was wrong."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from benchmarks._types import JsonValue


def expect_object(value: JsonValue, where: str) -> Mapping[str, JsonValue]:
    """Return a JSON object, or raise an error that names where it was expected."""
    if not isinstance(value, Mapping):
        raise TypeError(f"{where} must be an object")
    return value


def expect_list(value: JsonValue, where: str) -> Sequence[JsonValue]:
    """Return a JSON array, or raise an error that names where it was expected."""
    if not isinstance(value, list):
        raise TypeError(f"{where} must be a list")
    return value


def expect_string(value: JsonValue, where: str) -> str:
    """Return a JSON string, or raise an error that names where it was expected."""
    if not isinstance(value, str):
        raise TypeError(f"{where} must be a string")
    return value


def expect_number(value: JsonValue, where: str) -> float:
    """Return a JSON number, or raise an error that names where it was expected."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{where} must be a number")
    return float(value)
