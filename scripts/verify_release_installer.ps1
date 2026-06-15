[CmdletBinding()]
param(
    [string]$BuildRoot = "",
    [string]$SelfTestJson = "",
    [switch]$RequireSetup,
    [switch]$SkipSignatureCheck,
    [switch]$RequireSignatureCheck,
    [switch]$FullRuntimeCheck
)

$ErrorActionPreference = "Stop"

$root = if ($BuildRoot) { (Resolve-Path $BuildRoot).Path } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
$distAppDir = Join-Path $root "dist\LabiiaLex"
$distExe = Join-Path $distAppDir "LabiiaLex.exe"
$installerDistDir = Join-Path $root "installer\dist"
$stageDir = Join-Path $root "installer\_stage\LabiiaLex"
$stageExe = Join-Path $stageDir "LabiiaLex.exe"
$postInstallCheckScript = Join-Path $stageDir "installer\scripts\post_install_check.py"
$selfTestProfile = if ($FullRuntimeCheck) { "full" } else { "installer_quick" }

function Resolve-PythonForVerification {
    $venvPython = Join-Path $root "venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return (Resolve-Path $venvPython).Path
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        return @($pyCmd.Source, "-3")
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and $pythonCmd.Source -notlike "*\Microsoft\WindowsApps\*") {
        return $pythonCmd.Source
    }

    throw "Python nao encontrado para rodar post_install_check.py."
}

