#Requires -Version 5.1
<#
.SYNOPSIS
  Build Bowl-A-Lyzer locally on Windows and deploy to the VPS via docker save/scp/ssh.

.DESCRIPTION
  1. docker compose build (repo root)
  2. Tag image as bowlyzer:release
  3. docker save -> deploy/artifacts/bowlyzer-image.tar
  4. scp compose file + image to VPS
  5. ssh: docker load && docker compose -f docker-compose.prod.yml up -d

  Prerequisites: Docker Desktop, OpenSSH client (ssh/scp), SSH key access to VPS.

.PARAMETER RemoteHost
  VPS hostname or IP. Overrides deploy.config.ps1.

.PARAMETER RemoteUser
  SSH user (default: root).

.PARAMETER RemoteDir
  Directory on VPS (default: /root/bowlyzer).

.PARAMETER SkipBuild
  Skip docker compose build (reuse existing local image).

.PARAMETER SyncDatabase
  Also upload ./database (can be large; usually only when CSV data changed).

.PARAMETER SkipUpload
  Only build and save image locally (no scp/ssh).

.EXAMPLE
  cd C:\Users\cfell\repositories\bowlyzer_deploy
  Copy-Item deploy\deploy.config.example.ps1 deploy\deploy.config.ps1
  # edit deploy.config.ps1
  .\deploy\deploy.ps1

.EXAMPLE
  .\deploy\deploy.ps1 -RemoteHost 212.227.57.223 -SyncDatabase
#>
[CmdletBinding()]
param(
    [string] $RemoteHost,
    [string] $RemoteUser = "root",
    [string] $RemoteDir = "/root/bowlyzer",
    [string] $ReleaseImage = "bowlyzer:release",
    [switch] $SkipBuild,
    [switch] $SyncDatabase,
    [switch] $SkipUpload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Require-Command([string] $Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found on PATH: $Name"
    }
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

$configPath = Join-Path $PSScriptRoot "deploy.config.ps1"
if (Test-Path $configPath) {
    Write-Host "==> loading $configPath"
    $cfg = & $configPath
    if ($cfg.RemoteHost -and -not $PSBoundParameters.ContainsKey("RemoteHost")) { $RemoteHost = $cfg.RemoteHost }
    if ($cfg.RemoteUser -and -not $PSBoundParameters.ContainsKey("RemoteUser")) { $RemoteUser = $cfg.RemoteUser }
    if ($cfg.RemoteDir -and -not $PSBoundParameters.ContainsKey("RemoteDir")) { $RemoteDir = $cfg.RemoteDir }
    if ($cfg.ReleaseImage -and -not $PSBoundParameters.ContainsKey("ReleaseImage")) { $ReleaseImage = $cfg.ReleaseImage }
}

if (-not $SkipUpload -and [string]::IsNullOrWhiteSpace($RemoteHost)) {
    throw @"
RemoteHost is required. Either:
  - Copy deploy\deploy.config.example.ps1 to deploy\deploy.config.ps1 and set RemoteHost, or
  - Pass -RemoteHost <ip-or-hostname>
"@
}

Require-Command "docker"
if (-not $SkipUpload) {
    Require-Command "ssh"
    Require-Command "scp"
}

$ArtifactsDir = Join-Path $PSScriptRoot "artifacts"
$ImageTar = Join-Path $ArtifactsDir "bowlyzer-image.tar"
$ComposeProd = Join-Path $PSScriptRoot "docker-compose.prod.yml"
# Compose names the image {folder}-bowlyzer:latest (e.g. bowlyzer_deploy-bowlyzer).
$ComposeProjectImage = $null
foreach ($candidate in @("bowlyzer_deploy-bowlyzer:latest", "bowlyzer-bowlyzer:latest")) {
    if (docker image inspect $candidate 2>$null) {
        $ComposeProjectImage = $candidate
        break
    }
}

New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null

if (-not $SkipBuild) {
    Write-Host "==> docker compose build"
    docker compose build
    if ($LASTEXITCODE -ne 0) { throw "docker compose build failed with exit code $LASTEXITCODE" }
}

if (-not $ComposeProjectImage) {
    throw "Local compose image not found (tried bowlyzer_deploy-bowlyzer:latest and bowlyzer-bowlyzer:latest). Run without -SkipBuild."
}
Write-Host "==> using local image $ComposeProjectImage"

Write-Host "==> tagging $ComposeProjectImage -> $ReleaseImage"
docker tag $ComposeProjectImage $ReleaseImage
if ($LASTEXITCODE -ne 0) { throw "docker tag failed" }

Write-Host "==> docker save -> $ImageTar"
if (Test-Path $ImageTar) { Remove-Item -Force $ImageTar }
docker save $ReleaseImage -o $ImageTar
if ($LASTEXITCODE -ne 0) { throw "docker save failed" }
$tarSizeMb = [math]::Round((Get-Item $ImageTar).Length / 1MB, 1)
Write-Host "    saved ${tarSizeMb} MB"

if ($SkipUpload) {
    Write-Host "==> SkipUpload set; done."
    exit 0
}

$Remote = "${RemoteUser}@${RemoteHost}"
$RemoteCompose = "$RemoteDir/docker-compose.prod.yml"
$RemoteTar = "$RemoteDir/bowlyzer-image.tar"

Write-Host "==> ensuring remote directory $RemoteDir"
ssh $Remote "mkdir -p '$RemoteDir'"
if ($LASTEXITCODE -ne 0) { throw "ssh mkdir failed" }

Write-Host "==> uploading compose + image"
scp $ComposeProd "${Remote}:${RemoteCompose}"
if ($LASTEXITCODE -ne 0) { throw "scp compose failed" }
scp $ImageTar "${Remote}:${RemoteTar}"
if ($LASTEXITCODE -ne 0) { throw "scp image failed" }

if ($SyncDatabase) {
    Write-Host "==> uploading database/ (may take a while)"
    scp -r (Join-Path $RepoRoot "database") "${Remote}:${RemoteDir}/"
    if ($LASTEXITCODE -ne 0) { throw "scp database failed" }
} else {
    Write-Host "==> skipping database/ (use -SyncDatabase when CSV data changed)"
}

Write-Host "==> remote: load image and restart container"
# Bash on Linux chokes on Windows CRLF in the here-string (wrong paths, bogus flags, "set: invalid option").
$remoteScript = @"
set -e
cd '$RemoteDir'
docker load -i bowlyzer-image.tar
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker compose -f docker-compose.prod.yml ps
echo -n 'health /liga: '
curl -sf -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/liga || echo 'curl failed'
"@ -replace "`r`n", "`n" -replace "`r", ""

$remoteScript | ssh $Remote "bash -s"
if ($LASTEXITCODE -ne 0) { throw "remote deploy failed" }

Write-Host ""
Write-Host "==> deploy finished"
Write-Host "    Site (if nginx proxies to :8080): https://your-domain"
Write-Host "    Direct: http://${RemoteHost}:8080/liga"
Write-Host "    Logs:   ssh $Remote 'cd $RemoteDir && docker compose -f docker-compose.prod.yml logs -f --tail 50'"
