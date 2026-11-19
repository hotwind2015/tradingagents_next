from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tradingagents.models.recipe import Recipe


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    recipe: Recipe
    lang: str = "zh-CN"
    log_level: str = "INFO"