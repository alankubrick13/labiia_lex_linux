[CmdletBinding()]
param(
    [string]$JsonOut = "",
    [string]$CranUrl = "https://cloud.r-project.org",
    [string]$MinVersion = "4.0.0"
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

function Get-VersionToken {
    param([string]$Text)

    $safeText = Get-SafeString -Value $Text
    $match = [regex]::Match($safeText, "\d+(?:\.\d+){1,3}")
    if ($match.Success) {
        return $match.Value
    }
    return ""
}

function Convert-VersionParts {
    param([string]$Version)

    $parts = @()
    $safeVersion = Get-SafeString -Value $Version
    foreach ($part in ($safeVersion.Split("."))) {
        if ($part -match "^\d+$") {
            $parts += [int]$part
        }
        else {
            $parts += 0
        }
    }
    while ($parts.Count -lt 3) {
        $parts += 0
    }
    return $parts
}

function Test-MinVersion {
    param(
        [string]$CurrentVersion,
        [string]$RequiredVersion
    )

    if (-not $CurrentVersion) {
        return $false
    }

    $current = Convert-VersionParts -Version $CurrentVersion
    $required = Convert-VersionParts -Version $RequiredVersion

    for ($i = 0; $i -lt 3; $i++) {
        if ($current[$i] -gt $required[$i]) {
            return $true
        }
        if ($current[$i] -lt $required[$i]) {
            return $false
        }
    }
    return $true
}

function Get-VersionSortKey {
    param([string]$Version)

    $parts = Convert-VersionParts -Version $Version
    return "{0:D4}.{1:D4}.{2:D4}" -f $parts[0], $parts[1], $parts[2]
}

function Add-Candidate {
    param(
        [System.Collections.ArrayList]$Candidates,
        [hashtable]$Seen,
        [string]$Path,
        [string]$Source
    )

    if (-not $Path) {
        return
    }

    $trimmedPath = $Path.Trim('"').Trim()
    if (-not $trimmedPath) {
        return
    }

    $key = $trimmedPath.ToLowerInvariant()
    if ($Seen.ContainsKey($key)) {
        return
    }

    $Seen[$key] = $true
    [void]$Candidates.Add([ordered]@{
        path = $trimmedPath
        source = $Source
    })
}

function Add-RegistryCandidates {
    param(
        [System.Collections.ArrayList]$Candidates,
        [hashtable]$Seen
    )

    $roots = @(
        @{ hive = "HKLM"; path = "SOFTWARE\R-core\R" },
        @{ hive = "HKLM"; path = "SOFTWARE\R-core\R64" },
        @{ hive = "HKLM"; path = "SOFTWARE\WOW6432Node\R-core\R" },
        @{ hive = "HKCU"; path = "SOFTWARE\R-core\R" },
        @{ hive = "HKCU"; path = "SOFTWARE\R-core\R64" }
    )

    foreach ($root in $roots) {
        $registryPath = "Registry::{0}\{1}" -f $root.hive, $root.path
        try {
            $installPath = (Get-ItemProperty -Path $registryPath -Name InstallPath -ErrorAction Stop).InstallPath
            if ($installPath) {
                Add-Candidate -Candidates $Candidates -Seen $Seen -Path (Join-Path $installPath "bin\Rscript.exe") -Source ("registry:" + $root.hive + "\" + $root.path)
                Add-Candidate -Candidates $Candidates -Seen $Seen -Path (Join-Path $installPath "bin\x64\Rscript.exe") -Source ("registry:" + $root.hive + "\" + $root.path)
            }
        }
        catch {
            continue
        }
    }
}

function Add-RootCandidates {
    param(
        [System.Collections.ArrayList]$Candidates,
        [hashtable]$Seen,
        [string]$RootPath,
        [string]$SourcePrefix
    )

    if (-not $RootPath) {
        return
    }

    if (-not (Test-Path -LiteralPath $RootPath)) {
        return
    }

    $directories = @(Get-ChildItem -LiteralPath $RootPath -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "R-*" })
    $directories = $directories | Sort-Object Name -Descending
    foreach ($directory in $directories) {
        Add-Candidate -Candidates $Candidates -Seen $Seen -Path (Join-Path $directory.FullName "bin\Rscript.exe") -Source ($SourcePrefix + ":" + $directory.Name)
        Add-Candidate -Candidates $Candidates -Seen $Seen -Path (Join-Path $directory.FullName "bin\x64\Rscript.exe") -Source ($SourcePrefix + ":" + $directory.Name)
    }
}

function Get-RCandidates {
    $candidates = New-Object System.Collections.ArrayList
    $seen = @{}

    Add-RegistryCandidates -Candidates $candidates -Seen $seen

    try {
        $whereOutput = (& where.exe Rscript 2>$null | Out-String).Trim()
        if ($whereOutput) {
            foreach ($line in ($whereOutput -split "`r?`n")) {
                Add-Candidate -Candidates $candidates -Seen $seen -Path $line -Source "path:where"
            }
        }
    }
    catch {
    }

    if ($env:ProgramFiles) {
        Add-RootCandidates -Candidates $candidates -Seen $seen -RootPath (Join-Path $env:ProgramFiles "R") -SourcePrefix "programfiles"
    }
    if (${env:ProgramFiles(x86)}) {
        Add-RootCandidates -Candidates $candidates -Seen $seen -RootPath (Join-Path ${env:ProgramFiles(x86)} "R") -SourcePrefix "programfilesx86"
    }
    if ($env:LOCALAPPDATA) {
        Add-RootCandidates -Candidates $candidates -Seen $seen -RootPath (Join-Path $env:LOCALAPPDATA "Programs\R") -SourcePrefix "localappdata_programs"
        Add-RootCandidates -Candidates $candidates -Seen $seen -RootPath (Join-Path $env:LOCALAPPDATA "R") -SourcePrefix "localappdata_r"
    }
    Add-RootCandidates -Candidates $candidates -Seen $seen -RootPath "C:\R" -SourcePrefix "c_root"
    Add-RootCandidates -Candidates $candidates -Seen $seen -RootPath "C:\tools\R" -SourcePrefix "tools_r"

    return $candidates
}

function Get-RVersionInfo {
    param([string]$RScriptPath)

    $output = (& $RScriptPath --version 2>&1 | Out-String).Trim()
    $token = Get-VersionToken -Text $output
    return [ordered]@{
        raw = $output
        token = $token
        ok = (Test-MinVersion -CurrentVersion $token -RequiredVersion $MinVersion)
    }
}

function Test-CranReachability {
    param([string]$Url)

    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Head -TimeoutSec 20 | Out-Null
        return $true
    }
    catch {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Get -TimeoutSec 20 | Out-Null
            return $true
        }
        catch {
            return $false
        }
    }
}

