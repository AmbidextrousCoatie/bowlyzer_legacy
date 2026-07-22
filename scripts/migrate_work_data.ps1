#Requires -Version 5.1
<#
.SYNOPSIS
  Move pipeline intermediate data from database/data to the external work directory.

.DESCRIPTION
  DEPRECATED: use migrate_data_layout.ps1 (repo-local database/work/).

  This script remains as a thin wrapper for older docs that referenced C:\tmp\bowlyzer\data.
#>
param(
    [switch] $WhatIf
)

Write-Warning "migrate_work_data.ps1 is deprecated. Running migrate_data_layout.ps1 instead."
& (Join-Path $PSScriptRoot "migrate_data_layout.ps1") @PSBoundParameters
