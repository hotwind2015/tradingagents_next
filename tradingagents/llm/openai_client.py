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
    
    def __init__(self):
        settings = get_env_settings()
        if not settings.llm_api_key:
            logger.warning(get_i18n().t("errors.llm_api_key_missing"))
            
        self.client = OpenAI(
            api_key=settings.llm_api_key.get_secret_value() if settings.llm_api_key else "sk-mock",
            base_url=settings.llm_base_url,
        )
        self.default_model = settings.llm_model

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