from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRADINGAGENTS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM 三件套
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"

    # 其他系统配置
    runs_dir: Path = Field(default=Path("runs"))
    default_config: Path = Field(default=Path("config/default.yaml"))
    log_level: str = "INFO"
    lang: str = "zh-CN"


@lru_cache(maxsize=1)
def get_env_settings() -> EnvSettings:
    return EnvSettings()


ENV_KEY_MAP: dict[str, str] = {
    "llm_api_key": "llm.api_key",
    "llm_base_url": "llm.base_url",
    "llm_model": "llm.model",
    "runs_dir": "paths.runs",
    "log_level": "logging.level",
    "lang": "output.lang",
}


def explicit_env_overrides() -> dict[str, str]:
    settings = get_env_settings()
    out: dict[str, str] = {}
    for field_name in settings.model_fields_set:
        target = ENV_KEY_MAP.get(field_name)
        if target is None:
            continue
        value = getattr(settings, field_name)
        if value is None:
            continue
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        out[target] = str(value)
    return out