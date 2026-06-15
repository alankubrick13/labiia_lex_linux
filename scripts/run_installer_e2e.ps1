[CmdletBinding()]
param(
    [string]$SetupPath = "",
    [string]$ReportJson = ""
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$installerDist = Join-Path $root "installer\dist"
if (-not $SetupPath) {
    $setup = Get-ChildItem $installerDist -Filter "labiia_lex-Setup-x64-*.exe" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $setup) {
        throw "Setup nao encontrado em $installerDist"
    }
    $SetupPath = $setup.FullName
}
else {
    $SetupPath = (Resolve-Path $SetupPath).Path
}

if (-not $ReportJson) {
    $ReportJson = Join-Path $installerDist ("installer_e2e_report_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
}

$report = [ordered]@{
    timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
    setup_path = $SetupPath
    ok = $false
    installer_exit_code = -1
    installer_log = ""
    app_dir = ""
    app_exe = ""
    app_dir_exists = $false
    app_exe_exists = $false
    data_dir = ""
    logs_dir = ""
    data_dir_exists = $false
    logs_dir_exists = $false
    r_install_state = $null
    post_install_check = $null
    installed_self_test = $null
    errors = @()
}

function Add-ErrorLine {
    param([string]$Message)
    $report.errors = @($report.errors) + @($Message)
}

function Save-Report {
    $report.ok = (@($report.errors).Count -eq 0)
    $reportDir = Split-Path -Parent $ReportJson
    if ($reportDir) {
        New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
    }
    $report | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 $ReportJson
}

try {
    if (-not (Test-Path $SetupPath)) {
        throw "Setup nao encontrado: $SetupPath"
    }

    $installerLog = Join-Path $installerDist ("installer_run_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
    $report.installer_log = $installerLog

    Write-Host "[e2e] Executando instalador silencioso..."
    $proc = Start-Process -FilePath $SetupPath `
        -ArgumentList @("/SP-", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$installerLog") `
        -PassThru
    $proc.WaitForExit()
    $report.installer_exit_code = [int]$proc.ExitCode
    if ($proc.ExitCode -ne 0) {
        Add-ErrorLine "installer_exit_code_$($proc.ExitCode)"
    }

    $appDir = Join-Path $env:LOCALAPPDATA "Programs\LabiiaLex"
    $appExe = Join-Path $appDir "LabiiaLex.exe"
    $dataDir = Join-Path $env:LOCALAPPDATA "LabiiaLex"
    $logsDir = Join-Path $dataDir "logs"

    $report.app_dir = $appDir
    $report.app_exe = $appExe
    $report.data_dir = $dataDir
    $report.logs_dir = $logsDir

    $report.app_dir_exists = [bool](Test-Path $appDir)
    $report.app_exe_exists = [bool](Test-Path $appExe)
    $report.data_dir_exists = [bool](Test-Path $dataDir)
    $report.logs_dir_exists = [bool](Test-Path $logsDir)

    if (-not $report.app_dir_exists) { Add-ErrorLine "app_dir_missing" }
    if (-not $report.app_exe_exists) { Add-ErrorLine "app_exe_missing" }
    if (-not $report.data_dir_exists) { Add-ErrorLine "data_dir_missing" }
    if (-not $report.logs_dir_exists) { Add-ErrorLine "logs_dir_missing" }

    $statePath = Join-Path $dataDir "r_install_state.json"
    if (Test-Path $statePath) {
        try {
            $state = Get-Content $statePath -Raw | ConvertFrom-Json
            $report.r_install_state = $state
            if (-not $state.core_success) { Add-ErrorLine "r_core_install_failed" }
            if (-not $state.critical_load_success) { Add-ErrorLine "r_critical_load_failed" }
            if (-not $state.functional_smoke_success) { Add-ErrorLine "r_functional_smoke_failed" }
            if ($state.ggwordcloud_shape_smoke -and -not $state.ggwordcloud_shape_smoke.ok) {
                Add-ErrorLine "ggwordcloud_shape_smoke_failed"
            }
        }
        catch {
            Add-ErrorLine "r_install_state_parse_error"
        }
    }
    else {
        Add-ErrorLine "r_install_state_missing"
    }

    $postInstallJson = Join-Path $logsDir "post_install_check.json"
    if (Test-Path $postInstallJson) {
        try {
            $post = Get-Content $postInstallJson -Raw | ConvertFrom-Json
            $report.post_install_check = $post
            if (-not $post.ok) {
                Add-ErrorLine "post_install_check_failed"
            }
            $postImporterBackendsOk = $null
            if ($null -ne $post.importer_backends -and $null -ne $post.importer_backends.ok) {
                $postImporterBackendsOk = [bool]$post.importer_backends.ok
            }
            elseif ($null -ne $post.importer_backends_ok) {
                $postImporterBackendsOk = [bool]$post.importer_backends_ok
            }
            if ($postImporterBackendsOk -ne $true) {
                Add-ErrorLine "post_install_check_importer_backends_failed"
            }
        }
        catch {
            Add-ErrorLine "post_install_check_parse_error"
        }
    }
    else {
        Add-ErrorLine "post_install_check_missing"
    }

    if (Test-Path $appExe) {
        $selfTestOut = Join-Path $logsDir ("manual_installed_self_test_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
        Write-Host "[e2e] Executando self-test do app instalado..."
        $oldProfile = [System.Environment]::GetEnvironmentVariable("LEXIANALYST_SELF_TEST_PROFILE", "Process")
        [System.Environment]::SetEnvironmentVariable("LEXIANALYST_SELF_TEST_PROFILE", "full", "Process")
        try {
            $selfProc = Start-Process -FilePath $appExe -ArgumentList @("--self-test", "--json-out", $selfTestOut) -PassThru -WorkingDirectory $appDir
            $selfProc.WaitForExit()
        }
        finally {
            [System.Environment]::SetEnvironmentVariable("LEXIANALYST_SELF_TEST_PROFILE", $oldProfile, "Process")
        }

        if (-not (Test-Path $selfTestOut)) {
            Add-ErrorLine "installed_self_test_missing"
        }
        else {
            try {
                $selfPayload = Get-Content $selfTestOut -Raw | ConvertFrom-Json
                $report.installed_self_test = $selfPayload
                if (-not $selfPayload.ok) { Add-ErrorLine "installed_self_test_failed" }
                if (-not $selfPayload.importer_backends_ok) { Add-ErrorLine "installed_self_test_importer_backends_failed" }
                if (-not $selfPayload.wordcloud_ok) { Add-ErrorLine "installed_self_test_wordcloud_failed" }
                if ($selfPayload.wordcloud_shape_hashes) {
                    if ($selfPayload.wordcloud_shape_hashes.circle -eq $selfPayload.wordcloud_shape_hashes.star) {
                        Add-ErrorLine "installed_self_test_wordcloud_shape_not_applied"
                    }
                }
                else {
                    Add-ErrorLine "installed_self_test_wordcloud_hashes_missing"
                }
            }
            catch {
                Add-ErrorLine "installed_self_test_parse_error"
            }
        }
    }
}
catch {
    Add-ErrorLine ("unexpected_error: " + $_.Exception.Message)
}
finally {
    Save-Report
    Write-Host "[e2e] Relatorio: $ReportJson"
    if ($report.ok) {
        Write-Host "[e2e] OK"
        exit 0
    }
    Write-Host "[e2e] FAIL"
    exit 1
}
