from pathlib import Path

import yaml


class I18n:
    def __init__(self, lang: str = "zh-CN", i18n_dir: Path = Path("i18n")):
        self.lang = lang
        self.data: dict[str, str] = {}
        
        target_file = i18n_dir / f"{lang}.yaml"
        if target_file.exists():
            self.data.update(yaml.safe_load(target_file.read_text(encoding="utf-8")) or {})
            
        default_file = i18n_dir / "en-US.yaml"
        if default_file.exists():
            defaults = yaml.safe_load(default_file.read_text(encoding="utf-8")) or {}
            for k, v in defaults.items():
                if k not in self.data:
                    self.data[k] = v

    def t(self, key: str, **kwargs) -> str:
        text = self.data.get(key, key)
        try:
            return text.format(**kwargs)
        except KeyError:
            return text

# 全局单例状态
_current_i18n: I18n | None = None

def set_i18n(lang: str) -> None:
    """在 CLI 解析后由编排器调用，全局生效"""
    global _current_i18n
    _current_i18n = I18n(lang=lang)

def get_i18n() -> I18n:
    global _current_i18n
    if _current_i18n is None:
        from tradingagents.config.settings import get_env_settings
        _current_i18n = I18n(lang=get_env_settings().lang)
    return _current_i18n