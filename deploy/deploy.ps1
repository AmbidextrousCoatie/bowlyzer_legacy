#Requires -Version 5.1
<#
.SYNOPSIS
  Build Bowl-A-Lyzer locally on Windows and deploy to the VPS via docker save/scp/ssh.

.DESCRIPTION
  1. docker compose build (repo root)
  2. Tag image as bowlyzer:release
  3. docker save -> deploy/artifacts/bowlyzer-image.tar (default; no gzip)
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
  Upload database config and published Parquet/JSON under database/data (not huge CSVs).

.PARAMETER SyncDatabaseCsv
  With -SyncDatabase, also upload *.csv from database/data (legacy; much larger).

.PARAMETER SyncCache
  Upload .cache/league/ as league-cache.tar.gz (one scp, extract on VPS). Requires compose mount of ./.cache/league.

.PARAMETER DataOnly
  Skip image build/upload/load. Upload published database files and restart the container only.
  Implies -SyncDatabase. Does not require local Docker.

.PARAMETER SkipUpload
  Only build and save image locally (no scp/ssh).

.PARAMETER ZipContainerImage
  Gzip the docker save tar before scp (legacy). Default: uncompressed bowlyzer-image.tar
  (faster on small VPS; layer tars rarely shrink much).

.EXAMPLE
  cd C:\Users\cfell\repositories\bowlyzer_deploy
  Copy-Item deploy\deploy.config.example.ps1 deploy\deploy.config.ps1
  # edit deploy.config.ps1
  .\deploy\deploy.ps1

.EXAMPLE
  .\deploy\deploy.ps1 -RemoteHost 212.227.57.223 -SyncDatabase

.EXAMPLE
  .\deploy\deploy-data.ps1
  # same as: .\deploy\deploy.ps1 -DataOnly
#>
[CmdletBinding()]
param(
    [string] $RemoteHost,
    [string] $RemoteUser = "bowlyzer",
    [string] $RemoteDir = "/home/bowlyzer/bowlyzer",
    [string] $ReleaseImage = "bowlyzer:release",
    [switch] $SkipBuild,
    [switch] $SyncDatabase,
    [switch] $SyncDatabaseCsv,
    [switch] $SyncCache,
    [switch] $DataOnly,
    [switch] $SkipUpload,
    [switch] $ZipContainerImage
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

function Join-BashScript {
    param([Parameter(Mandatory = $true)][string[]] $Lines)
    (($Lines | Where-Object { $null -ne $_ }) -join "`n") -replace "`r", ""
}

function Get-RemoteHealthCheckLines {
    @(
        'echo -n "health /liga: "'
        'HTTP_CODE=""'
        'for i in {1..30}; do'
        '  HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/liga 2>/dev/null || true)'
        '  if [ "$HTTP_CODE" = "200" ]; then'
        '    echo "$HTTP_CODE"'
        '    HEALTH_OK=1'
        '    break'
        '  fi'
        '  sleep 2'
        'done'
        'if [ "${HEALTH_OK:-0}" -ne 1 ]; then'
        '  echo "timeout (waited ~60s; last code ${HTTP_CODE:-000}) - check: docker compose -f docker-compose.prod.yml logs --tail 40 bowlyzer"'
        'fi'
    )
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

function Sync-RemoteDatabase {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RepoRoot,
        [Parameter(Mandatory = $true)]
        [string] $Remote,
        [Parameter(Mandatory = $true)]
        [string] $RemoteDir,
        [string[]] $SshOpts,
        [switch] $IncludeCsv
    )
    Write-Host '==> SCP: database config + published Parquet/JSON (+ small published CSVs)'
    if ($IncludeCsv) {
        Write-Host '    (-SyncDatabaseCsv: also uploading *.csv from database/data/)'
    }
    $databasePath = Join-Path $RepoRoot "database"
    $remoteDb = "${Remote}:${RemoteDir}/database"
    & ssh @SshOpts $Remote "mkdir -p '$RemoteDir/database/data' '$RemoteDir/database/relational_csv' '$RemoteDir/database/config'"
    if (-not $?) { throw "ssh mkdir database failed" }
    & scp @SshOpts '-r' (Join-Path $databasePath "relational_csv") "${remoteDb}/"
    if (-not $?) { throw "scp database/relational_csv failed" }
    & scp @SshOpts '-r' (Join-Path $databasePath "config") "${remoteDb}/"
    if (-not $?) { throw "scp database/config failed" }
    $publishedCsvAllowlist = @(
        'tournament_manual_postprocessed.csv'
    )
    $dataFiles = Get-ChildItem -LiteralPath (Join-Path $databasePath "data") -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Extension -in '.parquet', '.json' -or
            ($IncludeCsv -and $_.Extension -eq '.csv') -or
            ($_.Extension -eq '.csv' -and $publishedCsvAllowlist -contains $_.Name)
        }
    if ($dataFiles) {
        foreach ($f in $dataFiles) {
            & scp @SshOpts $f.FullName "${remoteDb}/data/"
            if (-not $?) { throw "scp database/data/$($f.Name) failed" }
        }
        Write-Host ('    uploaded {0} file(s) from database/data/' -f $dataFiles.Count)
    } else {
        Write-Host '    warning: no Parquet/JSON (or CSV with -SyncDatabaseCsv) in database/data/ to upload'
    }
}

