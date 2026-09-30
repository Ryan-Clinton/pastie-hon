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

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent  # noqa: F821 - defined by PyInstaller
ICON = str(ROOT / "assets" / "pastie.ico")

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


def executable(name, console):
    return EXE(  # noqa: F821
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=name,
        console=console,
        icon=ICON,
        upx=False,
    )


window = executable("Pastie", console=False)
cli = executable("pastie-cli", console=True)

COLLECT(  # noqa: F821
    window,
    cli,
    analysis.binaries,
    analysis.datas,
    name="Pastie",
    upx=False,
)
