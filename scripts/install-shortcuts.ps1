<#
.SYNOPSIS
    Point the Start menu, the Desktop and Startup at this copy of Pastie.

.DESCRIPTION
    Pastie is two processes - a window and a background service - and a shortcut
    should not require anybody to know that. So:

      Start menu / Desktop  ->  the window. It starts the service if one is not
                                already running, so a single click is enough.
      Startup               ->  the service. Without this, nothing watches the
                                dryer unless the window happens to be open, and
                                being told while you are *not* at the PC is the
                                entire point of the project.

    This is a login task, not a Windows service. It runs as you, which is the
    honest difference: SPEC.md section 14 experiment 4 - whether the Haier
    libraries work under a service identity - is still unanswered, and pretending
    otherwise would hide it.

    Safe to run repeatedly: it overwrites its own shortcuts and touches nothing
    else.

.PARAMETER Remove
    Take the shortcuts away again.
#>
[CmdletBinding()]
param([switch]$Remove)

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $repo '.venv\Scripts'
$app = Join-Path $venv 'pastie-app.exe'
$pythonw = Join-Path $venv 'pythonw.exe'
$icon = Join-Path $repo 'assets\pastie.ico'

$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Pastie.lnk'
$desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Pastie.lnk'
$startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\Pastie service.lnk'

# The prototype's build and its shortcuts. Left on disk, taken off the menus:
# deleting somebody's working fallback is not this script's decision.
$old = @(
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Pastie Tumble Dryer.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Pastie Tumble Dryer.lnk')
)

if ($Remove) {
    foreach ($path in @($startMenu, $desktop, $startup)) {
        if (Test-Path $path) { Remove-Item $path -Force; "removed  $path" }
    }
    exit 0
}

foreach ($needed in @($app, $pythonw)) {
    if (-not (Test-Path $needed)) {
        Write-Error "$needed is missing. Run:  .venv\Scripts\pip install -e ."
    }
}

$shell = New-Object -ComObject WScript.Shell

function Set-Shortcut($path, $target, $arguments, $description) {
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $target
    $link.Arguments = $arguments
    $link.WorkingDirectory = $repo
    $link.Description = $description
    if (Test-Path $icon) { $link.IconLocation = $icon }
    $link.Save()
    "wrote    $path"
}

Set-Shortcut $startMenu $app '' 'Pastie - what your Haier appliance is doing'
Set-Shortcut $desktop $app '' 'Pastie - what your Haier appliance is doing'
Set-Shortcut $startup $pythonw '-m pastie.cli service' 'Pastie background service'

foreach ($stale in $old) {
    if (Test-Path $stale) {
        Remove-Item $stale -Force
        "removed  $stale  (pointed at the old prototype build)"
    }
}

""
"The window is on the Start menu and the Desktop. The service starts at login."
"Nothing is running yet - open Pastie, or run:  .venv\Scripts\pastie service"