function Sync-RemoteLeagueCache {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RepoRoot,
        [Parameter(Mandatory = $true)]
        [string] $Remote,
        [Parameter(Mandatory = $true)]
        [string] $RemoteDir,
        [string[]] $SshOpts
    )
    Require-Command tar
    $localCache = Join-Path $RepoRoot ".cache\league"
    if (-not (Test-Path -LiteralPath $localCache)) {
        Write-Host ('    warning: {0} not found - run warm_league_cache.py or rebuild_league_caches.py first' -f $localCache)
        return
    }
    $files = @(Get-ChildItem -LiteralPath $localCache -Recurse -File -ErrorAction SilentlyContinue)
    if (-not $files.Count) {
        Write-Host "    warning: .cache/league is empty; nothing to upload"
        return
    }
    $bytes = ($files | Measure-Object -Property Length -Sum).Sum
    $mb = [math]::Round($bytes / 1MB, 1)

    $artifactsDir = Join-Path $PSScriptRoot "artifacts"
    if (-not (Test-Path -LiteralPath $artifactsDir)) {
        New-Item -ItemType Directory -Path $artifactsDir -Force | Out-Null
    }
    $cacheArchive = Join-Path $artifactsDir "league-cache.tar.gz"
    $cacheParent = Join-Path $RepoRoot ".cache"
    if (Test-Path -LiteralPath $cacheArchive) {
        Remove-Item -LiteralPath $cacheArchive -Force
    }

    Write-Host ('==> pack .cache/league ({0} files, ~{1} MB) -> tar.gz' -f $files.Count, $mb)
    & tar -czf $cacheArchive -C $cacheParent league
    if (-not $?) { throw "tar league-cache failed" }

    $archiveMb = [math]::Round((Get-Item -LiteralPath $cacheArchive).Length / 1MB, 1)
    $remoteArchive = "$RemoteDir/league-cache.tar.gz"
    Write-Host ('==> SCP: league-cache.tar.gz (~{0} MB, one file)' -f $archiveMb)
    & scp @SshOpts $cacheArchive "${Remote}:${remoteArchive}"
    if (-not $?) { throw "scp league-cache.tar.gz failed" }

    Write-Host "==> remote: extract league cache archive"
    $extractScript = Join-BashScript @(
        'set -e'
        "cd $RemoteDir"
        'mkdir -p .cache .cache/league-runtime'
        'rm -rf .cache/league'
        'tar -xzf league-cache.tar.gz -C .cache'
        'rm -f league-cache.tar.gz'
        'chmod -R a+rX .cache/league'
        '# Fresh shipped cache: drop stale runtime overlay (orphan hashes are harmless but waste disk).'
        'find .cache/league-runtime -mindepth 1 -delete 2>/dev/null || rm -rf .cache/league-runtime/*'
        'chmod -R u+rwX,go+rX .cache/league-runtime 2>/dev/null || true'
    )
    Invoke-SshBashScript -ScriptBody $extractScript -SshTarget $Remote -SshOpts $SshOpts
    Write-Host "    league cache extracted to $RemoteDir/.cache/league"
}

function Invoke-RemoteContainerRestart {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RemoteDir,
        [Parameter(Mandatory = $true)]
        [string] $Remote,
        [string[]] $SshOpts,
        [switch] $Recreate
    )
    $upLine = if ($Recreate) {
        'docker compose -f docker-compose.prod.yml up -d --remove-orphans --force-recreate'
    } else {
        'docker compose -f docker-compose.prod.yml restart bowlyzer'
    }
    $remoteScript = Join-BashScript ( @(
        'set -e'
        "cd $RemoteDir"
        'mkdir -p .cache/league-runtime /home/bowlyzer/logs/analytics'
        'chmod -R a+rX ./database/data ./database/relational_csv ./database/config ./.cache/league 2>/dev/null || true'
        'chmod -R u+rwX,go+rX ./.cache/league-runtime /home/bowlyzer/logs/analytics 2>/dev/null || true'
        $upLine
        'docker compose -f docker-compose.prod.yml ps'
    ) + (Get-RemoteHealthCheckLines) )
    Invoke-SshBashScript -ScriptBody $remoteScript -SshTarget $Remote -SshOpts $SshOpts
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
    Write-Host @'

  This script builds the image on your PC and needs a working local Docker daemon.
  On Windows with Docker Desktop:
    1. Start Docker Desktop from the Start menu.
    2. Wait until it shows "Engine running" (whale icon steady).
    3. Run: docker version
       Client AND Server sections should both print - if Server is missing, the daemon is down.

  Then run this deploy script again.

