from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tradingagents.models.config import EffectiveConfig, ProvenanceField


def flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(flatten(value, path))
        else:
            out[path] = value
    return out


def _load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config file must contain a mapping: {path}")
    return flatten(data)


def load_effective_config(
    *,
    default_config_path: Path,
    user_config_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
    env_overrides: dict[str, Any] | None = None,
    recipe_id: str = "",
    recipe_version: str = "",
    template_versions: dict[str, str] | None = None,
    evidence_schema: str = "v1",
) -> EffectiveConfig:
    layers: list[tuple[str, dict[str, Any]]] = [
        ("default", _load_yaml(default_config_path)),
        ("user_config", _load_yaml(user_config_path)),
        ("env", flatten(env_overrides or {})),
        ("cli", flatten(cli_overrides or {})),
    ]
    merged: dict[str, ProvenanceField] = {}
    for source, layer in layers:
        for key, value in layer.items():
            merged[key] = ProvenanceField(value=value, source=source)  # type: ignore[arg-type]
    return EffectiveConfig(
        fields=merged,
        recipe_id=recipe_id,
        recipe_version=recipe_version,
        template_versions=template_versions or {},
        evidence_schema=evidence_schema,
    )