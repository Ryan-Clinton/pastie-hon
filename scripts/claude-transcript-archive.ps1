# Archive every Claude Code transcript, for every project, out of the pruning window.
#
# WHY: Claude Code deletes old session transcripts from ~/.claude/projects. When that
# happens `history_search.py` cannot find them, and "no matches" reads as "never
# discussed" -- which is exactly wrong when the thing you are looking for is a decision
# you made two months ago. An archive outside ~/.claude is the only thing that makes
# searching past decisions durable.
#
# Windows port of ApifyMoneySpinner's scripts/claude-transcript-archive.sh. A plain
# mirror, on purpose:
#   * Copy-only-if-newer, so a live session still being appended to converges on the next
#     run instead of being truncated.
#   * NO delete. If Claude prunes a session, the archive keeps it. That is the point.
#     It is also what keeps imported history (sessions copied in from another project
#     folder) alive here.
#   * NO compression. Compressing means the next run sees the .jsonl "missing" and copies
#     it again, then recompresses it -- churn every run, and two copies of the same
#     session whenever the timing is unlucky.
#
# Includes subagent transcripts (<session>/subagents/**/agent-*.jsonl); they carry the
# research and audit output, which is exactly the material worth searching later.
#
# Run it by hand, or hourly:
#   schtasks /create /tn "claude-transcript-archive" /sc hourly `
#     /tr "powershell -NoProfile -File <repo>\scripts\claude-transcript-archive.ps1"

$ErrorActionPreference = 'Stop'

$src = if ($env:CLAUDE_PROJECTS_DIR) { $env:CLAUDE_PROJECTS_DIR } else { Join-Path $HOME '.claude\projects' }
$dest = if ($env:CLAUDE_ARCHIVE_DIR) { $env:CLAUDE_ARCHIVE_DIR } else { Join-Path $HOME '.claude-archive\projects' }

if (-not (Test-Path $src)) { Write-Error "no source dir: $src"; exit 1 }
if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }

$copied = 0
foreach ($f in Get-ChildItem -Path $src -Filter *.jsonl -Recurse -File) {
    $rel = $f.FullName.Substring($src.Length).TrimStart('\', '/')
    $target = Join-Path $dest $rel
    $dir = Split-Path $target -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    # Update-only: never overwrite a newer copy with an older one.
    $existing = Get-Item -LiteralPath $target -ErrorAction SilentlyContinue
    if ($null -eq $existing -or $f.LastWriteTimeUtc -gt $existing.LastWriteTimeUtc) {
        Copy-Item -LiteralPath $f.FullName -Destination $target -Force
        $copied++
    }
}

$srcN = (Get-ChildItem -Path $src -Filter *.jsonl -Recurse -File).Count
$arcN = (Get-ChildItem -Path $dest -Filter *.jsonl -Recurse -File).Count
$projects = (Get-ChildItem -Path $dest -Directory).Count
"{0} archive: {1} transcript(s) across {2} project(s), {3} updated this run (~/.claude has {4})" -f `
    (Get-Date -Format o), $arcN, $projects, $copied, $srcN
