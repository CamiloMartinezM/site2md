"""The one error type the harness reports to its user as a single line."""

from __future__ import annotations


class HarnessError(Exception):
    """An expected failure, such as a missing program or a changed page copy."""
