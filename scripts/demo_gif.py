"""Render `pastie demo` as the animated terminal GIF at the top of the README.

    python scripts/demo_gif.py            (writes assets/demo.gif)

The frames are the real output of the real demo, captured when this runs - not
typed out by hand - so the picture cannot say anything the code does not. Run
it again whenever the demo's wording changes.

Needs Pillow and a monospaced font: Consolas on Windows, DejaVu Sans Mono
elsewhere.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "demo.gif"
SCENARIOS = ("cycle", "gap", "ignored")

WIDTH, HEIGHT = 980, 520
MARGIN, LINE = 18, 20
BACKGROUND = (24, 24, 27)
TEXT = (212, 212, 216)
DIM = (140, 140, 150)
PROMPT = (134, 239, 172)
LOUD = (253, 186, 116)

#: Milliseconds. Slow enough to read, quick enough that a visitor sees all three.
PER_LINE, HOLD = 110, 2600


def font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), 15)
    return ImageFont.load_default()


def demo(scenario: str) -> list[str]:
    completed = subprocess.run(
        [sys.executable, "-m", "pastie.cli", "demo", scenario],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    return [f"$ pastie demo {scenario}", *completed.stdout.rstrip().splitlines()]


def colour(line: str) -> tuple[int, int, int]:
    if line.startswith("$"):
        return PROMPT
    if "ANNOUNCE" in line:
        return LOUD
    if line.strip().startswith("(") or line.strip().startswith("---"):
        return DIM
    return TEXT


def frame(lines: list[str], face: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    visible = (HEIGHT - 2 * MARGIN) // LINE
    for row, line in enumerate(lines[-visible:]):
        draw.text((MARGIN, MARGIN + row * LINE), line, fill=colour(line), font=face)
    return image


def main() -> int:
    face = font()
    frames: list[Image.Image] = []
    durations: list[int] = []
    for scenario in SCENARIOS:
        lines = demo(scenario)
        for shown in range(1, len(lines) + 1):
            frames.append(frame(lines[:shown], face))
            durations.append(PER_LINE)
        durations[-1] = HOLD
    palette = [image.quantize(colors=16) for image in frames]
    palette[0].save(
        OUTPUT,
        save_all=True,
        append_images=palette[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"{OUTPUT.relative_to(ROOT)}: {len(frames)} frames, {OUTPUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
