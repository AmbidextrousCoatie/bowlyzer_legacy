#Requires -Version 5.1
<#
.SYNOPSIS
  Upload published database files and restart Bowl-A-Lyzer on the VPS (no Docker image deploy).

.EXAMPLE
  .\deploy\deploy-data.ps1
  .\deploy\deploy-data.ps1 -SyncDatabaseCsv
  .\deploy\deploy-data.ps1 -SyncCache
#>
[CmdletBinding()]
param(
    [string] $RemoteHost,
    [string] $RemoteUser,
    [string] $RemoteDir,
    [switch] $SyncDatabaseCsv,
    [switch] $SyncCache
)

$deployArgs = @{ DataOnly = $true }
if ($PSBoundParameters.ContainsKey("RemoteHost")) { $deployArgs["RemoteHost"] = $RemoteHost }
if ($PSBoundParameters.ContainsKey("RemoteUser")) { $deployArgs["RemoteUser"] = $RemoteUser }
if ($PSBoundParameters.ContainsKey("RemoteDir")) { $deployArgs["RemoteDir"] = $RemoteDir }
if ($SyncDatabaseCsv) { $deployArgs["SyncDatabaseCsv"] = $true }
if ($SyncCache) { $deployArgs["SyncCache"] = $true }

& (Join-Path $PSScriptRoot "deploy.ps1") @deployArgs
