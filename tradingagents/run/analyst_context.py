from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING
from tradingagents.evidence.view import EvidenceView
from tradingagents.models.recipe import Recipe

if TYPE_CHECKING:
    from tradingagents.roles.base import RoleOutput


@dataclass
class AnalystContext:
    """分析师运行时的完整上下文——单一入口，包含一切"""
    
    # === 只读：运行元信息 ===
    run_id: str
    run_dir: Path
    ticker: str
    lang: str
    recipe: Recipe
    
    # === 只读：证据层（含原始数据访问）===
    evidence: EvidenceView
    
    # === 只读：已完成的角色输出（按 DAG 拓扑序）===
    # Key: role_id, Value: RoleOutput
    prior_outputs: dict[str, RoleOutput] = field(default_factory=dict)
    
    # === 只读：全局共享状态（可扩展）===
    # 例：共享计算缓存、外部 API 会话、用户注入的任意对象
    shared_state: dict[str, Any] = field(default_factory=dict)
    
    # === 只读：配置透传（来自 recipe.roles[role_id].args）===
    role_args: dict[str, Any] = field(default_factory=dict)
    
    # === 只读：角色消费的证据类型（来自 recipe.roles[role_id].consumes）===
    consumes: list[str] = field(default_factory=list)
    
    # === 只读：模型配置 ===
    model_tier: str = "quick"  # "quick" | "deep"
    model_config: dict[str, Any] = field(default_factory=dict)
    
    # --- 便捷访问器 ---
    
    def get_prior_output(self, role_id: str) -> RoleOutput | None:
        """获取上游角色输出（按 consumes 依赖自动填充）"""
        return self.prior_outputs.get(role_id)
    
    def get_prior_narrative(self, role_id: str) -> str:
        out = self.get_prior_output(role_id)
        return out.narrative if out else ""
    
    def get_prior_fields(self, role_id: str) -> dict[str, Any]:
        out = self.get_prior_output(role_id)
        return out.fields if out else {}
    
    def get_evidence_raw(self, evidence_id: str) -> dict[str, Any] | None:
        return self.evidence.get_raw(evidence_id)
    
    def get_all_evidence_raw(self, evidence_type: str) -> list[dict[str, Any]]:
        return self.evidence.get_all_raw(evidence_type)
    
    # === 基因链与元数据便捷访问 ===
    
    def get_evidence_metadata(self, evidence_id: str) -> Any | None:
        """获取证据元数据"""
        return self.evidence.get_metadata(evidence_id)
    
    def get_lineage(self, evidence_id: str) -> list[str]:
        """获取基因链：正向溯源（祖先链）"""
        return self.evidence.get_lineage(evidence_id)
    
    def get_descendants(self, evidence_id: str) -> list[str]:
        """获取后代链：反向追踪（所有引用该证据的后代）"""
        return self.evidence.get_descendants(evidence_id)
    
    def get_evidence_by_level(self, evidence_type: str, level: str) -> list:
        """按处理层级筛选证据"""
        return self.evidence.get_by_level(evidence_type, level)
    
    # --- 模板渲染用的扁平化字典 ---
    
    def to_prompt_dict(self, include_raw: bool = False) -> dict[str, Any]:
        """一次性生成模板所需的所有变量"""
        return {
            "ticker": self.ticker,
            "lang": self.lang,
            "run_id": self.run_id,
            "evidence": self.evidence.to_prompt_items(include_raw=include_raw),
            "prior_outputs": {
                rid: {"role": o.role_id, "narrative": o.narrative, "fields": o.fields}
                for rid, o in self.prior_outputs.items()
            },
            "role_args": self.role_args,
            "model_config": self.model_config,
            "shared_state": self.shared_state,  # 慎用，仅供高级模板
        }