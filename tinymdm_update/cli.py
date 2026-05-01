from __future__ import annotations

import argparse
import sys

from rich.console import Console

from tinymdm_update.api import CredentialError, client_from_env
from tinymdm_update.commands import cmd_setup, cmd_update
from tinymdm_update.config import ConfigError, load_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update TinyMDM policy apps without fighting the web UI.",
    )
    debug_kwargs = dict(
        action="store_true",
        help="Print raw API response shapes to aid field discovery.",
    )
    parser.add_argument("--debug", **debug_kwargs)
    subparsers = parser.add_subparsers(dest="command")
    setup_p = subparsers.add_parser("setup", help="Configure watched policies and tracked apps.")
    setup_p.add_argument("--debug", **debug_kwargs)
    update_p = subparsers.add_parser("update", help="Update apps across watched policies (default).")
    update_p.add_argument("--debug", **debug_kwargs)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    console = Console()

    try:
        client = client_from_env()
    except CredentialError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        return 1

    try:
        cfg = load_config()
    except ConfigError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        return 1

    if args.command == "setup":
        cmd_setup(client, cfg, console, debug=args.debug)
        return 0
    else:
        return cmd_update(client, cfg, console, debug=args.debug)


if __name__ == "__main__":
    sys.exit(main())
