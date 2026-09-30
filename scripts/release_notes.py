"""Print one version's release notes, from its section of CHANGELOG.md.

    python scripts/release_notes.py 0.3.0 > NOTES.md

A version's section opens with a short summary written for the release page -
what's new, what to download, what to know - before its first `###` heading.
Only that summary goes on the GitHub Release, followed by a link to the full
section. The changelog stays exhaustive; the release page stays readable.

The output is always UTF-8. On the Windows release runner Python's stdout is the
ANSI code page, and the 0.3.0 notes went up with every dash and arrow turned
into a replacement character.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
FULL = "https://github.com/Ryan-Clinton/pastie-hon/blob/main/CHANGELOG.md"


def section(text: str, version: str) -> str:
    """The body under `## [<version>]`, up to the next `## ` heading."""
    heading = re.compile(rf"^## \[?{re.escape(version)}\b.*$", re.MULTILINE)
    found = heading.search(text)
    if found is None:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    rest = text[found.end() :]
    following = re.search(r"^## ", rest, re.MULTILINE)
    return (rest[: following.start()] if following else rest).strip()


def notes(text: str, version: str) -> str:
    """The release page: the section's summary, then a pointer to the rest."""
    body = section(text, version)
    first_heading = re.search(r"^### ", body, re.MULTILINE)
    summary = (body[: first_heading.start()] if first_heading else body).strip()
    return f"{summary}\n\n**Full technical changes:** [CHANGELOG.md]({FULL})\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        raise SystemExit("usage: release_notes.py <version>")
    output = notes(CHANGELOG.read_text(encoding="utf-8"), argv[0])
    sys.stdout.buffer.write(output.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
