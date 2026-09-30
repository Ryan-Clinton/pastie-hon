"""Print one version's section of CHANGELOG.md, for the GitHub Release.

    python scripts/release_notes.py 0.3.0

The changelog is the one place release notes are written. Copying them into a
release by hand is how the two come to disagree.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def section(text: str, version: str) -> str:
    """The body under `## <version>`, up to the next `## ` heading."""
    heading = re.compile(rf"^## \[?{re.escape(version)}\b.*$", re.MULTILINE)
    found = heading.search(text)
    if found is None:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    rest = text[found.end() :]
    following = re.search(r"^## ", rest, re.MULTILINE)
    return (rest[: following.start()] if following else rest).strip() + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        raise SystemExit("usage: release_notes.py <version>")
    sys.stdout.write(section(CHANGELOG.read_text(encoding="utf-8"), argv[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
