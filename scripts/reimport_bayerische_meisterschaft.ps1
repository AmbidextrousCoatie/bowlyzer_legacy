# Re-import Bayerische Meisterschaft XLSX files into gf_tournaments_2026__combined_postprocessed.csv
# and rebuild database/data/player_stats_merged_plus_tournaments.csv.
# Put one or more *.xlsx workbooks under: database/input/bayerische_meisterschaft_xlsx/
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$XlsxDir = Join-Path $Root "database\input\bayerische_meisterschaft_xlsx"
if (-not (Test-Path $XlsxDir)) {
    New-Item -ItemType Directory -Path $XlsxDir | Out-Null
}
$Args = @(
    "scripts/data/import_bayerische_meisterschaft_xlsx.py"
    "--xlsx-dir"
    $XlsxDir
    "--include-ko-finale"
)
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv run python @Args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 @Args
} else {
    & python @Args
}
