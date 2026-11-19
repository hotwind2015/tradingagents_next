from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PromptPersister:
    def __init__(self, run_dir: Path, strategy: str = "full"):
        self.prompts_dir = run_dir / "prompts"
        self.strategy = strategy
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        role_id: str,
        call_seq: int,
        prompt_text: str,
        meta: dict[str, Any],
    ) -> Path | None:
        if self.strategy == "off":
            return None

        role_dir = self.prompts_dir / role_id
        role_dir.mkdir(parents=True, exist_ok=True)

        meta_file = role_dir / f"{call_seq:03d}.meta.json"
        meta_record = {
            **meta,
            "role_id": role_id,
            "call_seq": call_seq,
            "rendered_at": datetime.now(timezone.utc).isoformat(),
        }
        meta_file.write_text(
            json.dumps(meta_record, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if self.strategy == "digest":
            # digest 模式不存全文，只写哈希占位
            import hashlib
            digest = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
            txt_file = role_dir / f"{call_seq:03d}.digest"
            txt_file.write_text(f"sha256:{digest}", encoding="utf-8")
            return txt_file

        txt_file = role_dir / f"{call_seq:03d}.md"
        txt_file.write_text(prompt_text, encoding="utf-8")
        return txt_file