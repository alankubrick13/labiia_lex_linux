[CmdletBinding()]
param(
    [string]$Root = "",
    [string]$VenvName = "venv",
    [switch]$SkipInstall = $false,
    [switch]$RunSmoke = $true
)

$ErrorActionPreference = "Stop"

$projectRoot = if ($Root) {
    (Resolve-Path $Root).Path
} else {
    (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Test-IsWindowsAppAlias {
    param([string]$Path)
    return ($Path -and $Path -like "*\Microsoft\WindowsApps\*")
}

function Resolve-PythonLauncher {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        return [PSCustomObject]@{
            Exe = $pyCmd.Source
            PrefixArgs = @("-3")
        }
    }
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and -not (Test-IsWindowsAppAlias $pythonCmd.Source)) {
        return [PSCustomObject]@{
            Exe = $pythonCmd.Source
            PrefixArgs = @()
        }
    }
    throw "Python launcher nao encontrado (python/py)."
}

$venvPath = Join-Path $projectRoot $VenvName
$venvPython = Join-Path $venvPath "Scripts\\python.exe"
$reqFile = Join-Path $projectRoot "requirements.txt"
$launcher = Resolve-PythonLauncher
$optionalRequirementNames = @("fa2-modified")

Write-Host "[bootstrap] Root: $projectRoot"
Write-Host "[bootstrap] Venv: $venvPath"

if (-not (Test-Path $venvPython)) {
    Write-Host "[bootstrap] Criando ambiente virtual..."
    $venvArgs = @()
    if ($launcher.PrefixArgs -and $launcher.PrefixArgs.Count -gt 0) {
        $venvArgs += $launcher.PrefixArgs
    }
    $venvArgs += @("-m", "venv", $venvPath)
    & $launcher.Exe @venvArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao criar venv em $venvPath"
    }
}

Write-Host "[bootstrap] Atualizando pip..."
& $venvPython -m pip install --upgrade pip --disable-pip-version-check --no-warn-script-location --no-cache-dir
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao atualizar pip no ambiente virtual."
}

if (-not $SkipInstall) {
    if (-not (Test-Path $reqFile)) {
        throw "requirements.txt nao encontrado em $projectRoot"
    }
    $requirementLines = Get-Content $reqFile | Where-Object {
        $trimmed = $_.Trim()
        $trimmed -ne "" -and -not $trimmed.StartsWith("#")
    }

    $requiredLines = @()
    $optionalLines = @()
    foreach ($line in $requirementLines) {
        $nameMatch = [regex]::Match($line.Trim(), '^[A-Za-z0-9_.-]+')
        if ($nameMatch.Success) {
            $pkgName = $nameMatch.Value.ToLowerInvariant()
            if ($optionalRequirementNames -contains $pkgName) {
                $optionalLines += $line.Trim()
                continue
            }
        }
        $requiredLines += $line.Trim()
    }

    if ($requiredLines.Count -gt 0) {
        $tmpReq = Join-Path ([System.IO.Path]::GetTempPath()) ("lexianalyst-required-" + $PID + ".txt")
        try {
            Set-Content -Path $tmpReq -Value $requiredLines -Encoding ascii
            Write-Host "[bootstrap] Instalando dependencias essenciais..."
            & $venvPython -m pip install -r $tmpReq --disable-pip-version-check --no-warn-script-location --no-cache-dir
            if ($LASTEXITCODE -ne 0) {
                throw "Falha ao instalar dependencias essenciais."
            }
        }
        finally {
            if (Test-Path $tmpReq) {
                Remove-Item $tmpReq -Force -ErrorAction SilentlyContinue
            }
        }
    }

    foreach ($optionalReq in $optionalLines) {
        Write-Host "[bootstrap] Tentando instalar opcional: $optionalReq"
        & $venvPython -m pip install $optionalReq --disable-pip-version-check --no-warn-script-location --no-cache-dir
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Dependencia opcional nao instalada: $optionalReq. O sistema seguira com fallback interno."
        }
    }
}

if ($RunSmoke) {
    Write-Host "[bootstrap] Executando smoke test..."
    if ($SkipInstall) {
        & $venvPython -c "import sys; print(sys.version)"
        if ($LASTEXITCODE -ne 0) {
            throw "Smoke basico falhou no ambiente virtual."
        }
    } else {
        Push-Location $projectRoot
        try {
            & $venvPython main.py --self-test
            if ($LASTEXITCODE -ne 0) {
                throw "Self-test falhou apos bootstrap completo."
            }
        }
        finally {
            Pop-Location
        }
    }
}

Write-Host "[bootstrap] Ambiente pronto."
