from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tradingagents.evidence.store import EvidenceStore
from tradingagents.models.evidence import EvidenceManifest
from tradingagents.utils import I18n
from tradingagents.utils.debug import is_debug


def add_evidence_subparser(subparsers: argparse._SubParsersAction, i18n: I18n) -> None:
    """注册 evidence 子命令组"""
    # 定义 i18n 节点前缀，避免重复拼接
    node = "cli.subcommands.evidence"
    n = lambda k: f"{node}.{k}"

    parser = subparsers.add_parser(
        "evidence",
        help=i18n.t(n("help")),
        description=i18n.t(n("help")),
    )
    sub = parser.add_subparsers(dest="evidence_action", required=True)

    # list
    p_list = sub.add_parser("list", help=i18n.t(n("list_help")))
    p_list.add_argument("--task-id", required=True, help=i18n.t(n("task_id_help")))
    p_list.add_argument("--runs-dir", default="runs", help=i18n.t(n("runs_dir_help")))
    p_list.add_argument("--format", choices=["table", "json"], default="table", help=i18n.t(n("format_help")))

    # show
    p_show = sub.add_parser("show", help=i18n.t(n("show_help")))
    p_show.add_argument("--task-id", required=True, help=i18n.t(n("task_id_help")))
    p_show.add_argument("--evidence-id", required=True, help=i18n.t(n("evidence_id_help")))
    p_show.add_argument("--runs-dir", default="runs", help=i18n.t(n("runs_dir_help")))
    p_show.add_argument("--format", choices=["json", "pretty"], default="pretty", help=i18n.t(n("format_help")))

    # graph
    p_graph = sub.add_parser("graph", help=i18n.t(n("graph_help")))
    p_graph.add_argument("--task-id", required=True, help=i18n.t(n("task_id_help")))
    p_graph.add_argument("--runs-dir", default="runs", help=i18n.t(n("runs_dir_help")))
    p_graph.add_argument("--format", choices=["dot", "json"], default="dot", help=i18n.t(n("format_help")))
    p_graph.add_argument("--output", help=i18n.t(n("output_help")))

    # verify
    p_verify = sub.add_parser("verify", help=i18n.t(n("verify_help")))
    p_verify.add_argument("--task-id", required=True, help=i18n.t(n("task_id_help")))
    p_verify.add_argument("--runs-dir", default="runs", help=i18n.t(n("runs_dir_help")))


def _load_manifest(runs_dir: str, task_id: str):
    """加载指定任务的 manifest"""
    from tradingagents.models.evidence import EvidenceManifest
    manifest_path = Path(runs_dir) / task_id / "evidence_manifest.json"
    if not manifest_path.exists():
        return None
    return EvidenceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    """简单的表格打印"""
    if not rows:
        print("(empty)")
        return
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    # 打印表头
    print(" | ".join(h.ljust(w) for h, w in zip(headers, col_widths)))
    print("-+-".join("-" * w for w in col_widths))
    for row in rows:
        print(" | ".join(str(c).ljust(w) for c, w in zip(row, col_widths)))


