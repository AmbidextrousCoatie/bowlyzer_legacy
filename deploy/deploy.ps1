#Requires -Version 5.1
<#
.SYNOPSIS
  Build Bowl-A-Lyzer locally on Windows and deploy to the VPS via docker save/scp/ssh.

.DESCRIPTION
  1. docker compose build (repo root)
  2. Tag image as bowlyzer:release
  3. docker save -> gzip -> deploy/artifacts/bowlyzer-image.tar.gz (smaller/faster scp than raw tar)
  4. scp compose file + image to VPS
  5. ssh: docker load && docker compose -f docker-compose.prod.yml up -d

  Prerequisites: Docker engine running locally (Docker Desktop on Windows), OpenSSH client (ssh/scp).

.PARAMETER RemoteHost
  VPS hostname or IP. Overrides deploy.config.ps1.

.PARAMETER RemoteUser
  SSH user (default: bowlyzer). Use root only for one-time setup-bowlyzer-user.sh.

.PARAMETER RemoteDir
  Directory on VPS (default: /home/bowlyzer/bowlyzer).

.PARAMETER SkipBuild
  Skip docker compose build (reuse existing local image). Use -SkipBuild (one hyphen). Do not use --SkipBuild (Git-style); if you do, the script tries to correct it.

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
    [string] $RemoteUser = "bowlyzer",
    [string] $RemoteDir = "/home/bowlyzer/bowlyzer",
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

function Compress-FileGzip([string] $SourcePath, [string] $DestinationPath) {
    $inStream = [System.IO.File]::OpenRead($SourcePath)
    try {
        $outStream = [System.IO.File]::Create($DestinationPath)
        try {
            $gzip = New-Object System.IO.Compression.GzipStream(
                $outStream,
                [System.IO.Compression.CompressionLevel]::Optimal
            )
            try {
                $inStream.CopyTo($gzip)
            }
            finally { $gzip.Dispose() }
        }
        finally { $outStream.Dispose() }
    }
    finally { $inStream.Dispose() }
}

function Invoke-SshBashScript {
    <#
      Run a multi-line bash script on the remote host without letting Windows CRLF reach the
      remote shell. Piping a here-string to ssh in PowerShell can emit CRLF line endings and
      break commands like 'tail -n 1' (error: invalid number of lines: '1\r').
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string] $ScriptBody,
        [Parameter(Mandatory = $true)]
        [string] $SshTarget,
        [string[]] $SshOpts = @()
    )
    $clean = ($ScriptBody -replace "`r", "")
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("bowlyzer-deploy-" + [Guid]::NewGuid().ToString() + ".sh")
    $outFile = Join-Path ([System.IO.Path]::GetTempPath()) ("bowlyzer-deploy-" + [Guid]::NewGuid().ToString() + ".out")
    $errFile = Join-Path ([System.IO.Path]::GetTempPath()) ("bowlyzer-deploy-" + [Guid]::NewGuid().ToString() + ".err")
    try {
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($tmp, $clean, $utf8)
        $sshExe = (Get-Command ssh -CommandType Application | Select-Object -First 1).Source
        $allArgs = [string[]]($SshOpts + @($SshTarget, "bash", "-s"))
        $p = Start-Process -FilePath $sshExe -ArgumentList $allArgs `
            -RedirectStandardInput $tmp -RedirectStandardOutput $outFile -RedirectStandardError $errFile `
            -NoNewWindow -Wait -PassThru
        if (Test-Path $outFile) {
            Get-Content -LiteralPath $outFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
        }
        if (Test-Path $errFile) {
            Get-Content -LiteralPath $errFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
        }
        if ($null -ne $p -and $p.ExitCode -ne 0) {
            throw "remote ssh failed with exit code $($p.ExitCode)"
        }
    }
    finally {
        Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $outFile -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $errFile -ErrorAction SilentlyContinue
    }
}

