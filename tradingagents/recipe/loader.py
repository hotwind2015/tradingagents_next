from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from omegaconf import OmegaConf

from tradingagents.models.recipe import Recipe

SUPPORTED_EVIDENCE_SCHEMAS = {"v1"}


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"recipe must be a mapping: {path}")
    return data


def _resolve_with_extends(path: Path, seen: set[Path] | None = None) -> dict[str, Any]:
    seen = seen or set()
    resolved = path.resolve()
    if resolved in seen:
        raise ValueError(f"recipe extends cycle detected: {path}")
    seen.add(resolved)

    raw = _read_yaml(path)
    parent_ref = raw.pop("extends", None)
    if not parent_ref:
        return raw

    parent_path = (path.parent / parent_ref).resolve()
    if not parent_path.exists():
        raise FileNotFoundError(f"parent recipe not found: {parent_path}")

    parent = _resolve_with_extends(parent_path, seen)
    merged = OmegaConf.merge(OmegaConf.create(parent), OmegaConf.create(raw))
    return OmegaConf.to_container(merged, resolve=True)  # type: ignore[return-value]


def load_recipe(path: Path) -> Recipe:
    data = _resolve_with_extends(path)
    recipe = Recipe.model_validate(data)
    if recipe.evidence_schema not in SUPPORTED_EVIDENCE_SCHEMAS:
        raise ValueError(
            f"unsupported evidence_schema {recipe.evidence_schema!r}; "
            f"supported: {sorted(SUPPORTED_EVIDENCE_SCHEMAS)}"
        )
    return recipe