def run_evidence_command(args: argparse.Namespace, i18n: I18n) -> int:
    """执行 evidence 子命令"""
    manifest = _load_manifest(args.runs_dir, args.task_id)
    if not manifest:
        print(i18n.t("cli.subcommands.evidence.task_not_found", task_id=args.task_id), file=sys.stderr)
        return 1

    action = args.evidence_action
    n = lambda k: f"cli.subcommands.evidence.{k}"

    if action == "list":
        rows = []
        for item in manifest.items:
            meta = item.metadata
            level = getattr(meta, "processing_level", "unknown")
            lineage_count = len(getattr(meta, "lineage", []))
            rows.append([
                item.evidence_id,
                item.evidence_type,
                item.provider,
                level,
                str(lineage_count),
                item.summary[:50] + ("..." if len(item.summary) > 50 else ""),
            ])
        if args.format == "json":
            print(json.dumps([{
                "evidence_id": item.evidence_id,
                "type": item.evidence_type,
                "provider": item.provider,
                "level": getattr(item.metadata, "processing_level", "unknown"),
                "lineage_count": len(getattr(item.metadata, "lineage", [])),
                "summary": item.summary,
            } for item in manifest.items], ensure_ascii=False, indent=2))
        else:
            _print_table(
                [i18n.t("cli.subcommands.evidence.col_id"), i18n.t("cli.subcommands.evidence.col_type"),
                 i18n.t("cli.subcommands.evidence.col_provider"), i18n.t("cli.subcommands.evidence.col_level"),
                 i18n.t("cli.subcommands.evidence.col_ancestors"), i18n.t("cli.subcommands.evidence.col_summary")],
                rows
            )
        return 0

    elif action == "show":
        item = None
        for it in manifest.items:
            if it.evidence_id == args.evidence_id:
                item = it
                break
        if not item:
            print(i18n.t("cli.subcommands.evidence.not_found", evidence_id=args.evidence_id), file=sys.stderr)
            return 1

        data = {
            "evidence_id": item.evidence_id,
            "type": item.evidence_type,
            "provider": item.provider,
            "method": item.method,
            "params": item.params,
            "summary": item.summary,
            "raw_ref": item.raw_ref,
            "fetched_at": item.fetched_at.isoformat() if item.fetched_at else None,
            "fallback_hit": item.fallback_hit,
            "prev_hash": item.prev_hash,
            "self_hash": item.self_hash,
            "metadata": item.metadata.model_dump() if item.metadata else {},
            "lineage": item.lineage,
        }

        if args.format == "json":
            print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        else:
            # pretty print
            for k, v in data.items():
                if isinstance(v, dict):
                    print(f"{k}:")
                    for k2, v2 in v.items():
                        print(f"  {k2}: {v2}")
                elif isinstance(v, list):
                    print(f"{k}:")
                    for item in v:
                        print(f"  - {item}")
                else:
                    print(f"{k}: {v}")
        return 0

    elif action == "graph":
        # 构建 DOT 格式
        lines = ["digraph evidence_graph {"]
        lines.append('  rankdir=LR;')
        lines.append('  node [shape=box, style=filled, fillcolor=lightblue];')

        # 节点
        for item in manifest.items:
            label = f"{item.evidence_id}\\n{item.evidence_type}\\n{item.provider}"
            lines.append(f'  "{item.evidence_id}" [label="{label}"];')

        # 边
        for item in manifest.items:
            for anc in item.lineage:
                lines.append(f'  "{anc}" -> "{item.evidence_id}";')

        lines.append("}")
        output = "\n".join(lines)

        if args.format == "json":
            # 输出节点和边的 JSON
            nodes = [{"id": it.evidence_id, "type": it.evidence_type, "provider": it.provider} for it in manifest.items]
            edges = [{"from": anc, "to": it.evidence_id} for it in manifest.items for anc in it.lineage]
            print(json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False, indent=2))
        else:
            output_text = "\n".join(lines)
            if args.output:
                Path(args.output).write_text(output_text, encoding="utf-8")
                print(i18n.t("cli.subcommands.evidence.graph_saved", path=args.output))
            else:
                print(output_text)
        return 0

    elif action == "verify":
        # 复用 store 的验证逻辑
        from tradingagents.evidence.store import EvidenceStore
        store = EvidenceStore(Path(args.runs_dir) / args.task_id, args.task_id, "", "")
        store.manifest = manifest
        try:
            ok = store.verify_integrity()
            if ok:
                print(i18n.t("cli.subcommands.evidence.verify_ok", task_id=args.task_id))
            else:
                print(i18n.t("cli.subcommands.evidence.verify_fail", task_id=args.task_id))
            return 0 if ok else 1
        except Exception as e:
            if is_debug():
                import traceback
                traceback.print_exc()
            else:
                print(i18n.t("cli.subcommands.evidence.verify_error", error=e))
            return 1

    return 0