from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tradingagents.config.settings import get_env_settings
from tradingagents.run.orchestrator import Orchestrator
from tradingagents.utils import I18n, get_i18n, set_i18n


def _requested_language(argv: list[str]) -> str:
    for index, item in enumerate(argv):
        if item == "--lang" and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith("--lang="):
            return item.partition("=")[2]
    return get_env_settings().lang


def parse_set_args(set_args: list[str]) -> dict[str, str]:
    """将 ['llm.model=gpt-4o', 'output.lang=en-US'] 转为字典"""
    overrides = {}
    for item in set_args:
        if "=" not in item:
            raise ValueError(get_i18n().t("cli.invalid_set_format", item=item))
        k, v = item.split("=", 1)
        overrides[k.strip()] = v.strip()
    return overrides


def _build_parser(i18n: I18n) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=i18n.t("cli.description"))
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        title=i18n.t("cli.commands"),
    )

    run_parser = subparsers.add_parser(
        "run",
        help=i18n.t("cli.run_help"),
        description=i18n.t("cli.run_help"),
    )
    run_parser.add_argument("--ticker", required=True, help=i18n.t("cli.ticker_help"))
    run_parser.add_argument("--config", type=Path, help=i18n.t("cli.config_help"))
    run_parser.add_argument("--lang", help=i18n.t("cli.lang_help"))
    run_parser.add_argument(
        "--plugin-dir",
        action="append",
        default=[],
        help=i18n.t("cli.plugin_dir_help"),
    )
    run_parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=i18n.t("cli.set_help"),
    )
    run_parser.add_argument("--resume", help=i18n.t("cli.resume_help"))
    return parser


def main():
    argv = sys.argv[1:]
    set_i18n(_requested_language(argv))
    parser = _build_parser(get_i18n())
    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            cli_overrides = parse_set_args(args.set)
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
            print(f"\n✅ {get_i18n().t('cli.success', report_path=report_path)}")
        except Exception as e:
            print(f"\n❌ {get_i18n().t('cli.error', error=e)}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()