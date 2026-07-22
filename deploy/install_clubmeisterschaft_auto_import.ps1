# Push Clubmeisterschaft auto-import scripts to the VPS and run the installer as bowlyzer.
# Requires deploy/deploy.config.ps1 (same as deploy.ps1).

#Requires -Version 5.1
[CmdletBinding()]
param(
    [string] $RemoteHost,
    [string] $RemoteUser = "bowlyzer",
    [string] $RemoteDir = "/home/bowlyzer/bowlyzer-src",
    [switch] $EnableTimer,
    [switch] $EnableLinger
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$ConfigPath = Join-Path $PSScriptRoot "deploy.config.ps1"
if (Test-Path $ConfigPath) {
    $cfg = & $ConfigPath
    if ($cfg.RemoteHost) { $RemoteHost = $cfg.RemoteHost }
    if ($cfg.RemoteUser) { $RemoteUser = $cfg.RemoteUser }
    if ($cfg.RemoteDir) { $RemoteDir = $cfg.RemoteDir }
}
if (-not $RemoteHost) {
    throw "Set RemoteHost in deploy/deploy.config.ps1 or pass -RemoteHost"
}

$Remote = "${RemoteUser}@${RemoteHost}"
$EnableArg = if ($EnableTimer) { " --enable-timer" } else { "" }

function Send-UnixLfFile {
    param(
        [Parameter(Mandatory = $true)][string] $LocalPath,
        [Parameter(Mandatory = $true)][string] $RemoteDest
    )
    if ($LocalPath -match '\.sh$') {
        $text = [System.IO.File]::ReadAllText($LocalPath) -replace "`r`n", "`n" -replace "`r", "`n"
        $temp = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), [System.IO.Path]::GetRandomFileName() + ".sh")
        [System.IO.File]::WriteAllText($temp, $text, [System.Text.UTF8Encoding]::new($false))
        try {
            scp $temp "${Remote}:${RemoteDest}"
            if ($LASTEXITCODE -ne 0) { throw "scp failed for $LocalPath" }
        }
        finally {
            Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
        }
    }
    else {
        scp $LocalPath "${Remote}:${RemoteDest}"
        if ($LASTEXITCODE -ne 0) { throw "scp failed for $LocalPath" }
    }
}

Write-Host "==> ensuring remote dir $RemoteDir (as $RemoteUser)"
ssh $Remote "mkdir -p '$RemoteDir'"
if ($LASTEXITCODE -ne 0) { throw "ssh mkdir failed" }

$paths = @(
    "scripts/publish_tournament_parquet.py",
    "scripts/send_notify_email.py",
    "scripts/clubmeisterschaft_auto_import.sh",
    "scripts/data/import_clubmeisterschaft_donaubowler_xlsx.py",
    "scripts/bootstrap_clubmeisterschaft_dropbox.sh",
    "scripts/install_clubmeisterschaft_auto_import.sh",
    "scripts/install_clubmeisterschaft_linger.sh",
    "deploy/vps/clubmeisterschaft-import.env.example",
    "deploy/vps/user/clubmeisterschaft-import.service",
    "deploy/vps/user/clubmeisterschaft-import.timer"
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
    Send-UnixLfFile -LocalPath $local -RemoteDest $remotePath
}

Write-Host "==> chmod scripts on VPS"
    ssh $Remote "mkdir -p '$RemoteDir'/database/input; chmod +x '$RemoteDir'/scripts/*.sh"

Write-Host "==> install as $RemoteUser (no root)"
$remoteCmd = "cd '$RemoteDir'; ./scripts/install_clubmeisterschaft_auto_import.sh$EnableArg"
ssh $Remote $remoteCmd
if ($LASTEXITCODE -ne 0) { throw "remote install failed" }

if ($EnableLinger -or $EnableTimer) {
    Write-Host "==> enable linger (root, one-time - timers survive reboot without login)"
    $lingerCmd = "cd '$RemoteDir'; ./scripts/install_clubmeisterschaft_linger.sh"
    ssh "root@${RemoteHost}" $lingerCmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "warning: linger install failed (run manually: sudo ./scripts/install_clubmeisterschaft_linger.sh on VPS)"
    }
}

Write-Host ""
Write-Host "==> next on VPS (as $RemoteUser)"
Write-Host "  1. rclone config    # dedicated Dropbox user"
Write-Host "  2. nano ~/.config/bowlyzer/clubmeisterschaft-import.env"
Write-Host "  3. ./scripts/bootstrap_clubmeisterschaft_dropbox.sh"
Write-Host ""
Write-Host "Logs: journalctl --user -u clubmeisterschaft-import.service -f"
Write-Host "See docs/CLUBMEISTERSCHAFT_AUTO_IMPORT.md"
