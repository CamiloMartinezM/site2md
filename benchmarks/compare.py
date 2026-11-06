"""Compare a tool's output with the benchmark reference records."""

from __future__ import annotations

import json

from benchmarks._types import JsonValue


def _difference(actual: JsonValue, expected: JsonValue, path: str) -> str | None:
    """Return the first difference between two parsed values, or None when they match."""
    # type() rather than isinstance: 468 must not match 468.0, nor True match 1.
    if type(actual) is not type(expected):
        return (
            f"{path or 'output'}: expected {expected!r} ({type(expected).__name__}), "
            f"got {actual!r} ({type(actual).__name__})"
        )
    if isinstance(actual, dict) and isinstance(expected, dict):
        if actual.keys() != expected.keys():
            return f"{path or 'output'}: expected keys {sorted(expected)}, got {sorted(actual)}"
        for key in expected:
            difference = _difference(actual[key], expected[key], f"{path}.{key}")
            if difference is not None:
                return difference
        return None
    if isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            return f"{path or 'output'}: expected {len(expected)} items, got {len(actual)}"
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            difference = _difference(actual_item, expected_item, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    if actual != expected:
        return f"{path}: expected {expected!r}, got {actual!r}"
    return None


def first_difference(output_text: str, expected: JsonValue) -> str | None:
    """Return the first difference between a tool's JSON output and the reference.

    Both sides are compared after parsing, so whitespace, key order and number
    notation are ignored, while number types and record order are not.
    """
    try:
        actual: JsonValue = json.loads(output_text)
    except json.JSONDecodeError as error:
        return f"output is not valid JSON: {error}"
    return _difference(actual, expected, "")


def set_difference(output_text: str, expected: JsonValue) -> str | None:
    """Return what keeps a tool's JSON output from holding the reference records as a set, if anything.

    Crawlers visit pages in different orders, so order and repeats don't matter. Records are compared
    through their canonical JSON, which keeps number types apart: 468 is not 468.0.
    """
    try:
        actual: JsonValue = json.loads(output_text)
    except json.JSONDecodeError as error:
        return f"output is not valid JSON: {error}"
    if not isinstance(actual, list) or not isinstance(expected, list):
        return "output is not a JSON array"
    actual_records = {json.dumps(record, sort_keys=True) for record in actual}
    expected_records = {json.dumps(record, sort_keys=True) for record in expected}
    parts = []
    if missing := expected_records - actual_records:
        parts.append(f"{len(missing)} missing records, the first {min(missing)}")
    if unexpected := actual_records - expected_records:
        parts.append(f"{len(unexpected)} unexpected records, the first {min(unexpected)}")
    return "; ".join(parts) or None
