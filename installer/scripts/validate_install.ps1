[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath,
    [string]$JsonOut = "",
    [int]$TimeoutSec = 600,
    [string]$Profile = "full",
    [switch]$RunApp
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-SafeString {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) {
        return ""
    }
    return [string]$Value
}

function New-ValidationPayload {
    param(
        [bool]$Ok,
        [string[]]$Errors,
        [string]$ResolvedExePath,
        [string]$ProfileName,
        [int]$ReturnCode,
        [string]$SelfTestJsonPath,
        [string]$StdoutText,
        [object]$SelfTestPayload
    )

    return [ordered]@{
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        ok = $Ok
        exe_path = $ResolvedExePath
        profile = $ProfileName
        return_code = $ReturnCode
        self_test_json = $SelfTestJsonPath
        stdout = $StdoutText
        payload = $SelfTestPayload
        errors = @($Errors | Where-Object { $_ })
    }
}

function Write-ValidationResult {
    param(
        [hashtable]$Payload,
        [string]$OutputPath
    )

    $json = $Payload | ConvertTo-Json -Depth 10
    if ($OutputPath) {
        $jsonDir = Split-Path -Parent $OutputPath
        if ($jsonDir) {
            New-Item -ItemType Directory -Force -Path $jsonDir | Out-Null
        }
        Set-Content -LiteralPath $OutputPath -Value $json -Encoding UTF8
    }
    Write-Output $json
}

try {
    $resolvedExe = (Resolve-Path -LiteralPath $ExePath -ErrorAction Stop).Path
}
catch {
    $fallbackOutput = if ($JsonOut) { $JsonOut } else { Join-Path $env:TEMP "lexianalyst_validate_install.json" }
    $payload = New-ValidationPayload `
        -Ok $false `
        -Errors @("exe_not_found") `
        -ResolvedExePath $ExePath `
        -ProfileName $Profile `
        -ReturnCode 2 `
        -SelfTestJsonPath "" `
        -StdoutText "" `
        -SelfTestPayload $null
    Write-ValidationResult -Payload $payload -OutputPath $fallbackOutput
    exit 2
}

if (-not $JsonOut) {
    $JsonOut = Join-Path $env:TEMP "lexianalyst_validate_install.json"
}

$jsonDir = Split-Path -Parent $JsonOut
if (-not $jsonDir) {
    $jsonDir = $env:TEMP
}
$selfTestJson = Join-Path $jsonDir "lexianalyst_self_test.json"
if (Test-Path -LiteralPath $selfTestJson) {
    Remove-Item -LiteralPath $selfTestJson -Force -ErrorAction SilentlyContinue
}

$profileName = (Get-SafeString -Value $Profile).Trim().ToLowerInvariant()
if (-not $profileName) {
    $profileName = "full"
}

try {
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $resolvedExe
    $startInfo.Arguments = ('--self-test --json-out "{0}"' -f $selfTestJson)
    $startInfo.WorkingDirectory = Split-Path -Parent $resolvedExe
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.EnvironmentVariables["LEXIANALYST_SELF_TEST_PROFILE"] = $profileName

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $process.Start() | Out-Null

    if (-not $process.WaitForExit($TimeoutSec * 1000)) {
        try {
            $process.Kill()
        }
        catch {
        }

        $payload = New-ValidationPayload `
            -Ok $false `
            -Errors @("self_test_timeout") `
            -ResolvedExePath $resolvedExe `
            -ProfileName $profileName `
            -ReturnCode 1 `
            -SelfTestJsonPath $selfTestJson `
            -StdoutText "" `
            -SelfTestPayload $null
        Write-ValidationResult -Payload $payload -OutputPath $JsonOut
        exit 1
    }

    $stdout = ($process.StandardOutput.ReadToEnd() + [Environment]::NewLine + $process.StandardError.ReadToEnd()).Trim()
    $process.WaitForExit()
    $returnCode = $process.ExitCode
}
catch {
    $payload = New-ValidationPayload `
        -Ok $false `
        -Errors @("self_test_execution_failed", $_.Exception.Message) `
        -ResolvedExePath $resolvedExe `
        -ProfileName $profileName `
        -ReturnCode 3 `
        -SelfTestJsonPath $selfTestJson `
        -StdoutText "" `
        -SelfTestPayload $null
    Write-ValidationResult -Payload $payload -OutputPath $JsonOut
    exit 3
}

if (-not (Test-Path -LiteralPath $selfTestJson)) {
    $payload = New-ValidationPayload `
        -Ok $false `
        -Errors @("self_test_json_not_found") `
        -ResolvedExePath $resolvedExe `
        -ProfileName $profileName `
        -ReturnCode 1 `
        -SelfTestJsonPath $selfTestJson `
        -StdoutText $stdout `
        -SelfTestPayload $null
    Write-ValidationResult -Payload $payload -OutputPath $JsonOut
    exit 1
}

try {
    $selfTestPayload = Get-Content -LiteralPath $selfTestJson -Raw | ConvertFrom-Json
}
catch {
    $payload = New-ValidationPayload `
        -Ok $false `
        -Errors @("self_test_json_parse_error", $_.Exception.Message) `
        -ResolvedExePath $resolvedExe `
        -ProfileName $profileName `
        -ReturnCode 1 `
        -SelfTestJsonPath $selfTestJson `
        -StdoutText $stdout `
        -SelfTestPayload $null
    Write-ValidationResult -Payload $payload -OutputPath $JsonOut
    exit 1
}

$errors = @()
if ($selfTestPayload.errors) {
    $errors += @($selfTestPayload.errors)
}
if (-not $selfTestPayload.ok) {
    $errors += "self_test_reported_failure"
}

$payload = New-ValidationPayload `
    -Ok ([bool]$selfTestPayload.ok) `
    -Errors $errors `
    -ResolvedExePath $resolvedExe `
    -ProfileName $profileName `
    -ReturnCode ([int]$returnCode) `
    -SelfTestJsonPath $selfTestJson `
    -StdoutText $stdout `
    -SelfTestPayload $selfTestPayload
Write-ValidationResult -Payload $payload -OutputPath $JsonOut

if ($payload.ok -and $RunApp) {
    Start-Process -FilePath $resolvedExe -WorkingDirectory (Split-Path -Parent $resolvedExe) | Out-Null
}

if ($payload.ok) {
    exit 0
}
exit 1