function Assert-AuthenticodeSignature {
    param(
        [string]$FilePath,
        [string]$ExpectedPublisher = "LabiiaLex"
    )
    if (-not (Test-Path $FilePath)) {
        throw "Arquivo nao encontrado para validar assinatura: $FilePath"
    }
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

if (-not (Test-Path $distExe)) {
    throw "Executavel de distribuicao nao encontrado: $distExe"
}
if (-not (Test-Path $stageExe)) {
    throw "Executavel staged do instalador nao encontrado: $stageExe"
}

if (-not $SelfTestJson) {
    $SelfTestJson = Join-Path $root "installer\dist\self_test_result.json"
}

$selfTestDir = Split-Path -Parent $SelfTestJson
New-Item -ItemType Directory -Force -Path $selfTestDir | Out-Null

Write-Host "[verify] Executando autoteste do executavel distribuivel ($selfTestProfile)..."
if (Test-Path $SelfTestJson) {
    Remove-Item $SelfTestJson -Force
}

$prevProfile = [System.Environment]::GetEnvironmentVariable("LEXIANALYST_SELF_TEST_PROFILE", "Process")
[System.Environment]::SetEnvironmentVariable("LEXIANALYST_SELF_TEST_PROFILE", $selfTestProfile, "Process")
try {
    $proc = Start-Process -FilePath $stageExe -ArgumentList @("--self-test", "--json-out", $SelfTestJson) -PassThru
    $timeoutAt = (Get-Date).AddMinutes(5)
    while ((-not $proc.HasExited) -or (-not (Test-Path $SelfTestJson))) {
        if ((Get-Date) -gt $timeoutAt) {
            try { $proc.Kill() } catch {}
        throw "Autoteste excedeu timeout de 5 minutos. JSON esperado em: $SelfTestJson"
        }
        Start-Sleep -Milliseconds 300
    }
}
finally {
    [System.Environment]::SetEnvironmentVariable("LEXIANALYST_SELF_TEST_PROFILE", $prevProfile, "Process")
}

if (-not (Test-Path $SelfTestJson)) {
    throw "JSON de autoteste nao foi gerado: $SelfTestJson"
}

$diag = Get-Content $SelfTestJson -Raw | ConvertFrom-Json
if (-not $diag.ok) {
    throw "Autoteste retornou ok=false. Verifique $SelfTestJson"
}
if (($diag.PSObject.Properties.Name -contains "self_test_profile") -and ($diag.self_test_profile -ne $selfTestProfile)) {
    throw "Autoteste executado fora do perfil $selfTestProfile. Perfil atual: $($diag.self_test_profile)"
}
if ($diag.PSObject.Properties.Name -contains "gephi_smoke_ok") {
    if (-not $diag.gephi_smoke_ok) {
        throw "Autoteste retornou gephi_smoke_ok=false. Verifique $SelfTestJson"
    }
}
if ($diag.PSObject.Properties.Name -contains "network_text_smoke_ok") {
    if (-not $diag.network_text_smoke_ok) {
        throw "Autoteste retornou network_text_smoke_ok=false. Verifique $SelfTestJson"
    }
}

if (-not (Test-Path $postInstallCheckScript)) {
    throw "Script obrigatório ausente no stage: $postInstallCheckScript"
}

$wordcloudSelfTestJson = Join-Path $root "installer\dist\wordcloud_selftest_result.json"
$wordcloudSelfTestLog = Join-Path $root "installer\dist\wordcloud_selftest_result.log"
$combinedPostInstallJson = Join-Path $root "installer\dist\post_install_check_result.json"
foreach ($artifact in @($wordcloudSelfTestJson, $wordcloudSelfTestLog, $combinedPostInstallJson)) {
    if (Test-Path $artifact) {
        Remove-Item $artifact -Force
    }
}

$pythonCheck = Resolve-PythonForVerification
Write-Host "[verify] Executando gate de pós-instalação do instalador ($selfTestProfile)..."
if ($pythonCheck -is [array]) {
    & $pythonCheck[0] $pythonCheck[1] $postInstallCheckScript `
        --exe $stageExe `
        --json-out $combinedPostInstallJson `
        --profile $selfTestProfile `
        --timeout 300
}
else {
    & $pythonCheck $postInstallCheckScript `
    --exe $stageExe `
    --json-out $combinedPostInstallJson `
    --profile $selfTestProfile `
    --timeout 300
}
if ($LASTEXITCODE -ne 0) {
    throw "post_install_check.py retornou falha no gate de pós-instalação (exit=$LASTEXITCODE). Verifique: $combinedPostInstallJson"
}

if (-not (Test-Path $combinedPostInstallJson)) {
    throw "JSON combinado do gate pos-instalacao nao foi gerado: $combinedPostInstallJson"
}

$combinedDiag = Get-Content $combinedPostInstallJson -Raw | ConvertFrom-Json
if (-not $combinedDiag.ok) {
    throw "Gate pos-instalacao retornou ok=false. Verifique $combinedPostInstallJson"
}

if (-not $combinedDiag.labiialex_self_test -or -not $combinedDiag.labiialex_self_test.payload) {
    throw "Payload do self-test combinado ausente em $combinedPostInstallJson"
}

$combinedPayload = $combinedDiag.labiialex_self_test.payload
if ($FullRuntimeCheck) {
    if (-not $combinedPayload.wordcloud_ok) {
        throw "Self-test combinado: wordcloud_ok=false. Verifique $combinedPostInstallJson"
    }
    if (-not $combinedPayload.wordcloud_shape_checks -or $combinedPayload.wordcloud_shape_checks.Count -lt 2) {
        throw "Self-test combinado: validacao de shape da wordcloud insuficiente."
    }
    if (-not $combinedPayload.wordcloud_shape_hashes) {
        throw "Self-test combinado: hashes de shape da wordcloud ausentes."
    }
    if ($combinedPayload.wordcloud_shape_hashes.circle -eq $combinedPayload.wordcloud_shape_hashes.star) {
        throw "Self-test combinado: hashes de circle/star identicos; shape nao aplicado."
    }
}

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
if (-not ($runnerCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)) {
    throw "Arquivo obrigatório ausente no stage: gephi-runner.jar"
}
if (-not ($javaCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)) {
    throw "Arquivo obrigatório ausente no stage: java.exe (jre17)"
}

$requiredStage = @(
    (Join-Path $stageDir "installer\scripts\install_r_packages.R"),
    (Join-Path $stageDir "installer\scripts\install_python_packages.py"),
    (Join-Path $stageDir "installer\scripts\post_install_check.py"),
    (Join-Path $stageDir "installer\manifests\r_packages_core.json"),
    (Join-Path $stageDir "installer\manifests\r_packages_optional.json"),
    (Join-Path $stageDir "installer\manifests\python_packages_core.json"),
    (Join-Path $stageDir "installer\manifests\python_packages_optional.json")
)
foreach ($path in $requiredStage) {
    if (-not (Test-Path $path)) {
        throw "Arquivo obrigatório ausente no stage: $path"
    }
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
    throw "Stage inconsistente: guided_tour.py no stage diverge do fonte atual."
}

$afcPlotCandidates = @(
    (Join-Path $stageDir "src\visualization\r_integration\r_scripts\afc_plot.R"),
    (Join-Path $stageDir "_internal\src\visualization\r_integration\r_scripts\afc_plot.R")
)
if (-not ($afcPlotCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)) {
    throw "Arquivo obrigatório ausente no stage: src\\visualization\\r_integration\\r_scripts\\afc_plot.R"
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
if (-not ($rScriptGenCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)) {
    throw "Arquivo obrigatório ausente no stage: src\\core\\r_script_generator.py"
}

$rCoreManifestPath = Join-Path $stageDir "installer\manifests\r_packages_core.json"
$rCoreManifest = Get-Content $rCoreManifestPath -Raw | ConvertFrom-Json
if (-not ($rCoreManifest.packages -contains "ca")) {
    throw "Manifesto R core invalido: pacote 'ca' ausente em $rCoreManifestPath"
}

$helpCandidates = @(
    (Join-Path $stageDir "docs\help\geral.html"),
    (Join-Path $stageDir "_internal\docs\help\geral.html")
)
if (-not ($helpCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)) {
    throw "Documentação obrigatória ausente no stage: docs\\help\\geral.html"
}

if ($RequireSignatureCheck -and -not $SkipSignatureCheck) {
    Assert-AuthenticodeSignature -FilePath $distExe -ExpectedPublisher "LabiiaLex"
}

$legacyForbidden = @(
    "instalar_lexianalyst.bat",
    "start_lexianalyst.bat",
    "iniciar_lexianalyst.bat",
    "iniciar_lexianalyst.vbs",
    "abrir_lexianalyst_sem_cmd.ps1"
)

foreach ($legacy in $legacyForbidden) {
    if (Test-Path (Join-Path $stageDir $legacy)) {
        throw "Arquivo legado indevido no stage final: $legacy"
    }
}

if ($RequireSetup) {
    $setup = Get-ChildItem $installerDistDir -Filter "labiia_lex-Setup-x64-*.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $setup) {
        throw "Setup final nao encontrado em $installerDistDir"
    }
    if ($RequireSignatureCheck -and -not $SkipSignatureCheck) {
        Assert-AuthenticodeSignature -FilePath $setup.FullName -ExpectedPublisher "LabiiaLex"
    }
    Write-Host "[verify] Setup encontrado: $($setup.FullName)"
}

Write-Host "[verify] OK - distribuicao validada com sucesso."
