from __future__ import annotations

from dataclasses import dataclass, field

from tradingagents.models.recipe import Recipe


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_recipe(
    recipe: Recipe,
    available_evidence_types: set[str] | None = None,
) -> ValidationResult:
    result = ValidationResult()
    provided_by_data = set(recipe.data.required)

    if available_evidence_types is not None:
        for t in sorted(provided_by_data - available_evidence_types):
            result.errors.append(f"no registered provider supplies evidence type: {t!r}")

    produced: set[str] = set()
    
    # 1. 校验分析师团队
    for role_id in recipe.team.analysts:
        if role_id not in recipe.roles:
            result.errors.append(f"Role id '{role_id}' referenced in team.analysts is not defined in roles pool.")
            continue
        role = recipe.roles[role_id]
        for t in role.consumes:
            if t not in provided_by_data:
                result.errors.append(f"role {role_id!r} consumes {t!r} but data.required does not include it")
        produced.update(role.produces)

    # 2. 校验项目经理
    pm_id = recipe.team.project_manager
    if pm_id not in recipe.roles:
        result.errors.append(f"PM id '{pm_id}' referenced in team.project_manager is not defined in roles pool.")
    else:
        pm = recipe.roles[pm_id]
        for t in pm.consumes:
            if t not in produced:
                result.errors.append(f"project_manager requires {t!r} but no analyst produces it")
                
    return result