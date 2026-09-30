"""The packaged build's single entry point.

One program, two faces, because Windows decides at build time whether an .exe
owns a console:

    Pastie.exe               the window (no console)
    Pastie.exe service       the background half, as the window starts it
    pastie-cli.exe <args>    the command line, with a console to print to

Both executables are this script. What differs is the name they were built
under and whether arguments were given.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Everything that loads native code or data files by path - the parts a
#: PyInstaller build silently leaves behind. The Amazon networking library is
#: the one the handover warns about.
_NATIVE = (
    "pyhon",
    "awscrt.mqtt",
    "awsiot.mqtt_connection_builder",
    "pychromecast",
    "zeroconf",
    "gtts",
    "webview",
    "win32crypt",
    "win32pipe",
    "pastie.service.main",
    "pastie.app.main",
)


def self_check() -> int:
    """`pastie-cli --self-check`: prove the build carries what the service needs.

    Run by the release workflow against the packaged folder, because a missing
    native library only shows itself when the service first tries to connect -
    on somebody else's PC.
    """
    import importlib

    failed = 0
    for name in _NATIVE:
        try:
            importlib.import_module(name)
        except Exception as error:  # noqa: BLE001 - every failure is the report
            failed += 1
            print(f"MISSING  {name}: {error}")
        else:
            print(f"ok       {name}")
    web = Path(sys.executable).parent / "_internal" / "pastie" / "app" / "web" / "index.html"
    if not web.exists():
        failed += 1
        print(f"MISSING  the window's page ({web})")
    return 1 if failed else 0


def main() -> int:
    arguments = sys.argv[1:]
    if arguments == ["--self-check"]:
        return self_check()
    console = Path(sys.executable).stem.lower() == "pastie-cli"
    if arguments or console:
        from pastie.cli import main as cli

        return cli(arguments)

    from pastie.app.main import main as window

    return window()


if __name__ == "__main__":
    sys.exit(main())
