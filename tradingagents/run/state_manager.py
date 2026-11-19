from __future__ import annotations

from pathlib import Path

from tradingagents.roles.base import RoleOutput


class StateManager:
    def __init__(self, run_dir: Path):
        self.outputs_dir = run_dir / "outputs"
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def save_output(self, role_id: str, output: RoleOutput):
        path = self.outputs_dir / f"{role_id}.json"
        path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    def load_output(self, role_id: str) -> RoleOutput | None:
        path = self.outputs_dir / f"{role_id}.json"
        if path.exists():
            return RoleOutput.model_validate_json(path.read_text(encoding="utf-8"))
        return None