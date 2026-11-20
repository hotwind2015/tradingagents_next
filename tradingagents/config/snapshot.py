from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tradingagents.models.config import EffectiveConfig

REDACT_MARKERS = ("api_key", "apikey", "secret", "token", "password")

def _is_sensitive(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in REDACT_MARKERS)

# === 新增 recipe_data 参数 ===
def write_snapshot(config: EffectiveConfig, path: Path, recipe_data: dict[str, Any] | None = None) -> list[str]:
    redacted: list[str] = []
    fields_out: dict[str, dict[str, Any]] = {}
    for key, field in sorted(config.fields.items()):
        value = field.value
        if _is_sensitive(key) and value not in (None, ""):
            value = "***REDACTED***"
            redacted.append(key)
        fields_out[key] = {"value": value, "source": field.source}

    payload = {
        "recipe": {"id": config.recipe_id, "version": config.recipe_version},
        "evidence_schema": config.evidence_schema,
        "template_versions": config.template_versions,
        "fields": fields_out,
    }
    
    # === 将配方内容合并进快照 ===
    # if recipe_data:
    #     payload["recipe_details"] = recipe_data
    
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    config.redacted_keys = redacted
    return redacted