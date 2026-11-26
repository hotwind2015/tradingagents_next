from __future__ import annotations

from dataclasses import dataclass, field

from tradingagents.models.recipe import Recipe
from tradingagents.providers.registry import available_evidence_types as get_available_evidence_types


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
    
    # Get all evidence types actually provided by registered providers
    provider_provided = get_available_evidence_types()
    
    # provider_chain keys declared in recipe
    declared_in_recipe = set(recipe.data.provider_chain.keys())
    
    # Check for mismatches: declared but not actually provided
    missing_from_providers = declared_in_recipe - provider_provided
    for t in sorted(missing_from_providers):
        result.warnings.append(
            f"Recipe declares evidence type {t!r} in provider_chain, "
            f"but no registered provider actually provides it. "
            f"Available types: {sorted(provider_provided)}"
        )
    
    # Also check for providers that are registered but not used in recipe
    unused_providers = provider_provided - declared_in_recipe
    if unused_providers:
        result.warnings.append(
            f"Registered providers offer these evidence types but they are not used in provider_chain: {sorted(unused_providers)}"
        )
    
    # Also include all role produces as available evidence types
    all_role_produces = set()
    for role in recipe.roles.values():
        all_role_produces.update(role.produces)
    
    # Combined available evidence types
    all_available = provider_provided | all_role_produces

    if available_evidence_types is not None:
        for t in sorted(declared_in_recipe - available_evidence_types):
            result.errors.append(f"no registered provider supplies evidence type: {t!r}")

    produced: set[str] = set()
    
    # 1. 校验分析师团队
    for role_id in recipe.team.analysts:
        if role_id not in recipe.roles:
            result.errors.append(f"Role id '{role_id}' referenced in team.analysts is not defined in roles pool.")
            continue
        role = recipe.roles[role_id]
        for t in role.consumes:
            if t not in all_available:
                result.errors.append(f"role {role_id!r} consumes {t!r} but no provider or upstream role produces it")
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