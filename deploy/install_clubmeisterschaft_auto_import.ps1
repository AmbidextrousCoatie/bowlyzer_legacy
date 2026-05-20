# Push Clubmeisterschaft auto-import scripts to the VPS and run the installer.
# Requires deploy/deploy.config.ps1 (same as deploy.ps1).

#Requires -Version 5.1
[CmdletBinding()]
param(
    [string] $RemoteHost,
    [string] $RemoteUser = "root",
    [string] $RemoteDir = "/root/bowlyzer-src",
    [switch] $EnableTimer
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$ConfigPath = Join-Path $PSScriptRoot "deploy.config.ps1"
if (Test-Path $ConfigPath) {
    $cfg = & $ConfigPath
    if ($cfg.RemoteHost) { $RemoteHost = $cfg.RemoteHost }
    if ($cfg.RemoteUser) { $RemoteUser = $cfg.RemoteUser }
}
if (-not $RemoteHost) {
    throw "Set RemoteHost in deploy/deploy.config.ps1 or pass -RemoteHost"
}

$Remote = "${RemoteUser}@${RemoteHost}"
$EnableArg = if ($EnableTimer) { " --enable-timer" } else { "" }

Write-Host "==> ensuring remote dir $RemoteDir"
ssh $Remote "mkdir -p '$RemoteDir'"
if ($LASTEXITCODE -ne 0) { throw "ssh mkdir failed" }

$paths = @(
    "scripts/clubmeisterschaft_auto_import.sh",
    "scripts/install_clubmeisterschaft_auto_import.sh",
    "deploy/vps/clubmeisterschaft-import.env.example",
    "deploy/vps/clubmeisterschaft-import.service",
    "deploy/vps/clubmeisterschaft-import.timer"
)
foreach ($rel in $paths) {
    $local = Join-Path $RepoRoot $rel
    if (-not (Test-Path $local)) { throw "Missing $local" }
    $remoteParent = ($rel -replace '/[^/]+$', '' -replace '\\[^\\]+$', '')
    if ($remoteParent) {
        ssh $Remote "mkdir -p '$RemoteDir/$($remoteParent -replace '\\','/')'"
    }
    $remotePath = "$RemoteDir/$($rel -replace '\\','/')"
    Write-Host "==> scp $rel"
    scp $local "${Remote}:${remotePath}"
    if ($LASTEXITCODE -ne 0) { throw "scp failed for $rel" }
}

Write-Host "==> normalizing shell script line endings on VPS"
ssh $Remote "sed -i 's/\r$//' '$RemoteDir'/scripts/*.sh && chmod +x '$RemoteDir'/scripts/*.sh"
if ($LASTEXITCODE -ne 0) { throw "sed/chmod failed" }

Write-Host "==> remote install"
$remoteCmd = "cd '$RemoteDir' && sudo ./scripts/install_clubmeisterschaft_auto_import.sh$EnableArg"
ssh $Remote $remoteCmd
if ($LASTEXITCODE -ne 0) { throw "remote install failed" }

Write-Host ""
Write-Host "==> next on VPS"
Write-Host "  1. sudo apt install -y rclone && rclone config"
Write-Host "  2. sudo nano /etc/bowlyzer/clubmeisterschaft-import.env"
Write-Host "  3. set -a && source /etc/bowlyzer/clubmeisterschaft-import.env && set +a"
Write-Host "  4. clubmeisterschaft_auto_import.sh --sync-only"
Write-Host ""
Write-Host "See docs/CLUBMEISTERSCHAFT_AUTO_IMPORT.md for dry-run week."
