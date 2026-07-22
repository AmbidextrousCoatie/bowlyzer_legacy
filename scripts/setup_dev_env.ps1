#Requires -Version 5.1
<#
.SYNOPSIS
  Bootstrap local Python dev environment (uv + .venv).

.DESCRIPTION
  Replaces the legacy root setup_venv.ps1 (pip + venv/). Uses uv per repo tooling contract.

.EXAMPLE
  cd C:\Users\cfell\repositories\bowlyzer_deploy
  .\scripts\setup_dev_env.ps1
#>
param(
    [switch] $Frozen
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is not on PATH. Install from https://docs.astral.sh/uv/ then retry."
}

Write-Host "==> uv sync in $RepoRoot"
if ($Frozen) {
    uv sync --frozen
} else {
    uv sync
}

Write-Host ""
Write-Host "Done. Activate with:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Run tests:"
Write-Host "  uv run pytest"
Write-Host "Run Flask (or use start.sh outside this script):"
Write-Host "  uv run python wsgi.py"