function Exit-IfDockerDaemonUnreachable {
    # Avoid cryptic "npipe dockerDesktopLinuxEngine" errors when Docker Desktop is off.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $null = & docker info 2>&1
    $daemonOk = $?
    $ErrorActionPreference = $prevEap
    if ($daemonOk) {
        return
    }
    Write-Host ""
    Write-Host "  DEPLOY ABORTED: Docker engine is not running or not reachable." -ForegroundColor Yellow
    Write-Host @"

  This script builds the image on your PC and needs a working local Docker daemon.
  On Windows with Docker Desktop:
    1. Start Docker Desktop from the Start menu.
    2. Wait until it shows ""Engine running"" (whale icon steady).
    3. Run: docker version
       (Client AND Server sections should both print - if Server is missing, the daemon is down.)

  Then run this deploy script again.

"@ -ForegroundColor Gray
    exit 1
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

# Windows PowerShell does not treat '--SwitchName' as a switch; the first '--…' token is often bound as
# positional value for the first [string] parameter (-RemoteHost). Recognize and fix common mistakes.
if ($RemoteHost -match '^--(.+)$') {
    $tok = $Matches[1]
    $handled = $false
    switch -Regex ($tok) {
        '(?i)^skipbuild$' {
            if (-not $SkipBuild) {
                Write-Host "==> treating '$RemoteHost' as -SkipBuild (PowerShell: use -SkipBuild, not Unix-style --)"
            }
            $SkipBuild = $true
            $handled = $true
        }
        '(?i)^syncdatabase$' {
            $SyncDatabase = $true
            $handled = $true
        }
        '(?i)^skipupload$' {
            $SkipUpload = $true
            $handled = $true
        }
    }
    if ($handled) {
        $RemoteHost = $null
        if (Test-Path $configPath) {
            $cfgR = & $configPath
            if ($cfgR.RemoteHost) { $RemoteHost = $cfgR.RemoteHost }
        }
    }
}

if (-not $SkipUpload -and [string]::IsNullOrWhiteSpace($RemoteHost)) {
    throw @"
RemoteHost is required. Either:
  - Copy deploy\deploy.config.example.ps1 to deploy\deploy.config.ps1 and set RemoteHost, or
  - Pass -RemoteHost <ip-or-hostname>
"@
}

Require-Command "docker"
Exit-IfDockerDaemonUnreachable
if (-not $SkipUpload) {
    Require-Command "ssh"
    Require-Command "scp"
}

$ArtifactsDir = Join-Path $PSScriptRoot "artifacts"
$ImageTar = Join-Path $ArtifactsDir "bowlyzer-image.tar"
$ImageTarGz = Join-Path $ArtifactsDir "bowlyzer-image.tar.gz"
$ComposeProd = Join-Path $PSScriptRoot "docker-compose.prod.yml"
# Compose names the image {folder}-bowlyzer:latest (e.g. bowlyzer_deploy-bowlyzer).
$ComposeProjectImage = $null
foreach ($candidate in @("bowlyzer_deploy-bowlyzer:latest", "bowlyzer-bowlyzer:latest")) {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $null = & docker image inspect $candidate 2>&1
    $found = $?
    $ErrorActionPreference = $prevEap
    if ($found) {
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

Write-Host "==> docker save -> gzip -> $(Split-Path -Leaf $ImageTarGz)"
if (Test-Path $ImageTar) { Remove-Item -Force $ImageTar }
if (Test-Path $ImageTarGz) { Remove-Item -Force $ImageTarGz }
docker save $ReleaseImage -o $ImageTar
if ($LASTEXITCODE -ne 0) { throw "docker save failed" }
$rawMb = [math]::Round((Get-Item $ImageTar).Length / 1MB, 1)
Write-Host "    uncompressed tar ${rawMb} MB - compressing (gzip)..."
Write-Host "    (gzip is CPU-bound; 10-40s silence here is normal for this size.)"
Compress-FileGzip -SourcePath $ImageTar -DestinationPath $ImageTarGz
Remove-Item -Force $ImageTar
$gzMb = [math]::Round((Get-Item $ImageTarGz).Length / 1MB, 1)
$pct = if ($rawMb -gt 0) { [math]::Round(100.0 * $gzMb / $rawMb, 0) } else { 0 }
Write-Host ('    artifact {0} MB (~{1}% of tar - faster scp than uncompressed)' -f $gzMb, $pct)

if ($SkipUpload) {
    Write-Host "==> SkipUpload set; done."
    exit 0
}

# ssh/scp share options (slow networks, first DNS lookup, or password prompt can pause 10-60s with no output otherwise)
$SshOpts = @(
    '-o', 'ConnectTimeout=45'
    '-o', 'ServerAliveInterval=10'
    '-o', 'ServerAliveCountMax=3'
)

$Remote = "${RemoteUser}@${RemoteHost}"
$RemoteCompose = "$RemoteDir/docker-compose.prod.yml"
$RemoteTarGz = "$RemoteDir/bowlyzer-image.tar.gz"

Write-Host "==> SSH: ensure deploy directory on VPS"
Write-Host "    ($Remote : mkdir -p $RemoteDir)"
Write-Host "    (This step can take 10-60s: DNS, first key auth, or password prompt with no extra lines until it returns.)"
& ssh @SshOpts $Remote "mkdir -p '$RemoteDir'"
if (-not $?) { throw "ssh mkdir failed" }

Write-Host "==> SCP: docker-compose.prod.yml -> ${Remote}:$RemoteCompose"
& scp @SshOpts $ComposeProd "${Remote}:${RemoteCompose}"
if (-not $?) { throw "scp compose failed" }

Write-Host "==> SCP: $(Split-Path -Leaf $ImageTarGz) (~${gzMb} MB - upload time depends on your uplink)"
& scp @SshOpts $ImageTarGz "${Remote}:${RemoteTarGz}"
if (-not $?) { throw "scp image failed" }

if ($SyncDatabase) {
    Write-Host "==> SCP: database config + published CSVs only (no legacy_scrape / work dir)"
    $databasePath = Join-Path $RepoRoot "database"
    $remoteDb = "${Remote}:${RemoteDir}/database"
    & ssh @SshOpts $Remote "mkdir -p '$RemoteDir/database/data' '$RemoteDir/database/relational_csv' '$RemoteDir/database/config'"
    if (-not $?) { throw "ssh mkdir database failed" }
    & scp @SshOpts '-r' (Join-Path $databasePath "relational_csv") "${remoteDb}/"
    if (-not $?) { throw "scp database/relational_csv failed" }
    & scp @SshOpts '-r' (Join-Path $databasePath "config") "${remoteDb}/"
    if (-not $?) { throw "scp database/config failed" }
    $dataFiles = Get-ChildItem -LiteralPath (Join-Path $databasePath "data") -File -ErrorAction SilentlyContinue
    if ($dataFiles) {
        foreach ($f in $dataFiles) {
            & scp @SshOpts $f.FullName "${remoteDb}/data/"
            if (-not $?) { throw "scp database/data/$($f.Name) failed" }
        }
        Write-Host "    uploaded $($dataFiles.Count) file(s) from database/data/"
    } else {
        Write-Host "    warning: no files in database/data/ to upload"
    }
} else {
    Write-Host "==> skipping database sync (use -SyncDatabase when published CSV data changed)"
}

Write-Host "==> remote: docker load + compose up + health (health loop up to ~60s)"
$remoteScript = @'
set -e
cd '__REMOTE_DIR__'
# CSVs are bind-mounted read-only; ensure UID 1000 in the container can traverse/read.
chmod -R a+rX ./database 2>/dev/null || true
docker load -i bowlyzer-image.tar.gz
rm -f bowlyzer-image.tar.gz bowlyzer-image.tar
rm -f /root/bowlyzer-image.tar /root/bowlyzer-image.tar.gz '__REMOTE_DIR__/../bowlyzer-image.tar' '__REMOTE_DIR__/../bowlyzer-image.tar.gz' 2>/dev/null || true
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker image prune -f >/dev/null 2>&1 || true
docker compose -f docker-compose.prod.yml ps
echo -n 'health /liga: '
HTTP_CODE=""
for i in {1..30}; do
  HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/liga 2>/dev/null || true)
  if [ "$HTTP_CODE" = "200" ]; then
    echo "$HTTP_CODE"
    HEALTH_OK=1
    break
  fi
  sleep 2
done
if [ "${HEALTH_OK:-0}" -ne 1 ]; then
  echo "timeout (waited ~60s; last code '${HTTP_CODE:-000}') - check: docker compose -f docker-compose.prod.yml logs --tail 40 bowlyzer"
fi
df -h /
'@ -replace '__REMOTE_DIR__', ($RemoteDir -replace "'", "'\''") -replace "`r`n", "`n" -replace "`r", ""

Invoke-SshBashScript -ScriptBody $remoteScript -SshTarget $Remote -SshOpts $SshOpts

Write-Host ""
Write-Host "==> deploy finished"
Write-Host "    Site (if nginx proxies to :8080): https://your-domain"
Write-Host "    Direct: http://${RemoteHost}:8080/liga"
Write-Host "    Logs:   ssh $Remote 'cd $RemoteDir && docker compose -f docker-compose.prod.yml logs -f --tail 50'"
