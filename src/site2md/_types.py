"""Custom types shared by site2md's modules."""

from __future__ import annotations

from typing import Any, Literal, Protocol

RemoteMode = Literal["page", "follow", "site"]

RemoteBuildStage = Literal[
    "validation",
    "fetch",
    "conversion",
    "destination",
    "cleanup",
    "interruption",
    "unexpected",
]

TraversalControl = Literal["continue", "stop"]

# A message of the DevTools protocol. The browser defines its shape, not site2md, and it varies by method.
DevToolsMessage = dict[str, Any]


class PositionedMarkoNode(Protocol):
    """Internal typing view of Marko's source-mapped nodes."""

    source_span: tuple[int, int]
