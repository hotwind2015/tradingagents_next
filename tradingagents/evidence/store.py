from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradingagents.models.evidence import EvidenceItem, EvidenceManifest, sha256_payload


class IntegrityError(Exception):
    pass


class EvidenceStore:
    def __init__(self, run_dir: Path, run_id: str, recipe_id: str, recipe_version: str):
        self.run_dir = run_dir
        self.manifest_path = run_dir / "evidence_manifest.json"
        self.chain_path = run_dir / "integrity.chain"
        self.manifest = EvidenceManifest(
            run_id=run_id, recipe_id=recipe_id, recipe_version=recipe_version
        )
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._raw_dir = run_dir / "raw"
        self._raw_dir.mkdir(exist_ok=True)

    def append(self, item: EvidenceItem, raw_payload: dict[str, Any] | None = None) -> None:
        if item.self_hash:
            raise ValueError("item is already sealed")
        
        prev_hash = self.manifest.last_hash()
        item.seal(prev_hash)

        if raw_payload is not None:
            # _meta 直接用 EvidenceItem 的完整元数据（model_dump）
            # raw_payload 作为主载荷，_meta 作为完整证据元数据
            save_payload = {
                **(item.model_dump(mode="json", exclude={"self_hash", "prev_hash"})),
                "raw_payload":raw_payload,
            }
            
            raw_path = self._raw_dir / f"{item.evidence_id}.json"
            raw_path.write_text(
                json.dumps(save_payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            # 将 raw 文件的哈希加入 integrity chain 的覆盖范围
            self._append_chain_record("raw_file", raw_path.name, sha256_payload(raw_payload))

        self.manifest.items.append(item)
        self._flush_manifest()
        self._append_chain_record("evidence", item.evidence_id, item.self_hash)

    def _flush_manifest(self) -> None:
        self.manifest_path.write_text(
            self.manifest.model_dump_json(indent=2), encoding="utf-8"
        )

    def _append_chain_record(self, kind: str, ref: str, self_hash: str) -> None:
        # 获取当前链尾
        prev_hash = ""
        if self.chain_path.exists():
            lines = self.chain_path.read_text(encoding="utf-8").strip().splitlines()
            # 从后向前找第一个有效的 JSON 行
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    prev_hash = json.loads(line)["self_hash"]
                    break
                except json.JSONDecodeError:
                    # 跳过损坏的行
                    continue

        record = {"kind": kind, "ref": ref, "prev_hash": prev_hash, "self_hash": self_hash}
        with self.chain_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def verify_integrity(self) -> bool:
        if not self.chain_path.exists():
            return True
        lines = self.chain_path.read_text(encoding="utf-8").strip().splitlines()
        prev = ""
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise IntegrityError(f"invalid JSON at line {line_num}: {e}")
            if rec["prev_hash"] != prev:
                raise IntegrityError(f"hash chain broken at {rec['ref']}")
            prev = rec["self_hash"]
        return True