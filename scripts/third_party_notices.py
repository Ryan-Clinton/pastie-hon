"""Generate THIRD_PARTY_NOTICES.txt from the dependencies actually installed.

The packaged .exe contains other people's code, and their licences require their
notices to travel with it. Not everything is MIT: the Amazon networking
components (`awscrt`, `awsiotsdk`) are Apache-2.0, which asks for more than MIT
does - attribution, a copy of the licence, and any NOTICE file carried through.

Generated rather than hand-written, because a hand-written list is wrong the
first time somebody adds a dependency and nobody notices for a year.

    python scripts/third_party_notices.py            write the file
    python scripts/third_party_notices.py --check    fail if it would change

`--check` is what CI runs: it does not commit anything, it just refuses to let
the tree drift from the pinned dependency list.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "THIRD_PARTY_NOTICES.txt"

HEADER = """\
THIRD PARTY NOTICES
===================

Pastie is distributed with the third-party software listed below. Each remains
under its own licence and its own copyright. This file is generated from the
installed dependency set by scripts/third_party_notices.py - do not edit it by
hand.

Licences that ask for more than attribution - Apache-2.0 in particular - require
their full text and any NOTICE file to be shipped alongside the binary. Where a
package below is Apache-2.0, its LICENSE and NOTICE files are included in the
distribution.

Generated: {generated}

"""


def shipped_packages() -> set[str]:
    """What actually goes in the box: the runtime dependency closure.

    Not everything installed. ruff, mypy and pytest are in the developer's
    environment and in nobody's .exe, and listing them in a notices file that
    claims to describe what is distributed would make the file a lie in the one
    direction that matters.
    """
    wanted: set[str] = set()
    queue = ["pastie"]
    while queue:
        name = _canonical(queue.pop())
        if name in wanted:
            continue
        wanted.add(name)
        try:
            requirements = metadata.requires(name) or []
        except metadata.PackageNotFoundError:
            continue
        for raw in requirements:
            requirement = Requirement(raw)
            # `; extra == "dev"` means it is only there for us, not for users.
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            queue.append(requirement.name)
    return wanted - {"pastie"}


def installed_packages() -> list[dict[str, str]]:
    """Ask pip-licenses what is installed, then keep only what ships."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "piplicenses",
            "--format=json",
            "--with-urls",
            "--with-authors",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    )
    shipped = shipped_packages()
    packages = [
        package
        for package in json.loads(result.stdout)
        if _canonical(str(package.get("Name", ""))) in shipped
    ]
    return sorted(packages, key=lambda item: str(item.get("Name", "")).lower())


def _canonical(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def render(packages: list[dict[str, str]], *, generated: str) -> str:
    lines = [HEADER.format(generated=generated)]
    for package in packages:
        name = package.get("Name", "?")
        lines.append(f"{name} {package.get('Version', '')}".strip())
        lines.append(f"    Licence : {package.get('License', 'UNKNOWN')}")
        author = package.get("Author", "")
        if author and author != "UNKNOWN":
            lines.append(f"    Author  : {author}")
        url = package.get("URL", "")
        if url and url != "UNKNOWN":
            lines.append(f"    Home    : {url}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the notices would change, rather than writing them",
    )
    args = parser.parse_args(argv)

    try:
        packages = installed_packages()
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        print(f"could not read the installed licences: {error}", file=sys.stderr)
        print("install the dev dependencies first:  pip install -e '.[dev]'", file=sys.stderr)
        return 2

    unknown = [p["Name"] for p in packages if p.get("License") in ("UNKNOWN", "", None)]

    if args.check:
        # The date changes every run, so compare the part that carries meaning:
        # which packages are there and under what terms.
        current = _summary(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else ""
        wanted = _summary(render(packages, generated=""))
        if current != wanted:
            print(
                "THIRD_PARTY_NOTICES.txt is out of date - run "
                "`python scripts/third_party_notices.py`",
                file=sys.stderr,
            )
            return 1
        print(f"notices cover {len(packages)} package(s)")
    else:
        generated = datetime.now(UTC).strftime("%Y-%m-%d")
        OUTPUT.write_text(render(packages, generated=generated), encoding="utf-8")
        print(f"wrote {OUTPUT} ({len(packages)} packages)")

    if unknown:
        # Not fatal, but it is the one thing in here worth a human looking at.
        print(f"note: no licence declared by {', '.join(unknown)}", file=sys.stderr)
    return 0


def _summary(text: str) -> str:
    """The lines that matter, ignoring the generated-on date."""
    return "\n".join(
        line for line in text.splitlines() if line and not line.startswith("Generated:")
    )


if __name__ == "__main__":
    raise SystemExit(main())
