# Copy VPS maintenance scripts and run disk cleanup + optional bowlyzer user setup.
# Run from repo root. Uses deploy/deploy.config.ps1 (RemoteHost); defaults to root for one-time ops.

#Requires -Version 5.1
[CmdletBinding()]
param(
    [string] $RemoteHost,
    [string] $RemoteUser = "root",
    [switch] $SetupBowlyzerUser,
    [switch] $MigrateFromRoot,
    [switch] $AggressiveCleanup,
    [switch] $ReportOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$configPath = Join-Path $PSScriptRoot "deploy.config.ps1"
if (Test-Path $configPath) {
    $cfg = & $configPath
    if ($cfg.RemoteHost) { $RemoteHost = $cfg.RemoteHost }
}
if (-not $RemoteHost) { throw "Set RemoteHost in deploy.config.ps1 or pass -RemoteHost" }

$Remote = "${RemoteUser}@${RemoteHost}"
$RemoteTmp = "/tmp/bowlyzer-vps-scripts"

Write-Host "==> uploading maintenance scripts to $RemoteTmp"
ssh $Remote "mkdir -p '$RemoteTmp'"
foreach ($name in @("cleanup-disk.sh", "docker-disk-report.sh", "setup-bowlyzer-user.sh")) {
    $local = Join-Path $PSScriptRoot "vps" $name
    scp $local "${Remote}:${RemoteTmp}/$name"
    if ($LASTEXITCODE -ne 0) { throw "scp failed: $name" }
}

# Windows editors may save CRLF; strip before bash runs on Linux.
Write-Host "==> normalizing line endings (CRLF -> LF)"
ssh $Remote "sed -i 's/\r$//' '$RemoteTmp'/*.sh && chmod +x '$RemoteTmp'/*.sh"
if ($LASTEXITCODE -ne 0) { throw "sed/chmod on remote scripts failed" }

if ($ReportOnly) {
    Write-Host "==> running docker-disk-report.sh"
    ssh $Remote "bash '$RemoteTmp/docker-disk-report.sh'"
    if ($LASTEXITCODE -ne 0) { throw "report failed" }
} else {
    $cleanupArg = if ($AggressiveCleanup) { " --aggressive" } else { "" }
    Write-Host "==> running cleanup-disk.sh$cleanupArg"
    ssh $Remote "bash '$RemoteTmp/cleanup-disk.sh$cleanupArg'"
    if ($LASTEXITCODE -ne 0) { throw "cleanup failed" }
}

if ($SetupBowlyzerUser) {
    $migrateArg = if ($MigrateFromRoot) { " --migrate-from-root" } else { "" }
    Write-Host "==> running setup-bowlyzer-user.sh$migrateArg"
    ssh $Remote "bash '$RemoteTmp/setup-bowlyzer-user.sh$migrateArg'"
    if ($LASTEXITCODE -ne 0) { throw "setup failed" }
    Write-Host ""
    Write-Host "Next: ssh-copy-id bowlyzer@${RemoteHost}"
    Write-Host "       Update deploy.config.ps1: RemoteUser=bowlyzer RemoteDir=/home/bowlyzer/bowlyzer"
}

Write-Host "==> done"
