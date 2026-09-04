# ms -- tiny command entry point, so the invocation matches the ApifyMoneySpinner CLI
# this was ported from (`bash scripts/ms history search "..."`).
#
#   powershell -File scripts\ms.ps1 history search "remote control"
#   powershell -File scripts\ms.ps1 history search "mqtt" --role all
#
# Deliberately not a framework: this repo has one command. Adding a second means adding
# a branch here, not porting ms_cli's lazy dispatcher.

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$scripts = Split-Path -Parent $MyInvocation.MyCommand.Path

function Show-Usage {
    "ms -- Pastie Tumble Dryer helper commands"
    ""
    "  ms history search <query> [--role user|assistant|all] [--regex] [--full]"
    "                           [--context N] [--limit N] [--include-dumps]"
    "                           [--session ID] [--subagents]"
    ""
    "      Search this project's Claude chat transcripts (live dir + archive)."
}

if ($Args.Count -lt 2 -or $Args[0] -in @('-h', '--help', 'help')) { Show-Usage; exit 0 }

if ($Args[0] -eq 'history' -and $Args[1] -eq 'search') {
    $rest = @($Args | Select-Object -Skip 2)
    & python (Join-Path $scripts 'history_search.py') @rest
    exit $LASTEXITCODE
}

"unknown command: $($Args -join ' ')"
""
Show-Usage
exit 2
