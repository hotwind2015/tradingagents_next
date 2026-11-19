from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, meta


class TemplateValidationError(ValueError):
    pass


class PromptRenderer:
    def __init__(self, template_dirs: list[Path] | Path):
        if isinstance(template_dirs, Path):
            template_dirs = [template_dirs]
        
        # 过滤掉不存在的目录，并把 Path 转换为 str 列表
        search_paths = [str(d) for d in template_dirs if d.exists()]
        
        # Jinja2 会按列表顺序去查找模板，前面的找不到才会找后面的
        self.env = Environment(
            loader=FileSystemLoader(search_paths),
            autoescape=False,
            keep_trailing_newline=True,
        )

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