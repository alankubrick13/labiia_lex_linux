[CmdletBinding()]
param(
    [string]$AppVersion = "",
    [string]$PythonExe = "",
    [switch]$SkipPyInstaller,
    [switch]$SkipInno,
    [switch]$SkipSigning
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TargetScript = Join-Path $ScriptDir "build_release_installer.ps1"

if (-not (Test-Path $TargetScript)) {
    Write-Error "build_release_installer.ps1 nao encontrado em $TargetScript"
    exit 1
}

$InvokeArgs = @{}
if ($AppVersion) {
    $InvokeArgs["AppVersion"] = $AppVersion
}
if ($PythonExe) {
    $InvokeArgs["PythonExe"] = $PythonExe
}
if ($SkipPyInstaller) {
    $InvokeArgs["SkipPyInstaller"] = $true
}
if ($SkipInno) {
    $InvokeArgs["SkipInno"] = $true
}
if ($SkipSigning) {
    $InvokeArgs["SkipSigning"] = $true
}

& $TargetScript @InvokeArgs
$ExitCode = 0
if (Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue) {
    $ExitCode = $global:LASTEXITCODE
}
exit $ExitCode
