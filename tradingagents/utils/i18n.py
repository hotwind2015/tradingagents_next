from collections.abc import Mapping
from logging import getLogger
from pathlib import Path
from typing import Any

import yaml

logger = getLogger("tradingagents.i18n")

_LEGACY_KEY_ALIASES = {
    "run_start": "run.started",
    "fetch_evidence": "run.fetching_evidence",
    "fetched_item": "run.fetched_evidence",
    "run_analyst": "run.analyst_started",
    "run_pm": "run.manager_started",
    "run_complete": "run.completed",
    "hallucinated_citations": "run.hallucinated_citations",
    "calling_llm": "run.calling_llm",
    "report_title": "report.title",
}


def _read_catalog(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Translation catalog must contain a mapping: {path}")
    return data


def _merge_catalogs(
    defaults: dict[str, Any], translated: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in translated.items():
        default_value = merged.get(key)
        if isinstance(default_value, dict) and isinstance(value, dict):
            merged[key] = _merge_catalogs(default_value, value)
        else:
            merged[key] = value
    return merged


class I18n:
    def __init__(self, lang: str = "zh-CN", i18n_dir: Path = Path("i18n")):
        self.lang = lang
        defaults = _read_catalog(i18n_dir / "en-US.yaml")
        translated = _read_catalog(i18n_dir / f"{lang}.yaml")
        self.data = _merge_catalogs(defaults, translated)

    def t(self, key: str, **kwargs: Any) -> str:
        key = _LEGACY_KEY_ALIASES.get(key, key)
        value: Any = self.data
        try:
            for segment in key.split("."):
                if not isinstance(value, Mapping) or segment not in value:
                    raise KeyError(segment)
                value = value[segment]
        except KeyError:
            logger.warning("Missing translation key '%s' for locale '%s'", key, self.lang)
            return key

        if not isinstance(value, str):
            raise TypeError(f"Translation key '{key}' for locale '{self.lang}' is not a string")

        try:
            return value.format(**kwargs)
        except (KeyError, ValueError, IndexError) as exc:
            raise ValueError(
                f"Invalid translation template for key '{key}' and locale '{self.lang}': {exc}"
            ) from exc


_current_i18n: I18n | None = None


def set_i18n(lang: str) -> None:
    """Set the current locale for the active run."""
    global _current_i18n
    _current_i18n = I18n(lang=lang)


def get_i18n() -> I18n:
    global _current_i18n
    if _current_i18n is None:
        from tradingagents.config.settings import get_env_settings

        _current_i18n = I18n(lang=get_env_settings().lang)
    return _current_i18n
