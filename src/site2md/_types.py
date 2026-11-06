"""Custom types shared by site2md's modules."""

from __future__ import annotations

from typing import Literal, Protocol

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


class PositionedMarkoNode(Protocol):
    """Internal typing view of Marko's source-mapped nodes."""

    source_span: tuple[int, int]
