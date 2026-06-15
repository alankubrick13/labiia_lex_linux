[CmdletBinding()]
param(
    [string]$AppVersion = "",
    [string]$PythonExe = "",
    [switch]$SkipPyInstaller,
    [switch]$SkipInno,
    [switch]$SkipSigning
)

$ErrorActionPreference = "Stop"

function Get-TrimmedEnvValue {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ($null -eq $value) {
        return ""
    }
    return $value.Trim()
}

function Test-IsWindowsAppAlias {
    param([string]$Path)
    return ($Path -and $Path -like "*\Microsoft\WindowsApps\*")
}

function Resolve-PythonExe {
    param(
        [string]$Preferred,
        [string]$ProjectRoot = ""
    )
    if ($Preferred -and (Test-Path $Preferred)) {
        return (Resolve-Path $Preferred).Path
    }

    if ($ProjectRoot) {
        $venvCandidates = @(
            (Join-Path $ProjectRoot "venv\Scripts\python.exe"),
            (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
        )
        foreach ($candidate in $venvCandidates) {
            if (Test-Path $candidate) {
                return (Resolve-Path $candidate).Path
            }
        }
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    $candidates = @()
    if ($pyCmd) { $candidates += $pyCmd.Source }
    if ($pythonCmd -and -not (Test-IsWindowsAppAlias $pythonCmd.Source)) {
        $candidates += $pythonCmd.Source
    }
    $candidates = $candidates | Where-Object { $_ }

    foreach ($candidate in $candidates) {
        if ($candidate -and $candidate.ToLower().EndsWith("py.exe")) {
            try {
                $resolved = & $candidate -3 -c "import sys;print(sys.executable)"
                if ($LASTEXITCODE -eq 0 -and $resolved) {
                    return $resolved.Trim()
                }
            }
            catch {
                continue
            }
        }
        elseif (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "Python nao encontrado. Informe -PythonExe <caminho>."
}

function Resolve-AppVersion {
    param([string]$Current, [string]$Root)
    if ($Current) {
        return $Current
    }

    $versionFile = Join-Path $Root "VERSION"
    if (Test-Path $versionFile) {
        $fileVersion = (Get-Content -Path $versionFile -Encoding UTF8 -TotalCount 1).Trim()
        if ($fileVersion -match '^[0-9]+\.[0-9]+\.[0-9]+$') {
            return $fileVersion
        }
    }

    $readme = Join-Path $Root "README.md"
    if (Test-Path $readme) {
        $m = Select-String -Path $readme -Pattern "version-([0-9]+\.[0-9]+\.[0-9]+)" -AllMatches | Select-Object -First 1
        if ($m -and $m.Matches.Count -gt 0) {
            return $m.Matches[0].Groups[1].Value
        }
    }

    return "1.0.8"
}

function Resolve-Iscc {
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    try {
        $hkcuUninstall = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like '*Inno Setup*' } |
            Select-Object -First 1
        if ($hkcuUninstall -and $hkcuUninstall.InstallLocation) {
            $candidate = Join-Path $hkcuUninstall.InstallLocation "ISCC.exe"
            if (Test-Path $candidate) {
                return $candidate
            }
        }
    }
    catch {
        # continua para caminhos conhecidos
    }

    $common = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($path in $common) {
        if (Test-Path $path) {
            return $path
        }
    }

    throw "ISCC (Inno Setup) nao encontrado. Instale Inno Setup 6 e adicione ISCC ao PATH."
}

function Resolve-SignTool {
    $cmd = Get-Command signtool -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $kitRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (Test-Path $kitRoot) {
        $candidate = Get-ChildItem -Path $kitRoot -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }

    throw "signtool.exe nao encontrado. Instale o Windows SDK com Signing Tools."
}

function Resolve-CodeSigningConfig {
    param([switch]$Skip)
    if ($Skip) {
        return @{
            Enabled = $false
            Reason = "disabled_by_flag"
        }
    }

    $pfxPath = Get-TrimmedEnvValue "LEXI_SIGN_PFX_PATH"
    $pfxPassword = Get-TrimmedEnvValue "LEXI_SIGN_PFX_PASSWORD"
    $timestampUrl = Get-TrimmedEnvValue "LEXI_SIGN_TIMESTAMP_URL"

    if (-not $pfxPath -and -not $pfxPassword -and -not $timestampUrl) {
        return @{
            Enabled = $false
            Reason = "not_configured"
        }
    }

    if (-not $pfxPath) {
        throw "Variavel LEXI_SIGN_PFX_PATH nao definida."
    }
    if (-not (Test-Path $pfxPath)) {
        throw "Arquivo PFX nao encontrado em LEXI_SIGN_PFX_PATH: $pfxPath"
    }
    if (-not $pfxPassword) {
        throw "Variavel LEXI_SIGN_PFX_PASSWORD nao definida."
    }
    if (-not $timestampUrl) {
        throw "Variavel LEXI_SIGN_TIMESTAMP_URL nao definida."
    }

    return @{
        Enabled = $true
        SignTool = (Resolve-SignTool)
        PfxPath = (Resolve-Path $pfxPath).Path
        PfxPassword = $pfxPassword
        TimestampUrl = $timestampUrl
    }
}

function Assert-AuthenticodeSignature {
    param(
        [string]$FilePath,
        [string]$ExpectedPublisher = "LabiiaLex"
    )
    $sig = Get-AuthenticodeSignature -FilePath $FilePath
    if (-not $sig) {
        throw "Nao foi possivel validar assinatura de: $FilePath"
    }
    if ($sig.Status -ne "Valid") {
        throw "Assinatura invalida para $FilePath (status: $($sig.Status))."
    }
    if ($ExpectedPublisher) {
        $subject = ($sig.SignerCertificate.Subject | Out-String).Trim()
        if (-not $subject -or ($subject -notmatch [Regex]::Escape($ExpectedPublisher))) {
            throw "Assinatura valida, mas publisher inesperado em $FilePath. Subject: $subject"
        }
    }
}

function Sign-FileAuthenticode {
    param(
        [string]$SignTool,
        [string]$FilePath,
        [string]$PfxPath,
        [string]$PfxPassword,
        [string]$TimestampUrl
    )
    if (-not (Test-Path $FilePath)) {
        throw "Arquivo para assinatura nao encontrado: $FilePath"
    }
    & $SignTool sign /fd SHA256 /td SHA256 /tr $TimestampUrl /f $PfxPath /p $PfxPassword /d "LabiiaLex" /du "https://github.com/cardososampaio/labiia_lex" $FilePath
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao assinar arquivo: $FilePath (signtool exit=$LASTEXITCODE)"
    }
}

function Test-PyInstaller {
    param([string]$Python)
    & $Python -c "import PyInstaller,sys; print(PyInstaller.__version__)"
    return ($LASTEXITCODE -eq 0)
}

function Test-BuildRuntimeDeps {
    param([string]$Python)
    & $Python -c "import customtkinter,numpy,pandas,networkx,matplotlib,docx,lxml.etree,openpyxl,pdfplumber,yake,cleantext,tkinterweb; from sklearn.feature_extraction.text import CountVectorizer; from sklearn.decomposition import LatentDirichletAllocation; print('runtime_deps_ok')"
    return ($LASTEXITCODE -eq 0)
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$specPath = Join-Path $root "labiialex_app.spec"
$distRoot = Join-Path $root "dist"
$distAppDir = Join-Path $distRoot "LabiiaLex"
$distExe = Join-Path $distAppDir "LabiiaLex.exe"
$stageDir = Join-Path $root "installer\_stage\LabiiaLex"
$installerDistDir = Join-Path $root "installer\dist"
$innoScript = Join-Path $root "installer\inno\LabiiaLex.iss"

$python = Resolve-PythonExe -Preferred $PythonExe -ProjectRoot $root
$AppVersion = Resolve-AppVersion -Current $AppVersion -Root $root
$signing = Resolve-CodeSigningConfig -Skip:$SkipSigning

Write-Host "[build] Root: $root"
Write-Host "[build] Python: $python"
Write-Host "[build] Version: $AppVersion"
if ($signing.Enabled) {
    Write-Host "[build] Code signing: habilitado (OV + timestamp)"
}
else {
    Write-Host "[build] Code signing: desabilitado ($($signing.Reason))"
}

if (-not (Test-Path $specPath)) {
    throw "Spec canônico nao encontrado: $specPath"
}
if (-not (Test-Path $innoScript)) {
    throw "Script Inno nao encontrado: $innoScript"
}

if (-not $SkipPyInstaller) {
    if (-not (Test-PyInstaller -Python $python)) {
        throw "PyInstaller nao encontrado no Python selecionado. Execute: `"$python`" -m pip install pyinstaller"
    }
    if (-not (Test-BuildRuntimeDeps -Python $python)) {
        throw "Dependencias de runtime ausentes no Python selecionado (incluindo docx/lxml/openpyxl/pdfplumber). Ative o venv correto antes do build."
    }
    Write-Host "[build] Executando PyInstaller com spec canônico..."
    Push-Location $root
    try {
        & $python -m PyInstaller $specPath --noconfirm --clean --distpath $distRoot --workpath (Join-Path $root "build")
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller falhou com codigo $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path $distExe)) {
    throw "Executavel nao encontrado apos build: $distExe"
}

if ($signing.Enabled) {
    Write-Host "[build] Assinando executavel principal..."
    Sign-FileAuthenticode -SignTool $signing.SignTool -FilePath $distExe -PfxPath $signing.PfxPath -PfxPassword $signing.PfxPassword -TimestampUrl $signing.TimestampUrl
    Assert-AuthenticodeSignature -FilePath $distExe -ExpectedPublisher "LabiiaLex"
}

Write-Host "[build] Montando stage para instalador..."
if (Test-Path $stageDir) {
    Remove-Item $stageDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stageDir | Out-Null
Copy-Item (Join-Path $distAppDir "*") $stageDir -Recurse -Force

$stageInstallerScripts = Join-Path $stageDir "installer\scripts"
$stageInstallerManifests = Join-Path $stageDir "installer\manifests"
New-Item -ItemType Directory -Force -Path $stageInstallerScripts | Out-Null
New-Item -ItemType Directory -Force -Path $stageInstallerManifests | Out-Null

Copy-Item (Join-Path $root "installer\scripts\*") $stageInstallerScripts -Recurse -Force
Copy-Item (Join-Path $root "installer\manifests\*") $stageInstallerManifests -Recurse -Force
Copy-Item (Join-Path $root "license.txt") $stageDir -Force
Write-Host "[build] Estrategia de runtime: R externo obrigatorio no computador do usuario."

if (-not (Test-Path (Join-Path $stageDir "LabiiaLex.exe"))) {
    throw "Arquivo obrigatório ausente no stage: LabiiaLex.exe"
}

$runnerCandidates = @(
    (Join-Path $stageDir "resources\gephi_runner\gephi-runner.jar"),
    (Join-Path $stageDir "_internal\resources\gephi_runner\gephi-runner.jar")
)
$javaCandidates = @(
    (Join-Path $stageDir "resources\jre17\bin\java.exe"),
    (Join-Path $stageDir "_internal\resources\jre17\bin\java.exe")
)

$runnerJar = $runnerCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $runnerJar) {
    throw "Arquivo obrigatório ausente no stage: gephi-runner.jar"
}
$javaExe = $javaCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $javaExe) {
    throw "Arquivo obrigatório ausente no stage: java.exe (jre17)"
}

$requiredStageFiles = @(
    (Join-Path $stageDir "installer\scripts\install_r_packages.R"),
    (Join-Path $stageDir "installer\scripts\post_install_check.py"),
    (Join-Path $stageDir "installer\scripts\check_r.ps1"),
    (Join-Path $stageDir "installer\scripts\validate_install.ps1"),
    (Join-Path $stageDir "installer\manifests\r_packages_core.json"),
    (Join-Path $stageDir "installer\manifests\r_packages_optional.json"),
    (Join-Path $stageDir "installer\manifests\r_environment_lock.json")
)
foreach ($req in $requiredStageFiles) {
    if (-not (Test-Path $req)) {
        throw "Arquivo obrigatório ausente no stage: $req"
    }
}

$wrongProductNameHits = Get-ChildItem -Path $stageDir -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'LabbiaLexi|LexiAnalyst\.exe' }
if ($wrongProductNameHits) {
    $hitList = ($wrongProductNameHits | Select-Object -First 5 -ExpandProperty FullName) -join '; '
    throw "Stage invalido: nome de produto antigo/incorreto encontrado: $hitList"
}

$guidedTourSourcePath = Join-Path $root "src\ui\widgets\guided_tour.py"
if (-not (Test-Path $guidedTourSourcePath)) {
    throw "Fonte obrigatória ausente: src\\ui\\widgets\\guided_tour.py"
}
$guidedTourStageCandidates = @(
    (Join-Path $stageDir "src\ui\widgets\guided_tour.py"),
    (Join-Path $stageDir "_internal\src\ui\widgets\guided_tour.py")
)
$guidedTourStagePath = $guidedTourStageCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $guidedTourStagePath) {
    throw "Arquivo obrigatório ausente no stage: src\\ui\\widgets\\guided_tour.py"
}
$guidedTourSourceHash = (Get-FileHash -Path $guidedTourSourcePath -Algorithm SHA256).Hash
$guidedTourStageHash = (Get-FileHash -Path $guidedTourStagePath -Algorithm SHA256).Hash
if ($guidedTourSourceHash -ne $guidedTourStageHash) {
    throw "Stage desatualizado: guided_tour.py no stage diverge do fonte atual. Rode o build sem reaproveitar dist antigo."
}

$wordcloudStageCandidates = @(
    (Join-Path $stageDir "src\analysis\wordcloud.py"),
    (Join-Path $stageDir "_internal\src\analysis\wordcloud.py")
)
if (-not ($wordcloudStageCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)) {
    throw "Arquivo obrigatório ausente no stage: src\\analysis\\wordcloud.py"
}

$rScriptGenCandidates = @(
    (Join-Path $stageDir "src\core\r_script_generator.py"),
    (Join-Path $stageDir "_internal\src\core\r_script_generator.py")
)
$rScriptGenPath = $rScriptGenCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $rScriptGenPath) {
    throw "Arquivo obrigatório ausente no stage: src\\core\\r_script_generator.py"
}
$rScriptGenRaw = Get-Content $rScriptGenPath -Raw
$legacyWordcloudPatterns = @(
    "shape_clip_applied",
    "shape_outside_ratio_after",
    "compute_outside_ratio",
    "enforce_shape_clip_png"
)
foreach ($legacyPattern in $legacyWordcloudPatterns) {
    if ($rScriptGenRaw -match [Regex]::Escape($legacyPattern)) {
        throw "Stage invalido: trecho legado de recorte de nuvem detectado em $rScriptGenPath ($legacyPattern)"
    }
}
$requiredWordcloudPatterns = @(
    "shape = shape",
    "rm_outside = TRUE",
    "use_richtext = FALSE"
)
foreach ($requiredPattern in $requiredWordcloudPatterns) {
    if ($rScriptGenRaw -notmatch [Regex]::Escape($requiredPattern)) {
        throw "Stage invalido: ajuste obrigatório da nuvem ausente em $rScriptGenPath ($requiredPattern)"
    }
}

$rCoreManifestPath = Join-Path $stageDir "installer\manifests\r_packages_core.json"
$rCoreManifest = Get-Content $rCoreManifestPath -Raw | ConvertFrom-Json
foreach ($requiredRPackage in @("ca", "topicmodels", "slam")) {
    if (-not ($rCoreManifest.packages -contains $requiredRPackage)) {
        throw "Manifesto R core invalido: pacote '$requiredRPackage' ausente em $rCoreManifestPath"
    }
}

$afcPlotCandidates = @(
    (Join-Path $stageDir "src\visualization\r_integration\r_scripts\afc_plot.R"),
    (Join-Path $stageDir "_internal\src\visualization\r_integration\r_scripts\afc_plot.R")
)
if (-not ($afcPlotCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)) {
    throw "Arquivo obrigatório ausente no stage: src\\visualization\\r_integration\\r_scripts\\afc_plot.R"
}

$ldaTopicmodelsCandidates = @(
    (Join-Path $stageDir "Rscripts\lda_topicmodels.R"),
    (Join-Path $stageDir "_internal\Rscripts\lda_topicmodels.R")
)
if (-not ($ldaTopicmodelsCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)) {
    throw "Arquivo obrigatório ausente no stage: Rscripts\\lda_topicmodels.R"
}

$helpCandidates = @(
    (Join-Path $stageDir "docs\help\geral.html"),
    (Join-Path $stageDir "_internal\docs\help\geral.html")
)
if (-not ($helpCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)) {
    throw "Documentação obrigatória ausente no stage: docs\\help\\geral.html"
}

$stageSelfTestJson = Join-Path $root "installer\_debug\stage_self_test_result.json"
if (Test-Path $stageSelfTestJson) {
    Remove-Item $stageSelfTestJson -Force
}

Write-Host "[build] Validando self-test no executavel staged (installer_quick)..."
$prevSelfTestProfile = $env:LEXIANALYST_SELF_TEST_PROFILE
$stageSelfTestExit = -1
try {
    $env:LEXIANALYST_SELF_TEST_PROFILE = "installer_quick"
    $stageSelfTestProcess = Start-Process `
        -FilePath (Join-Path $stageDir "LabiiaLex.exe") `
        -ArgumentList @("--self-test", "--json-out", $stageSelfTestJson) `
        -WorkingDirectory $stageDir `
        -PassThru `
        -Wait
    $stageSelfTestExit = $stageSelfTestProcess.ExitCode
}
finally {
    if ($null -eq $prevSelfTestProfile) {
        Remove-Item Env:LEXIANALYST_SELF_TEST_PROFILE -ErrorAction SilentlyContinue
    }
    else {
        $env:LEXIANALYST_SELF_TEST_PROFILE = $prevSelfTestProfile
    }
}

if ($stageSelfTestExit -ne 0) {
    throw "Self-test staged retornou codigo $stageSelfTestExit."
}
elseif (-not (Test-Path $stageSelfTestJson)) {
    throw "Self-test staged nao gerou JSON em $stageSelfTestJson."
}
else {
    try {
        $stageSelfTestPayload = Get-Content $stageSelfTestJson -Raw | ConvertFrom-Json
    }
    catch {
        throw "Nao foi possivel interpretar JSON do self-test staged: $($_.Exception.Message)"
    }
    if (-not $stageSelfTestPayload.ok) {
        $selfTestErrors = @()
        if ($stageSelfTestPayload.errors) {
            $selfTestErrors = @($stageSelfTestPayload.errors)
        }
        $errorText = if ($selfTestErrors.Count -gt 0) { ($selfTestErrors -join '; ') } else { 'sem detalhes no payload' }
        throw "Self-test staged ok=false: $errorText"
    }
}

if (-not $SkipInno) {
    Write-Host "[build] Gerando setup Inno..."
    New-Item -ItemType Directory -Force -Path $installerDistDir | Out-Null
    $stageDebugDir = Join-Path $stageDir "installer\_debug"
    if (Test-Path $stageDebugDir) {
        Remove-Item -Path $stageDebugDir -Recurse -Force
    }
    $expectedSetupPath = Join-Path $installerDistDir ("labiia_lex-Setup-x64-{0}.exe" -f $AppVersion)
    if (Test-Path $expectedSetupPath) {
        try {
            Remove-Item -Path $expectedSetupPath -Force
        }
        catch {
            throw "Setup de saida em uso: $expectedSetupPath. Feche ou mova o arquivo antes de rodar o build."
        }
    }

    $iscc = Resolve-Iscc
    $runnerSha256 = (Get-FileHash -Path $runnerJar -Algorithm SHA256).Hash.ToLowerInvariant()

    & $iscc "/DSourceDir=$stageDir" "/DAppVersion=$AppVersion" "/DSetupOutputDir=$installerDistDir" "/DGephiRunnerSHA256=$runnerSha256" $innoScript
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC falhou com codigo $LASTEXITCODE"
    }

    $setupPath = Join-Path $installerDistDir ("labiia_lex-Setup-x64-{0}.exe" -f $AppVersion)
    if (-not (Test-Path $setupPath)) {
        $latest = Get-ChildItem $installerDistDir -Filter "labiia_lex-Setup-x64-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($latest) {
            $setupPath = $latest.FullName
        }
    }

    if (-not (Test-Path $setupPath)) {
        throw "Setup final nao encontrado em $installerDistDir"
    }

    if ($signing.Enabled) {
        Write-Host "[build] Assinando setup final..."
        Sign-FileAuthenticode -SignTool $signing.SignTool -FilePath $setupPath -PfxPath $signing.PfxPath -PfxPassword $signing.PfxPassword -TimestampUrl $signing.TimestampUrl
        Assert-AuthenticodeSignature -FilePath $setupPath -ExpectedPublisher "LabiiaLex"
    }

    Write-Host "[build] Setup gerado: $setupPath"
}

Write-Host "[build] Concluido com sucesso."


