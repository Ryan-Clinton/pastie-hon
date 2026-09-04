"""The command line: run the service, look at the appliance, set things up.

Useful on its own, and the fastest way to find out whether something works
before involving a window. `pastie status` asks the running service; if there
isn't one, it says so in a sentence rather than a stack trace.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path
from typing import Any

from pastie import __version__
from pastie.app.client import ServiceClient, ServiceUnavailableError
from pastie.service import main as service_main
from pastie.service import migrate, paths
from pastie.service.channel import PipeClient
from pastie.service.config import SettingsStore
from pastie.service.secrets import (
    Credentials,
    SecretStore,
    SecretsUnavailableError,
)


def _client() -> ServiceClient:
    return ServiceClient(PipeClient().ask)


def _secrets() -> SecretStore:
    return SecretStore(paths.service_dir() / "account.json")


def cmd_service(args: argparse.Namespace) -> int:
    """Run the watcher and the app's channel until stopped."""
    service_main.configure_logging(verbose=args.verbose)
    try:
        credentials = _secrets().load()
    except SecretsUnavailableError as error:
        print(f"{error}\n\nRun:  pastie login")
        return 2
    if credentials is None:
        print("No hOn account saved yet.\n\nRun:  pastie login")
        return 2

    service = service_main.build(credentials)
    try:
        asyncio.run(service_main.run(service, with_channel=not args.no_channel))
    except KeyboardInterrupt:
        print("stopped")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    """Save the hOn account, encrypted under this account's own identity."""
    username = args.username or input("hOn email: ").strip()
    password = getpass.getpass("hOn password: ")
    if not username or not password:
        print("Both are needed.")
        return 2
    try:
        _secrets().save(Credentials(username, password))
    except SecretsUnavailableError as error:
        print(str(error))
        return 2
    print(f"Saved to {_secrets().path}, encrypted. Restart the service to pick it up.")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Bring a prototype folder's account and alert settings across."""
    folder = Path(args.folder)
    settings = SettingsStore(paths.settings_file())
    try:
        migration = migrate.apply(folder, _secrets(), settings)
    except SecretsUnavailableError as error:
        print(str(error))
        return 2

    if not migration.anything:
        print(f"Nothing to bring across from {folder}.")
        return 1

    if migration.account:
        print(f"Account {migration.account} saved, encrypted.")
    for name in sorted(migration.messengers):
        print(f"{name} settings brought across.")
    for note in migration.notes:
        print(f"\n  note: {note}")
    if (folder / ".credentials").exists():
        print(
            f"\nYour password is now encrypted. {folder / '.credentials'} still has it in "
            "plain text - delete it when you are happy this works."
        )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Ask the running service what the appliance is doing."""
    try:
        status = _client().status()
    except ServiceUnavailableError as error:
        print(error)
        return 1

    if args.json:
        print(json.dumps(status, indent=2))
        return 0

    print(status.get("health_message", ""))
    for appliance in status.get("appliances", []):
        print()
        name = str(appliance.get("name", "appliance"))
        print(f"{name[:1].upper()}{name[1:]}  ({appliance.get('model', '')})")
        print(f"  state       {appliance.get('state')}")
        if appliance.get("trust") != "verified":
            print("              (unverified appliance type - raw readings only)")
        if appliance.get("programme"):
            print(f"  programme   {appliance['programme']}")
        print(f"  remaining   {appliance.get('remaining')}")
        if appliance.get("remote_allowed") is False:
            print("  remote      not armed - turn the dial to the remote position")
        if appliance.get("fault_code"):
            print(f"  fault       {appliance['fault_code']}")
        for item in appliance.get("maintenance", []):
            if item.get("due"):
                print(f"  due         {item['name']}")

    recent = status.get("recent", [])
    if recent:
        print("\nRecently:")
        for item in recent[:5]:
            print(f"  {item['at'][11:16]}  {item['message']}")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """Fire one messenger, now, so you can see whether it works."""
    try:
        ok, detail = _client().test_messenger(args.messenger)
    except ServiceUnavailableError as error:
        print(error)
        return 1
    print(detail or ("worked" if ok else "failed"))
    return 0 if ok else 1


def cmd_demo(args: argparse.Namespace) -> int:
    """Replay recorded readings through the real code, with no appliance."""
    from pastie import demo

    available = demo.scenarios()
    if args.scenario == "list":
        print("Scenarios:\n")
        for scenario in available.values():
            print(f"  {scenario.key:12} {scenario.title}")
        print("\n  all          run every one of them")
        return 0

    if args.scenario == "all":
        wanted = list(available.values())
    elif args.scenario in available:
        wanted = [available[args.scenario]]
    else:
        print(f"No scenario called {args.scenario!r}. Try:  pastie demo list")
        return 2

    for scenario in wanted:
        demo.run(scenario)
    return 0


def cmd_where(_args: argparse.Namespace) -> int:
    """Print where everything lives, which is the first question when it misbehaves."""
    for label, path in (
        ("settings", paths.settings_file()),
        ("account", paths.service_dir() / "account.json"),
        ("what it knew", paths.memory_file()),
        ("what it announced", paths.ledger_file()),
        ("speech cache", paths.speech_cache_dir()),
        ("log", paths.log_file()),
    ):
        print(f"{label:20} {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pastie",
        description="Pastie - an appliance companion for Haier hOn appliances. Unofficial.",
    )
    parser.add_argument("--version", action="version", version=f"pastie {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("service", help="run the watcher (this is the background half)")
    run.add_argument("-v", "--verbose", action="store_true", help="also log to the console")
    run.add_argument(
        "--no-channel",
        action="store_true",
        help="do not open the app's channel - watch and alert only",
    )
    run.set_defaults(handler=cmd_service)

    login = commands.add_parser("login", help="save the hOn account, encrypted")
    login.add_argument("--username", help="the account's email address")
    login.set_defaults(handler=cmd_login)

    bring = commands.add_parser(
        "migrate", help="bring an old prototype folder's account and settings across"
    )
    bring.add_argument(
        "--folder", default="prototype", help="where the prototype's .credentials lives"
    )
    bring.set_defaults(handler=cmd_migrate)

    status = commands.add_parser("status", help="what the appliance is doing")
    status.add_argument("--json", action="store_true", help="print the reply as JSON")
    status.set_defaults(handler=cmd_status)

    test = commands.add_parser("test", help="fire one messenger now")
    test.add_argument("messenger", help="hue, cast, webhook ...")
    test.set_defaults(handler=cmd_test)

    show = commands.add_parser(
        "demo", help="watch it work on recorded readings - no appliance, no account"
    )
    show.add_argument(
        "scenario",
        nargs="?",
        default="all",
        help="which one to run: a name, 'list', or 'all' (the default)",
    )
    show.set_defaults(handler=cmd_demo)

    where = commands.add_parser("where", help="print where Pastie keeps its files")
    where.set_defaults(handler=cmd_where)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Any = args.handler
    return int(handler(args))


if __name__ == "__main__":  # pragma: no cover - entry point
    sys.exit(main())
