"""Wiring the service together, and running it.

Everything above this file is testable in isolation; this is where the real
stores, the real connector and the real channel are chosen. Keeping that
choice in one place is what lets the tests build the same service out of
stand-ins without a flag or a mock framework.
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import signal
from dataclasses import dataclass
from typing import Any

from pastie.connector.hon import HonConnector
from pastie.core.commands import start_programme, stop_programme
from pastie.core.ledger import Ledger
from pastie.core.memory import MemoryStore
from pastie.core.tracker import Tracker
from pastie.messengers import MessengerRunner, SpeechCache, build_registry
from pastie.service import paths
from pastie.service.channel import PipeServer
from pastie.service.config import SettingsStore
from pastie.service.protocol import Dispatcher, Reply
from pastie.service.secrets import Credentials, SecretStore, SecretsUnavailableError
from pastie.service.watcher import Watcher

log = logging.getLogger("pastie")


@dataclass
class Service:
    watcher: Watcher
    dispatcher: Dispatcher
    secrets: SecretStore
    settings: SettingsStore


def build(credentials: Credentials) -> Service:
    """Assemble a service from the real stores and a real connection."""
    registry = build_registry(SpeechCache(paths.speech_cache_dir()))
    watcher = Watcher(
        connector=HonConnector(credentials.username, credentials.password),
        tracker=Tracker(MemoryStore(paths.memory_file()), Ledger(paths.ledger_file())),
        messengers=MessengerRunner(registry.messengers),
        settings=SettingsStore(paths.settings_file()),
    )
    service = Service(
        watcher=watcher,
        dispatcher=Dispatcher(),
        secrets=SecretStore(paths.service_dir() / "account.json"),
        settings=SettingsStore(paths.settings_file()),
    )
    register_handlers(service, registry)
    return service


def register_handlers(service: Service, registry: Any) -> None:
    """Everything the app is allowed to ask for.

    Note what is missing: there is no way to read a password back out. One goes
    in, and nothing returns one.
    """
    watcher, settings, secrets = service.watcher, service.settings, service.secrets

    async def status(_arguments: dict[str, Any]) -> Reply:
        return Reply.worked(**watcher.status().to_json())

    async def settings_get(_arguments: dict[str, Any]) -> Reply:
        current = settings.load()
        return Reply.worked(
            settings=current.to_json(),
            account=secrets.exists(),
            messengers=[
                {
                    "name": messenger.name,
                    "label": messenger.label,
                    "settings": [
                        {
                            "key": setting.key,
                            "label": setting.label,
                            "kind": setting.kind.value,
                            "default": setting.default,
                            "choices": list(setting.choices),
                            "help": setting.help,
                        }
                        for setting in messenger.settings()
                    ],
                }
                for messenger in registry
            ],
        )

    async def settings_set(arguments: dict[str, Any]) -> Reply:
        name = str(arguments.get("messenger", ""))
        values = arguments.get("values")
        if not name or not isinstance(values, dict):
            return Reply.failed("a messenger name and its values are both needed")
        settings.update_messenger(name, values)
        return Reply.worked(saved=True)

    async def account_set(arguments: dict[str, Any]) -> Reply:
        username = str(arguments.get("username", "")).strip()
        password = str(arguments.get("password", ""))
        if not username or not password:
            return Reply.failed("an email address and a password are both needed")
        try:
            secrets.save(Credentials(username, password))
        except SecretsUnavailableError as error:
            return Reply.failed(str(error))
        # Deliberately not echoed back, not logged, and not kept in memory here.
        return Reply.worked(saved=True, restart_needed=True)

    async def messenger_test(arguments: dict[str, Any]) -> Reply:
        messenger = registry.get(str(arguments.get("name", "")))
        if messenger is None:
            return Reply.failed("no such messenger")
        result = await messenger.test(settings.load().messenger(messenger.name))
        return Reply.worked(ok=result.ok, detail=result.detail)

    async def messenger_discover(arguments: dict[str, Any]) -> Reply:
        messenger = registry.get(str(arguments.get("name", "")))
        if messenger is None:
            return Reply.failed("no such messenger")
        targets = await messenger.discover(settings.load().messenger(messenger.name))
        return Reply.worked(targets=[vars(target) for target in targets])

    async def command_start(arguments: dict[str, Any]) -> Reply:
        appliance = str(arguments.get("appliance", ""))
        programme = str(arguments.get("programme", ""))
        if not appliance or not programme:
            return Reply.failed("an appliance and a programme are both needed")
        extra = {
            key: arguments[key]
            for key in ("dryLevel", "tempLevel")
            if arguments.get(key) is not None
        }
        progress = await watcher.send(
            appliance,
            start_programme(programme, **extra),
            "startProgram",
            {"program": programme, **extra},
        )
        return Reply.worked(outcome=progress.outcome.value, lines=progress.lines())

    async def command_stop(arguments: dict[str, Any]) -> Reply:
        appliance = str(arguments.get("appliance", ""))
        if not appliance:
            return Reply.failed("an appliance is needed")
        progress = await watcher.send(appliance, stop_programme(), "stopProgram", {})
        return Reply.worked(outcome=progress.outcome.value, lines=progress.lines())

    service.dispatcher.on("status", status)
    service.dispatcher.on("settings.get", settings_get)
    service.dispatcher.on("settings.set", settings_set)
    service.dispatcher.on("account.set", account_set)
    service.dispatcher.on("messenger.test", messenger_test)
    service.dispatcher.on("messenger.discover", messenger_discover)
    service.dispatcher.on("command.start", command_start)
    service.dispatcher.on("command.stop", command_stop)


def configure_logging(verbose: bool = False) -> None:
    """Log to a rotating file, and to the console when somebody is watching.

    Nothing here ever logs a password, a key or a token - see
    `pastie.messengers.base.redact`, which exists so there is no excuse.
    """
    paths.service_dir().mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        paths.log_file(), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(name)s  %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(handler)
    if verbose:
        root.addHandler(logging.StreamHandler())


async def run(service: Service, *, with_channel: bool = True) -> None:
    """Run the watcher, and the app's channel alongside it, until stopped."""
    stop = asyncio.Event()
    _install_signal_handlers(stop)

    jobs = [asyncio.create_task(service.watcher.run(stop), name="watcher")]
    if with_channel:
        jobs.append(asyncio.create_task(PipeServer(service.dispatcher).serve(stop), name="channel"))
    try:
        await asyncio.gather(*jobs)
    finally:
        stop.set()
        for job in jobs:
            job.cancel()


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        signal_number = getattr(signal, name, None)
        if signal_number is None:
            continue
        try:
            loop.add_signal_handler(signal_number, stop.set)
        except (NotImplementedError, RuntimeError, ValueError):
            # Windows supports almost none of this; Ctrl+C still raises
            # KeyboardInterrupt, which the CLI turns into a clean stop.
            signal.signal(signal_number, lambda *_: stop.set())
