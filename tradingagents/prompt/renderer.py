from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json

from jinja2 import Environment, FileSystemLoader, meta


class TemplateValidationError(ValueError):
    pass


class PromptRenderer:
    def __init__(self, template_dirs: list[Path] | Path):
        if isinstance(template_dirs, Path):
            template_dirs = [template_dirs]
        
        search_paths = [str(d) for d in template_dirs if d.exists()]
        
        self.env = Environment(
            loader=FileSystemLoader(search_paths),
            autoescape=False,
            keep_trailing_newline=True,
        )
        
        # 注入当前日期
        self.env.globals['current_date'] = datetime.now().strftime("%Y-%m-%d")
        self.env.globals['current_datetime'] = datetime.now()
        
        # 注册支持 ensure_ascii 的 tojson filter
        def tojson_filter(value, ensure_ascii=True):
            return json.dumps(value, ensure_ascii=ensure_ascii)
        
        self.env.filters['tojson'] = tojson_filter

    def validate_variables(self, template_name: str, allowed_vars: set[str]) -> None:
        source = self.env.loader.get_source(self.env, template_name)[0]
        ast = self.env.parse(source)
        undeclared = meta.find_undeclared_variables(ast)
        unknown = undeclared - allowed_vars
        if unknown:
            raise TemplateValidationError(
                f"template {template_name!r} references unknown variables: {sorted(unknown)}. "
                f"Allowed: {sorted(allowed_vars)}"
            )

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        # 自动注入语言变量给所有模板
        context["output_language"] = context.get("output_language", "English")
        template = self.env.get_template(template_name)
        return template.render(**context)