function Write-JsonResult {
    param(
        [hashtable]$Payload,
        [int]$ExitCode
    )

    $json = $Payload | ConvertTo-Json -Depth 10
    if ($JsonOut) {
        $jsonDir = Split-Path -Parent $JsonOut
        if ($jsonDir) {
            New-Item -ItemType Directory -Force -Path $jsonDir | Out-Null
        }
        Set-Content -LiteralPath $JsonOut -Value $json -Encoding UTF8
    }
    Write-Output $json
    exit $ExitCode
}

try {
    $downloadUrl = "https://cran.r-project.org/bin/windows/base/"
    $cranReachable = Test-CranReachability -Url $CranUrl
    $candidates = @(Get-RCandidates)
    $compatibleEntries = @()
    $bestIncompatible = $null

    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate.path)) {
            continue
        }

        try {
            $versionInfo = Get-RVersionInfo -RScriptPath $candidate.path
        }
        catch {
            continue
        }

        $entry = [ordered]@{
            rscript_path = $candidate.path
            source = $candidate.source
            version = $versionInfo.raw
            version_token = $versionInfo.token
        }

        if ($versionInfo.ok) {
            $entry["version_sort_key"] = Get-VersionSortKey -Version $versionInfo.token
            $entry["path_priority"] = if ($candidate.path -match "\\bin\\Rscript\.exe$") { 1 } else { 0 }
            $compatibleEntries += $entry
            continue
        }

        if (-not $bestIncompatible) {
            $bestIncompatible = $entry
        }
    }

    if ($compatibleEntries.Count -gt 0) {
        $compatible = $compatibleEntries |
            Sort-Object -Property { $_["version_sort_key"] }, { $_["path_priority"] } -Descending |
            Select-Object -First 1
        $message = "R detectado com sucesso."
        if (-not $cranReachable) {
            $message = "R detectado, mas sem acesso ao CRAN. Conecte-se a internet e tente novamente."
        }

        Write-JsonResult -Payload ([ordered]@{
            ok = $true
            rscript_path = $compatible.rscript_path
            version = $compatible.version
            version_token = $compatible.version_token
            source = $compatible.source
            cran_reachable = $cranReachable
            cran_url_tested = $CranUrl
            message_ptbr = $message
            download_url = $downloadUrl
        }) -ExitCode 0
    }

    if ($bestIncompatible) {
        Write-JsonResult -Payload ([ordered]@{
            ok = $false
            rscript_path = $bestIncompatible.rscript_path
            version = $bestIncompatible.version
            version_token = $bestIncompatible.version_token
            source = $bestIncompatible.source
            cran_reachable = $cranReachable
            cran_url_tested = $CranUrl
            message_ptbr = ("O R foi encontrado, mas a versao e incompativel. Instale o R {0} ou superior." -f $MinVersion)
            download_url = $downloadUrl
        }) -ExitCode 2
    }

    Write-JsonResult -Payload ([ordered]@{
        ok = $false
        rscript_path = ""
        version = ""
        version_token = ""
        source = ""
        cran_reachable = $cranReachable
        cran_url_tested = $CranUrl
        message_ptbr = ("O labiia_lex requer o R {0} ou superior. Instale o R e execute este instalador novamente." -f $MinVersion)
        download_url = $downloadUrl
    }) -ExitCode 1
}
catch {
    Write-JsonResult -Payload ([ordered]@{
        ok = $false
        rscript_path = ""
        version = ""
        version_token = ""
        source = ""
        cran_reachable = $false
        cran_url_tested = $CranUrl
        message_ptbr = ("Falha interna ao verificar o R: {0}" -f $_.Exception.Message)
        download_url = "https://cran.r-project.org/bin/windows/base/"
    }) -ExitCode 3
}
