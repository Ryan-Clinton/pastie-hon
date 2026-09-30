# PyInstaller build for the Windows download.
#
#     pyinstaller packaging/pastie.spec --noconfirm
#
# A folder, not a single .exe: a one-file build unpacks itself into a temporary
# directory on every start, which is slow, trips antivirus heuristics, and gives
# the Amazon networking library's native parts a different path each time.
#
# Two executables share one set of files (packaging/entry.py explains why).

from pathlib import Path

import re

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).parent  # noqa: F821 - defined by PyInstaller
ICON = str(ROOT / "assets" / "pastie.ico")

# The version Windows shows in Properties -> Details, and the product name code
# signing checks against. Read from the package, so the two cannot disagree.
VERSION = re.search(
    r'__version__ = "([^"]+)"', (ROOT / "src" / "pastie" / "__init__.py").read_text()
).group(1)
_NUMBERS = tuple(int(part) for part in (VERSION.split(".") + ["0"] * 4)[:4])


def version_info(internal_name, description):
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=_NUMBERS, prodvers=_NUMBERS),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "080904B0",
                        [
                            StringStruct("CompanyName", "Pastie contributors"),
                            StringStruct("FileDescription", description),
                            StringStruct("FileVersion", VERSION),
                            StringStruct("InternalName", internal_name),
                            StringStruct("LegalCopyright", "MIT licence. Unofficial - not affiliated with Haier."),
                            StringStruct("OriginalFilename", f"{internal_name}.exe"),
                            StringStruct("ProductName", "Pastie"),
                            StringStruct("ProductVersion", VERSION),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [0x0809, 1200])]),
        ],
    )


datas = [(str(ROOT / "src" / "pastie" / "app" / "web"), "pastie/app/web")]
datas.append((str(ROOT / "src" / "pastie" / "app" / "pastie.ico"), "pastie/app"))
binaries = []
hiddenimports = []

# Found the hard way on the prototype: these load native code and data files by
# path at run time, which PyInstaller's import scan cannot see.
for package in ("pyhon", "awscrt", "awsiot", "pychromecast", "zeroconf", "gtts", "webview"):
    found = collect_all(package)
    datas += found[0]
    binaries += found[1]
    hiddenimports += found[2]

analysis = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter.test", "pytest", "mypy", "ruff"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)  # noqa: F821


def executable(name, console, description):
    return EXE(  # noqa: F821
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=name,
        console=console,
        icon=ICON,
        upx=False,
        version=version_info(name, description),
    )


window = executable("Pastie", False, "Pastie - what your Haier appliance is doing")
cli = executable("pastie-cli", True, "Pastie command line")

COLLECT(  # noqa: F821
    window,
    cli,
    analysis.binaries,
    analysis.datas,
    name="Pastie",
    upx=False,
)
