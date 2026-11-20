from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tradingagents.run.orchestrator import Orchestrator


def parse_set_args(set_args: list[str]) -> dict:
    """将 ['llm.model=gpt-4o', 'output.lang=en-US'] 转为字典"""
    overrides = {}
    for item in set_args:
        if "=" not in item:
            raise ValueError(f"Invalid --set format: {item}. Must be key=value")
        k, v = item.split("=", 1)
        overrides[k.strip()] = v.strip()
    return overrides


def main():
    parser = argparse.ArgumentParser(description="Config-driven investment analysis")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    run_parser = subparsers.add_parser("run", help="Run an analysis")
    run_parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g., AAPL)")
    run_parser.add_argument("--config", type=Path, help="Path to user config YAML")
    
    # 新增 CLI 覆盖参数
    run_parser.add_argument("--lang", help="Override output language (e.g., en-US, zh-CN)")

    # === 新增：允许命令行指定多个插件目录 ===
    run_parser.add_argument(
        "--plugin-dir", 
        action="append", 
        default=[], 
        help="Add custom plugin directory (can be used multiple times)"
    )
    
    run_parser.add_argument(
        "--set", action="append", default=[], metavar="KEY=VALUE",
        help="Override any config key (e.g., --set llm.model=gpt-4o)"
    )
    run_parser.add_argument("--resume", help="Resume from a previous run_id (e.g., 20261118_061356_ee8a9f)")
    
    args = parser.parse_args()

    if args.command == "run":
        try:
            # 收集 CLI 覆盖项
            cli_overrides = parse_set_args(args.set)
            if args.lang:
                cli_overrides["output.lang"] = args.lang

            cli_plugin_dirs = args.plugin_dir
            
            orchestrator = Orchestrator(
                ticker=args.ticker,
                cli_overrides=cli_overrides,
                config_path=args.config,
                resume_run_id=args.resume,
                cli_plugin_dirs=cli_plugin_dirs  # 传递进去
            )
            report_path = orchestrator.run()
            print(f"\n✅ Success! Report generated at: {report_path}")
        except Exception as e:
            print(f"\n❌ Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()