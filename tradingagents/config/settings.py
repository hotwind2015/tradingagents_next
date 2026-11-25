from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import re
from typing import Any, Union

from dotenv import dotenv_values
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "TRADINGAGENTS_"

# 敏感 key 的启发式匹配：snake_case 下命中 api_key / secret / token 等
_SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[_-])("
    r"api[_-]?key|secret|password|passwd|token|"
    r"private[_-]?key|credential|access[_-]?key"
    r")(?:$|[_-])",
    re.IGNORECASE,
)

def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_RE.search(key))

class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
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

    # ---- 新增：动态配置容器 ----
    # .env 里的 TRADINGAGENTS_MY_KEY=key  →  dynamic_env["my_key"] == "key"
    # 类型从 dict[str, str] 改为混合
    dynamic_env: dict[str, Union[str, SecretStr]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _collect_dynamic_env(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        declared = set(cls.model_fields.keys())

        merged: dict[str, str] = {}
        env_file = cls.model_config.get("env_file")
        encoding = cls.model_config.get("env_file_encoding", "utf-8")
        if env_file:
            env_path = Path(env_file)
            if env_path.is_file():
                for k, v in dotenv_values(env_path, encoding=encoding).items():
                    if v is not None:
                        merged[k] = v
        merged.update(os.environ)

        dynamic: dict[str, Union[str, SecretStr]] = {}
        for raw_key, value in merged.items():
            if not raw_key.upper().startswith(ENV_PREFIX):
                continue
            key = raw_key[len(ENV_PREFIX):].lower()
            if not key or key in declared:
                continue
            # 关键：命中敏感词的包 SecretStr，其余保持 str
            dynamic[key] = SecretStr(value) if _is_sensitive_key(key) else value

        # 显式传入的 dynamic_env 也统一处理一遍
        existing = data.get("dynamic_env")
        if isinstance(existing, dict):
            for k, v in existing.items():
                if isinstance(v, SecretStr):
                    dynamic[k] = v
                else:
                    dynamic[k] = SecretStr(str(v)) if _is_sensitive_key(k) else str(v)

        if dynamic:
            data["dynamic_env"] = dynamic
        return data

    def get_extra(self, key: str, default: str | None = None) -> str | None:
        v = self.dynamic_env.get(key)
        if v is None:
            return default
        if isinstance(v, SecretStr):
            return v.get_secret_value()
        return v

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

# 其他程序统一入口，避免到处 get_env_settings().dynamic_env.get(...)
def get_dynamic_env(key: str, default: str | None = None) -> str | None:
    return get_env_settings().dynamic_env.get(key, default)