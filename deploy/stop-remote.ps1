#Requires -Version 5.1
<#
.SYNOPSIS
  Stop Bowl-A-Lyzer on the VPS (free RAM before redeploy or when the host is struggling).

.EXAMPLE
  .\deploy\stop-remote.ps1
  .\deploy\stop-remote.ps1 -PruneImages
#>
[CmdletBinding()]
param(
    [string] $RemoteHost,
    [string] $RemoteUser = "bowlyzer",
    [string] $RemoteDir = "/home/bowlyzer/bowlyzer",
    [switch] $PruneImages
)

$ErrorActionPreference = "Stop"

function Invoke-SshBashScript {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ScriptBody,
        [Parameter(Mandatory = $true)]
        [string] $SshTarget,
        [string[]] $SshOpts = @()
    )
    $clean = ($ScriptBody -replace "`r", "")
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("bowlyzer-stop-" + [Guid]::NewGuid().ToString() + ".sh")
    $outFile = Join-Path ([System.IO.Path]::GetTempPath()) ("bowlyzer-stop-" + [Guid]::NewGuid().ToString() + ".out")
    $errFile = Join-Path ([System.IO.Path]::GetTempPath()) ("bowlyzer-stop-" + [Guid]::NewGuid().ToString() + ".err")
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

$configPath = Join-Path $PSScriptRoot "deploy.config.ps1"
if (Test-Path $configPath) {
    $cfg = & $configPath
    if ($cfg.RemoteHost -and -not $PSBoundParameters.ContainsKey("RemoteHost")) { $RemoteHost = $cfg.RemoteHost }
    if ($cfg.RemoteUser -and -not $PSBoundParameters.ContainsKey("RemoteUser")) { $RemoteUser = $cfg.RemoteUser }
    if ($cfg.RemoteDir -and -not $PSBoundParameters.ContainsKey("RemoteDir")) { $RemoteDir = $cfg.RemoteDir }
}

if ([string]::IsNullOrWhiteSpace($RemoteHost)) {
    throw "RemoteHost required (deploy.config.ps1 or -RemoteHost)."
}

$SshOpts = @('-o', 'ConnectTimeout=45', '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=3')
$Remote = "${RemoteUser}@${RemoteHost}"
$remoteDirEsc = $RemoteDir -replace "'", "'\''"
$pruneLine = if ($PruneImages) { "docker image prune -f >/dev/null 2>&1 || true" } else { ":" }

$script = @"
set -e
cd '$remoteDirEsc'
echo '==> compose down'
docker compose -f docker-compose.prod.yml down --remove-orphans 2>/dev/null || true
echo '==> stop any bowlyzer containers'
docker ps -q --filter 'name=bowlyzer' | xargs -r docker stop -t 10 2>/dev/null || true
docker ps -aq --filter 'name=bowlyzer' | xargs -r docker rm -f 2>/dev/null || true
echo '==> optional image prune'
$pruneLine
echo '==> remaining containers'
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true
echo '==> memory'
free -h | head -n 2
echo '==> disk /'
df -h / | tail -n 1
"@

Write-Host "==> SSH stop on $Remote ($RemoteDir)"
Invoke-SshBashScript -ScriptBody $script -SshTarget $Remote -SshOpts $SshOpts
Write-Host ""
Write-Host "Stopped. Redeploy when ready:"
Write-Host "  .\deploy\deploy.ps1"
