from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NodeIR(BaseModel):
    id: str
    kind: Literal["analyst", "project_manager", "join"]
    role_ref: str | None = None


class EdgeIR(BaseModel):
    src: str
    dst: str


class GraphIR(BaseModel):
    nodes: list[NodeIR]
    edges: list[EdgeIR] = Field(default_factory=list)
    entry: str
    terminals: list[str] = Field(default_factory=list)