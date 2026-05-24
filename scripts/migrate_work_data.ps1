#Requires -Version 5.1
<#
.SYNOPSIS
  Move pipeline intermediate data from database/data to the external work directory.

.DESCRIPTION
  Default target: C:\tmp\bowlyzer\data (override with BOWLYZER_WORK_DATA_DIR).
  Published runtime CSVs (league_results_merged.csv, player hybrid, tournament configs)
  stay in database/data unless you set BOWLYZER_DATA_DIR.

.EXAMPLE
  cd C:\Users\cfell\repositories\bowlyzer_deploy
  .\scripts\migrate_work_data.ps1
  .\scripts\migrate_work_data.ps1 -WhatIf
#>
param(
    [switch] $WhatIf
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RepoData = Join-Path $RepoRoot "database\data"

$WorkDir = $env:BOWLYZER_WORK_DATA_DIR
if ([string]::IsNullOrWhiteSpace($WorkDir)) {
    $WorkDir = "C:\tmp\bowlyzer\data"
}
$WorkDir = [System.IO.Path]::GetFullPath($WorkDir)

$DirsToMove = @("legacy_scrape", "tmp")
$FilesToMove = @(
    "extract_excel_analysis_log.json",
    "historical_league_results.csv",
    "unique_team_names_after_merge.csv",
    "league_results_merged_duplicates.csv",
    "league_results_merged_duplicates_non_exact.csv",
    "bowling_ergebnisse.csv",
    "bowling_ergebnisse_ohne_punkte.csv",
    "bowling_ergebnisse_real.csv",
    "bowling_ergebnisse_real_from_bowlingbayern.csv",
    "bowling_ergebnisse_reconstructed.csv",
    "bowling_ergebnisse_reconstructed_clean.csv",
    "bowling_ergebnisse_test_errors.csv",
    "bowling_ergebnisse_test_with_errors.csv"
)

function Move-WorkItem {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Source,
        [Parameter(Mandatory = $true)]
        [string] $Dest
    )
    if ($WhatIf) {
        Write-Host "WhatIf: move $Source -> $Dest"
        return
    }
    if (Test-Path -LiteralPath $Dest) {
        Write-Warning "Skip - destination already exists: $Dest"
        return
    }
    Move-Item -LiteralPath $Source -Destination $Dest
}

Write-Host "Work directory: $WorkDir"
if (-not $WhatIf) {
    New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
}

foreach ($name in $DirsToMove) {
    $src = Join-Path $RepoData $name
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $dst = Join-Path $WorkDir $name
    Move-WorkItem -Source $src -Dest $dst
    if (-not $WhatIf) { Write-Host "Moved directory $name" }
}

foreach ($name in $FilesToMove) {
    $src = Join-Path $RepoData $name
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $dst = Join-Path $WorkDir $name
    Move-WorkItem -Source $src -Dest $dst
    if (-not $WhatIf) { Write-Host "Moved file $name" }
}

Write-Host ""
Write-Host "Done. Set permanently (PowerShell profile or deploy.config.ps1):"
Write-Host ('  $env:BOWLYZER_WORK_DATA_DIR = "{0}"' -f $WorkDir)
