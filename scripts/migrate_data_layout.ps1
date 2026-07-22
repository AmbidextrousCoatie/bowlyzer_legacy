#Requires -Version 5.1
<#
.SYNOPSIS
  Reorganize repo data layout: work intermediates, published CSV mirrors, clean data/.

.DESCRIPTION
  Moves files from the legacy scattered layout into:

    database/work/           — pipeline intermediates (gitignored)
    database/published_csv/  — CSV mirrors of published Parquet stems
    database/data/           — Parquet + runs/ + config JSON only

  Safe to re-run: skips when destination already exists.

.EXAMPLE
  cd C:\Users\cfell\repositories\bowlyzer_deploy
  .\scripts\migrate_data_layout.ps1 -WhatIf
  .\scripts\migrate_data_layout.ps1
#>
param(
    [switch] $WhatIf
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DataDir = Join-Path $RepoRoot "database\data"
$WorkDir = Join-Path $RepoRoot "database\work"
$PublishedCsvDir = Join-Path $RepoRoot "database\published_csv"
$LegacyInput = Join-Path $RepoRoot "database\input"
$LegacyPipeline = Join-Path $RepoRoot "database\pipeline"
$ExternalWork = if ($env:BOWLYZER_WORK_DATA_DIR) { $env:BOWLYZER_WORK_DATA_DIR } else { "C:\tmp\bowlyzer\data" }

$PublishedStems = @(
    "league_results_merged",
    "tournaments_postprocessed",
    "players_registry",
    "affiliation_index",
    "clubs_registry",
    "vereine_registry",
    "player_stats_merged_plus_tournaments"
)

$WorkSubdirs = @(
    "legacy_scrape",
    "league",
    "tournaments\input",
    "tournaments\staging",
    "gf",
    "pipeline\bowling_bayern\legacy_out",
    "pipeline\bowling_bayern\canonical",
    "raw",
    "audits",
    "tmp"
)

function Move-IfExists {
    param(
        [string] $Source,
        [string] $Dest
    )
    if (-not (Test-Path -LiteralPath $Source)) { return $false }
    $destDir = Split-Path -Parent $Dest
    if (-not (Test-Path -LiteralPath $destDir)) {
        if ($WhatIf) {
            Write-Host "WhatIf: mkdir $destDir"
        } else {
            New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        }
    }
    if (Test-Path -LiteralPath $Dest) {
        Write-Warning "Skip (dest exists): $Dest"
        return $false
    }
    if ($WhatIf) {
        Write-Host "WhatIf: move $Source -> $Dest"
    } else {
        Move-Item -LiteralPath $Source -Destination $Dest
        Write-Host "Moved: $(Split-Path -Leaf $Source) -> $Dest"
    }
    return $true
}

function Copy-TreeIfMissing {
    param(
        [string] $Source,
        [string] $Dest
    )
    if (-not (Test-Path -LiteralPath $Source)) { return }
    if (Test-Path -LiteralPath $Dest) {
        Write-Warning "Skip tree (dest exists): $Dest"
        return
    }
    if ($WhatIf) {
        Write-Host "WhatIf: copy-tree $Source -> $Dest"
    } else {
        Copy-Item -LiteralPath $Source -Destination $Dest -Recurse
        Write-Host "Copied tree: $Source -> $Dest"
    }
}

Write-Host "Repo:           $RepoRoot"
Write-Host "Work dir:       $WorkDir"
Write-Host "Published CSV:  $PublishedCsvDir"
Write-Host "External work:  $ExternalWork (legacy C:\tmp copy if present)"
Write-Host ""

if (-not $WhatIf) {
    foreach ($sub in $WorkSubdirs) {
        New-Item -ItemType Directory -Force -Path (Join-Path $WorkDir $sub) | Out-Null
    }
    New-Item -ItemType Directory -Force -Path $PublishedCsvDir | Out-Null
}

# 1) External work dir (old Windows default)
if (Test-Path -LiteralPath $ExternalWork) {
    Write-Host "==> Merging external work dir: $ExternalWork"
    Get-ChildItem -LiteralPath $ExternalWork -Force | ForEach-Object {
        Move-IfExists -Source $_.FullName -Dest (Join-Path $WorkDir $_.Name)
    }
}

# 2) GF exports: database/input/gf_tables_export -> database/work/gf
$gfLegacy = Join-Path $LegacyInput "gf_tables_export"
$gfWork = Join-Path $WorkDir "gf"
if (Test-Path -LiteralPath $gfLegacy) {
    Write-Host "==> GF exports"
    Get-ChildItem -LiteralPath $gfLegacy -File | ForEach-Object {
        Move-IfExists -Source $_.FullName -Dest (Join-Path $gfWork $_.Name)
    }
}

# 3) Pipeline outputs
Write-Host "==> Pipeline outputs"
$pipeLegacy = Join-Path $LegacyPipeline "bowling_bayern"
$pipeWork = Join-Path $WorkDir "pipeline\bowling_bayern"
if (Test-Path -LiteralPath $pipeLegacy) {
    Copy-TreeIfMissing -Source $pipeLegacy -Dest $pipeWork
}

# 4) Raw input (xlsx, liga csv) — keep tracked files, move to work/raw
Write-Host "==> Raw input snapshots"
if (Test-Path -LiteralPath $LegacyInput) {
    Get-ChildItem -LiteralPath $LegacyInput -File | ForEach-Object {
        Move-IfExists -Source $_.FullName -Dest (Join-Path (Join-Path $WorkDir "raw") $_.Name)
    }
    Get-ChildItem -LiteralPath $LegacyInput -Directory | Where-Object { $_.Name -ne "gf_tables_export" } | ForEach-Object {
        Copy-TreeIfMissing -Source $_.FullName -Dest (Join-Path (Join-Path $WorkDir "raw") $_.Name)
    }
}

# 5) Published CSV mirrors from database/data
Write-Host "==> Published CSV mirrors"
foreach ($stem in $PublishedStems) {
    $src = Join-Path $DataDir "$stem.csv"
    $dst = Join-Path $PublishedCsvDir "$stem.csv"
    Move-IfExists -Source $src -Dest $dst
}

# 6) Work intermediates still sitting in database/data
Write-Host "==> Intermediates in database/data"
$keepInData = @("runs", "README.md", "ARTIFACTS.md", "TEST_ERRORS_SUMMARY.md")
$keepPatterns = @("*.parquet", "*.json", "*.example.json")

Get-ChildItem -LiteralPath $DataDir -Force | ForEach-Object {
    if ($_.PSIsContainer) {
        if ($_.Name -eq "runs") { return }
        if ($_.Name -in @("legacy_scrape", "tmp")) {
            Move-IfExists -Source $_.FullName -Dest (Join-Path $WorkDir $_.Name)
        }
        return
    }
    if ($_.Name -in $keepInData) { return }
    $isKeep = $false
    foreach ($pat in $keepPatterns) {
        if ($_.Name -like $pat) { $isKeep = $true; break }
    }
    if ($isKeep) { return }

    $name = $_.Name
    if ($name -eq "tournament_manual_postprocessed.csv") {
        Move-IfExists -Source $_.FullName -Dest (Join-Path $WorkDir "tournaments\tournament_manual_postprocessed.csv")
        return
    }
    if ($name -match "^tournament_.*_postprocessed\.csv$" -or $name -match "^tournament_.*\.csv$") {
        Move-IfExists -Source $_.FullName -Dest (Join-Path (Join-Path $WorkDir "tournaments\staging") $name)
        return
    }
    if ($name -match "historical_league|duplicates|bowling_ergebnisse|unique_team|extract_excel|available_weeks|missing_weeks|league_weeks") {
        Move-IfExists -Source $_.FullName -Dest (Join-Path (Join-Path $WorkDir "league") $name)
        return
    }
    Move-IfExists -Source $_.FullName -Dest (Join-Path (Join-Path $WorkDir "tmp") $name)
}

# 7) Repo tmp/ scratch scripts output
$repoTmp = Join-Path $RepoRoot "tmp"
if (Test-Path -LiteralPath $repoTmp) {
    Write-Host "==> Repo tmp/ (outputs only; scripts stay)"
    Get-ChildItem -LiteralPath $repoTmp -File | Where-Object { $_.Extension -in @(".csv", ".txt", ".bak") } | ForEach-Object {
        Move-IfExists -Source $_.FullName -Dest (Join-Path (Join-Path $WorkDir "tmp") $_.Name)
    }
}

Write-Host ""
Write-Host "Done. Next steps:"
Write-Host "  1. Review git status (database/data should be mostly *.parquet + runs/ + *.json)"
Write-Host "  2. uv run python scripts/build_published_dataset.py --dry-run"
Write-Host "  3. Optional: git rm --cached for stray CSVs still tracked under database/data"
