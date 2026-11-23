from __future__ import annotations

import logging
from typing import Any

from openai import OpenAI

from tradingagents.config.settings import get_env_settings
from tradingagents.llm.base import LLMClient
from tradingagents.utils import get_i18n

logger = logging.getLogger("tradingagents.llm")


class OpenAICompatibleClient(LLMClient):

    llm_id = "openai"
    
    def __init__(self, **kwargs):
        settings = get_env_settings()
        
        # 优先级：kwargs > 环境变量
        api_key = kwargs.get("api_key") or (settings.llm_api_key.get_secret_value() if settings.llm_api_key else None)
        base_url = kwargs.get("base_url") or settings.llm_base_url
        organization = kwargs.get("organization")
        
        if not api_key:
            error_msg = get_i18n().t("errors.llm_api_key_missing")
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        client_kwargs = {"api_key": api_key, "base_url": base_url}
        if organization:
            client_kwargs["organization"] = organization
            
        self.client = OpenAI(**client_kwargs)
        self.default_model = kwargs.get("model") or settings.llm_model

    def invoke(self, prompt: str, model_config: dict[str, Any]) -> str:
        # 优先级：配方模型配置 > 环境变量(TRADINGAGENTS_LLM_MODEL) > 代码默认值
        model_name = model_config.get("model") or self.default_model

        i18n = get_i18n()
        
        logger.info(i18n.t("run.calling_llm", model_name=model_name))
        
        response = self.client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=model_config.get("temperature", 0.2),
        )
        return response.choices[0].message.content or ""