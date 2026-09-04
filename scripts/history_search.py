"""Search this project's Claude chat transcripts.

Ported from ApifyMoneySpinner's `ms history search`
(scripts/ms_cli/commands/history_search.py), with two changes for this repo: stdlib
`argparse` instead of `click` (nothing here depends on click, and the point of the tool
is that it runs with a bare `python`), and a slug rule that works on Windows paths as
well as POSIX ones.

Finds where something was said across every session for this repo -- e.g. "where did I
say the dial has to be on Remote Control?". Defaults to YOUR (user) turns, since the
usual question is "what did I actually ask for"; use --role all to include the
assistant's replies. Case-insensitive substring by default, --regex for a pattern.
Pasted-in dumps (huge ChatGPT quotes) are skipped unless --include-dumps.

    python scripts/history_search.py "remote control"
    python scripts/history_search.py "mqtt" --role all --context 200
    python scripts/history_search.py "PROG_PHASE" --regex --full
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]  # the repo root


def _slug(path: Path) -> str:
    """Claude Code's project-directory name for a repo path.

    Every non-alphanumeric character becomes a hyphen, which is why C:\\Users\\me\\haier
    lands in C--Users-me-haier (the drive colon and the separator after it each contribute
    one) and /home/me/haier lands in -home-me-haier.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


SLUG = _slug(REPO)
PROJECTS = Path.home() / ".claude" / "projects" / SLUG
# Claude Code PRUNES ~/.claude/projects. The archive below is a mirror that never deletes,
# so it is usually the deeper of the two sources -- and it is also where sessions started
# from a different working directory (this project's early work happened in the parent
# folder) get copied to, so they are searchable from here.
# See scripts/claude-transcript-archive.ps1.
ARCHIVE = Path.home() / ".claude-archive" / "projects" / SLUG


def _sources(include_subagents: bool) -> list[Path]:
    """Live + archive, deduped by session id, preferring the live copy.

    Same session id means same session; the live file is the one still being appended to,
    so it wins. Anything the archive holds and ~/.claude no longer does is pruned or
    imported history, and is the whole reason this is not just a glob of PROJECTS.
    """
    seen: dict[str, Path] = {}
    for root in (ARCHIVE, PROJECTS):  # PROJECTS second so it overwrites
        if not root.exists():
            continue
        for f in sorted(root.glob("*.jsonl")):
            seen[f.name] = f
        if include_subagents:
            for f in sorted(root.glob("*/subagents/**/*.jsonl")):
                seen[str(f.relative_to(root))] = f
    return list(seen.values())


def _coverage(files: list[Path], stamps: list[str]) -> str:
    """The window actually searched.

    Printed on every result and on every miss, because a bare "no matches" is the reason a
    pruned decision reads as one that was never made. "Not in the last four weeks" and
    "never discussed" are different answers, and the caller cannot tell them apart without
    this line.

    Measured from the timestamps inside the transcripts, not file mtimes. The upstream
    version used mtime, which is the last append -- an imported session copied in from
    another project folder then reports the day it was copied, hiding the fact that it
    covers the two weeks before it. Falls back to mtime only if nothing was parsed.
    """
    days = sorted({s[:10] for s in stamps if len(s) >= 10})
    if not days:
        days = sorted(
            {
                datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).strftime("%Y-%m-%d")
                for f in files
                if f.exists()
            }
        )
    if not days:
        return "no transcripts on file"
    return f"covers {days[0]} -> {days[-1]}"


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                out.append(p["text"])
        return " ".join(out)
    return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="history_search",
        description=(
            "Search Claude chat transcripts for QUERY, across the live dir AND the archive."
        ),
    )
    ap.add_argument("query")
    ap.add_argument(
        "--role",
        choices=["user", "assistant", "all"],
        default="user",
        help="whose turns to search (default: user)",
    )
    ap.add_argument("--regex", action="store_true", help="treat QUERY as a regular expression")
    ap.add_argument(
        "--context",
        dest="ctx",
        type=int,
        default=300,
        help="chars of context around the hit (default: 300)",
    )
    ap.add_argument(
        "--full", action="store_true", help="print the whole matching message, not a snippet"
    )
    ap.add_argument("--limit", type=int, default=40, help="max matches to print (default: 40)")
    ap.add_argument(
        "--include-dumps", action="store_true", help="don't skip very long pasted messages"
    )
    ap.add_argument("--session", help="restrict to one session id (or its prefix)")
    ap.add_argument(
        "--subagents",
        action="store_true",
        help="also search subagent transcripts (research/audit output; ~5x the files)",
    )
    a = ap.parse_args(argv)

    files = _sources(a.subagents)
    if not files:
        print(f"no transcripts at {PROJECTS} or {ARCHIVE}", file=sys.stderr)
        return 1
    pat = re.compile(a.query if a.regex else re.escape(a.query), re.I)

    if a.session:
        files = [f for f in files if f.stem.startswith(a.session)]

    hits = []
    stamps: list[str] = []
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for line in lines:
            try:
                o = json.loads(line)
            except Exception:
                continue
            ts = o.get("timestamp")
            if isinstance(ts, str) and ts:
                stamps.append(ts)
            typ = o.get("type")
            if typ not in ("user", "assistant"):
                continue
            if a.role != "all" and typ != a.role:
                continue
            txt = _text(o.get("message", {}).get("content"))
            if not txt:
                continue
            if not a.include_dumps and len(txt) > 4000:
                continue
            m = pat.search(txt)
            if not m:
                continue
            hits.append((o.get("timestamp") or "", f.stem[:8], typ, txt, m.start()))

    hits.sort(key=lambda h: h[0])
    cov = _coverage(files, stamps)
    if not hits:
        # Never a bare "no matches". A miss outside the covered window means "not
        # searched", not "not said", and the two get confused precisely when it matters.
        print(f"no matches for {a.query!r} in {len(files)} transcript(s) - {cov}.")
        if not a.subagents:
            print("  subagent transcripts were NOT searched; add --subagents.")
        print(
            "  anything older than that window predates the archive and is gone "
            "unless recovered from a backup."
        )
        return 0

    shown = hits[-a.limit :]
    more = f" (showing last {a.limit})" if len(hits) > a.limit else ""
    print(
        f"{len(hits)} match(es){more} for {a.query!r} - role={a.role} - "
        f"{len(files)} transcript(s), {cov}\n"
    )
    for ts, sid, typ, txt, at in shown:
        try:
            tstr = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%m-%d %H:%M")
        except Exception:
            tstr = ts[:16] or "??"
        who = "YOU " if typ == "user" else "asst"
        if a.full:
            body = txt.strip()
        else:
            lo, hi = max(0, at - a.ctx // 3), min(len(txt), at + a.ctx)
            body = (
                ("..." if lo else "")
                + txt[lo:hi].strip().replace("\n", " ")
                + ("..." if hi < len(txt) else "")
            )
        print(f"[{sid} {tstr}] {who}: {body}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
