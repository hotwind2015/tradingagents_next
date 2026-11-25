from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RoleSpec(BaseModel):
    # id 字段可以删了，因为字典的 key 就是 id
    role_id: str
    display_name_key: str
    consumes: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    template: str
    model_tier: Literal["quick", "deep"] = "quick"
    params: dict[str, Any] = Field(default_factory=dict)
    args: dict[str, Any] = Field(default_factory=dict)


class TeamSpec(BaseModel):
    # 这里只放角色在 roles 库里的 ID
    analysts: list[str] = Field(default_factory=list)
    project_manager: str


class DataSpec(BaseModel):
    provider_chain: dict[str, list[str]] = Field(default_factory=dict)
    fallback: list[str] = Field(default_factory=list)
    provider_args: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ModelRouting(BaseModel):
    provider: str = "openai"
    quick: dict[str, Any] = Field(default_factory=dict)
    deep: dict[str, Any] = Field(default_factory=dict)
    provider_args: dict[str, dict[str, Any]] = Field(default_factory=dict)


class Recipe(BaseModel):
    id: str
    version: str
    target_profile: str
    # === 新增：全量角色资源池 ===
    roles: dict[str, RoleSpec] 
    team: TeamSpec
    data: DataSpec
    models: ModelRouting
    evidence_schema: str = "v1"
    prompt_persistence: Literal["full", "digest", "off"] = "full"
    plugin_dirs: list[str] = Field(default_factory=list)