'@ -ForegroundColor Gray
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
    # Optional key — bracket access avoids StrictMode PropertyNotFound on older deploy.config.ps1
    if (($cfg['ZipContainerImage'] -eq $true) -and -not $PSBoundParameters.ContainsKey("ZipContainerImage")) {
        $ZipContainerImage = $true
    }
}

# Windows PowerShell does not treat '--SwitchName' as a switch; the first '--…' token is often bound as
# positional value for the first [string] parameter (-RemoteHost). Recognize and fix common mistakes.
if ($RemoteHost -match '^--(.+)$') {
    $tok = $Matches[1]
    $handled = $false
    switch -Regex ($tok) {
        '(?i)^skipbuild$' {
            if (-not $SkipBuild) {
                Write-Host ('==> treating {0} as -SkipBuild; on Windows use -SkipBuild, not Unix-style --flags' -f $RemoteHost)
            }
            $SkipBuild = $true
            $handled = $true
        }
        '(?i)^syncdatabase$' {
            $SyncDatabase = $true
            $handled = $true
        }
        '(?i)^synccache$' {
            $SyncCache = $true
            $handled = $true
        }
        '(?i)^skipupload$' {
            $SkipUpload = $true
            $handled = $true
        }
        '(?i)^dataonly$' {
            $DataOnly = $true
            $handled = $true
        }
        '(?i)^zipcontainerimage$' {
            $ZipContainerImage = $true
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
    throw @'
RemoteHost is required. Either:
  - Copy deploy\deploy.config.example.ps1 to deploy\deploy.config.ps1 and set RemoteHost, or
  - Pass -RemoteHost <ip-or-hostname>
'@
}

if ($DataOnly) {
    $SyncDatabase = $true
}

if (-not $DataOnly) {
    Require-Command "docker"
    Exit-IfDockerDaemonUnreachable
}
if (-not $SkipUpload) {
    Require-Command "ssh"
    Require-Command "scp"
}

$SshOpts = @(
    '-o', 'ConnectTimeout=45'
    '-o', 'ServerAliveInterval=10'
    '-o', 'ServerAliveCountMax=3'
)

if ($DataOnly -and -not $SkipUpload) {
    $Remote = "${RemoteUser}@${RemoteHost}"
    Write-Host "==> data-only deploy (no image build/upload)"
    Write-Host ('    ({0})' -f $Remote)
    & ssh @SshOpts $Remote "mkdir -p '$RemoteDir'"
    if (-not $?) { throw "ssh mkdir failed" }
    Sync-RemoteDatabase -RepoRoot $RepoRoot -Remote $Remote -RemoteDir $RemoteDir -SshOpts $SshOpts -IncludeCsv:$SyncDatabaseCsv
    if ($SyncCache) {
        Sync-RemoteLeagueCache -RepoRoot $RepoRoot -Remote $Remote -RemoteDir $RemoteDir -SshOpts $SshOpts
    }
    Write-Host '==> remote: restart container + health'
    if ($SyncCache) {
        Invoke-RemoteContainerRestart -RemoteDir $RemoteDir -Remote $Remote -SshOpts $SshOpts -Recreate
    } else {
        Invoke-RemoteContainerRestart -RemoteDir $RemoteDir -Remote $Remote -SshOpts $SshOpts
    }
    Write-Host ""
    Write-Host "==> data deploy finished"
    Write-Host '    Site: https://www.bowlyzer.online (nginx must be running)'
    Write-Host ('    Logs: ssh {0}; then: cd {1}; docker compose -f docker-compose.prod.yml logs --tail 50 bowlyzer' -f $Remote, $RemoteDir)
    exit 0
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

if (Test-Path $ImageTar) { Remove-Item -Force $ImageTar }
if (Test-Path $ImageTarGz) { Remove-Item -Force $ImageTarGz }
docker save $ReleaseImage -o $ImageTar
if ($LASTEXITCODE -ne 0) { throw "docker save failed" }
$rawMb = [math]::Round((Get-Item $ImageTar).Length / 1MB, 1)

if ($ZipContainerImage) {
    Write-Host "==> docker save -> gzip -> $(Split-Path -Leaf $ImageTarGz)"
    Write-Host ('    uncompressed tar {0} MB - compressing (gzip)...' -f $rawMb)
    Write-Host '    (gzip is CPU-bound; 10-40s silence here is normal for this size.)'
    Compress-FileGzip -SourcePath $ImageTar -DestinationPath $ImageTarGz
    Remove-Item -Force $ImageTar
    $ImageArtifact = $ImageTarGz
    $artifactMb = [math]::Round((Get-Item $ImageArtifact).Length / 1MB, 1)
    $pct = if ($rawMb -gt 0) { [math]::Round(100.0 * $artifactMb / $rawMb, 0) } else { 0 }
    Write-Host ('    artifact {0} MB (~{1}% of tar)' -f $artifactMb, $pct)
} else {
    Write-Host "==> docker save -> $(Split-Path -Leaf $ImageTar) (uncompressed)"
    Write-Host ('    artifact {0} MB' -f $rawMb)
    $ImageArtifact = $ImageTar
    $artifactMb = $rawMb
}

if ($SkipUpload) {
    Write-Host "==> SkipUpload set; done."
    exit 0
}

$Remote = "${RemoteUser}@${RemoteHost}"
$RemoteCompose = "$RemoteDir/docker-compose.prod.yml"
$RemoteImageName = if ($ZipContainerImage) { 'bowlyzer-image.tar.gz' } else { 'bowlyzer-image.tar' }
$RemoteImagePath = "$RemoteDir/$RemoteImageName"

Write-Host "==> SSH: ensure deploy directory on VPS"
Write-Host ('    ({0} : mkdir -p {1})' -f $Remote, $RemoteDir)
Write-Host '    (This step can take 10-60s: DNS, first key auth, or password prompt with no extra lines until it returns.)'
& ssh @SshOpts $Remote "mkdir -p '$RemoteDir'"
if (-not $?) { throw "ssh mkdir failed" }

Write-Host "==> SCP: docker-compose.prod.yml -> ${Remote}:$RemoteCompose"
& scp @SshOpts $ComposeProd "${Remote}:${RemoteCompose}"
if (-not $?) { throw "scp compose failed" }

Write-Host ('==> SCP: {0} (~{1} MB - upload time depends on your uplink)' -f (Split-Path -Leaf $ImageArtifact), $artifactMb)
& scp @SshOpts $ImageArtifact "${Remote}:${RemoteImagePath}"
if (-not $?) { throw "scp image failed" }

if ($SyncDatabase) {
    Sync-RemoteDatabase -RepoRoot $RepoRoot -Remote $Remote -RemoteDir $RemoteDir -SshOpts $SshOpts -IncludeCsv:$SyncDatabaseCsv
} else {
    Write-Host "==> skipping database sync (use -SyncDatabase when published data changed)"
}

if ($SyncCache) {
    Sync-RemoteLeagueCache -RepoRoot $RepoRoot -Remote $Remote -RemoteDir $RemoteDir -SshOpts $SshOpts
} else {
    Write-Host "==> skipping league cache sync (use -SyncCache after warm_league_cache.py)"
}

Write-Host '==> remote: docker load + compose up + health (health loop up to ~60s)'
$composeUpLine = if ($SyncCache) {
    'docker compose -f docker-compose.prod.yml up -d --remove-orphans --force-recreate'
} else {
    'docker compose -f docker-compose.prod.yml up -d --remove-orphans'
}
$remoteScript = Join-BashScript ( @(
    'set -e'
    "cd $RemoteDir"
    '# Published data bind-mounts; shipped cache ro, league-runtime rw (UID 1000).'
    'mkdir -p .cache/league-runtime'
    'mkdir -p /home/bowlyzer/logs/analytics'
    'chmod -R u+rwX,go+rX /home/bowlyzer/logs/analytics 2>/dev/null || true'
    'chmod -R a+rX ./database/data ./database/relational_csv ./database/config ./.cache/league 2>/dev/null || true'
    'chmod -R u+rwX,go+rX ./.cache/league-runtime 2>/dev/null || true'
    ('docker load -i {0}' -f $RemoteImageName)
    'rm -f bowlyzer-image.tar.gz bowlyzer-image.tar'
    ('rm -f /root/bowlyzer-image.tar /root/bowlyzer-image.tar.gz {0}/../bowlyzer-image.tar {0}/../bowlyzer-image.tar.gz 2>/dev/null || true' -f $RemoteDir)
    $composeUpLine
    'docker image prune -f >/dev/null 2>&1 || true'
    'docker compose -f docker-compose.prod.yml ps'
) + (Get-RemoteHealthCheckLines) + @('df -h /') )

Invoke-SshBashScript -ScriptBody $remoteScript -SshTarget $Remote -SshOpts $SshOpts

Write-Host ""
Write-Host "==> deploy finished"
Write-Host '    Site (if nginx proxies to :8080): https://your-domain'
Write-Host ('    Direct: http://{0}:8080/liga' -f $RemoteHost)
Write-Host ('    Logs:   ssh {0}; then: cd {1}; docker compose -f docker-compose.prod.yml logs -f --tail 50' -f $Remote, $RemoteDir)
