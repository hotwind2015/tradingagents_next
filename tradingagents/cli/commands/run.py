from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tradingagents.config.settings import get_env_settings
from tradingagents.run.orchestrator import Orchestrator
from tradingagents.utils import I18n
from tradingagents.utils.debug import is_debug


def add_run_subparser(subparsers: argparse._SubParsersAction, i18n: I18n) -> None:
    """注册 run 子命令"""

    node = "cli.subcommands.run"
    n = lambda k: f"{node}.{k}"
        
    parser = subparsers.add_parser(
        "run",
        help=i18n.t(n("help")),
        description=i18n.t(n("help")),
    )
    parser.add_argument("--ticker", required=True, help=i18n.t(n("ticker_help")))
    parser.add_argument("--config", type=Path, help=i18n.t(n("config_help")))
    parser.add_argument("--lang", help=i18n.t("cli.lang_help"))
    parser.add_argument(
        "--plugin-dir",
        action="append",
        default=[],
        help=i18n.t("cli.plugin_dir_help"),
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=i18n.t("cli.set_help"),
    )
    parser.add_argument("--resume", help=i18n.t(n("resume_help")))


def parse_set_args(set_args: list[str], i18n: I18n) -> dict[str, str]:
    """将 ['llm.model=gpt-4o', 'output.lang=en-US'] 转为字典"""
    overrides = {}
    for item in set_args:
        if "=" not in item:
            raise ValueError(i18n.t("cli.invalid_set_format", item=item))
        k, v = item.split("=", 1)
        overrides[k.strip()] = v.strip()
    return overrides


def run_run_command(args: argparse.Namespace, i18n: I18n) -> int:
    """执行 run 子命令"""
    try:
        cli_overrides = parse_set_args(args.set, i18n)
        if args.lang:
            cli_overrides["output.lang"] = args.lang

        orchestrator = Orchestrator(
            ticker=args.ticker,
            cli_overrides=cli_overrides,
            config_path=args.config,
            resume_run_id=args.resume,
            cli_plugin_dirs=args.plugin_dir,
        )
        report_path = orchestrator.run()
        print(f"\n{i18n.t('cli.success', report_path=report_path)}")
        return 0
    except Exception as e:
        if is_debug():
            import traceback
            traceback.print_exc()
        else:
            print(f"\n{i18n.t('cli.error', error=e)}", file=sys.stderr)
        return 1