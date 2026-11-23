from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tradingagents.cli.commands.evidence import add_evidence_subparser, run_evidence_command
from tradingagents.cli.commands.run import add_run_subparser, run_run_command
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


def _build_parser(i18n: I18n) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=i18n.t("cli.description"))
    parser.add_argument("--lang", help=i18n.t("cli.lang_help"))
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        title=i18n.t("cli.commands"),
    )

    # run 子命令
    add_run_subparser(subparsers, i18n)

    # evidence 子命令组
    add_evidence_subparser(subparsers, i18n)

    return parser


def main():
    argv = sys.argv[1:]
    set_i18n(_requested_language(argv))
    i18n = get_i18n()
    parser = _build_parser(i18n)
    args = parser.parse_args(argv)

    if args.command == "run":
        sys.exit(run_run_command(args, i18n))
    elif args.command == "evidence":
        sys.exit(run_evidence_command(args, i18n))


if __name__ == "__main__":
    main()