param(
    [switch]$SkipCopy
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$runnerDir = Join-Path $root "tools\gephi_runner"
$targetJar = Join-Path $runnerDir "target\gephi-runner.jar"
$outJar = Join-Path $root "resources\gephi_runner\gephi-runner.jar"

$javacCmd = Get-Command javac -ErrorAction SilentlyContinue
if (-not $javacCmd) {
    if ($env:JAVA_HOME -and (Test-Path (Join-Path $env:JAVA_HOME "bin\javac.exe"))) {
        $env:Path = "$(Join-Path $env:JAVA_HOME 'bin');$env:Path"
        $javacCmd = Get-Command javac -ErrorAction SilentlyContinue
    }
}
if (-not $javacCmd) {
    $jdkCandidate = Get-ChildItem "C:\Program Files\Eclipse Adoptium" -Recurse -Filter "javac.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $jdkCandidate) {
        $jdkCandidate = Get-ChildItem "C:\Program Files\Java" -Recurse -Filter "javac.exe" -ErrorAction SilentlyContinue |
            Select-Object -First 1
    }
    if ($jdkCandidate) {
        $env:JAVA_HOME = Split-Path (Split-Path $jdkCandidate.FullName -Parent) -Parent
        $env:Path = "$(Join-Path $env:JAVA_HOME 'bin');$env:Path"
        $javacCmd = Get-Command javac -ErrorAction SilentlyContinue
    }
}
if (-not $javacCmd) {
    throw "JDK não encontrado (javac ausente). Instale/configure Java 17 JDK antes do build."
}

$mvnCmd = $null
$mvnInPath = Get-Command mvn -ErrorAction SilentlyContinue
if ($mvnInPath) {
    $mvnCmd = $mvnInPath.Source
}
elseif ($env:MAVEN_HOME -and (Test-Path (Join-Path $env:MAVEN_HOME "bin\mvn.cmd"))) {
    $mvnCmd = Join-Path $env:MAVEN_HOME "bin\mvn.cmd"
}
else {
    $candidate = Get-ChildItem "C:\Tools" -Recurse -Filter "mvn.cmd" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($candidate) {
        $mvnCmd = $candidate.FullName
    }
}

if (-not $mvnCmd) {
    throw "Maven não encontrado. Configure MAVEN_HOME ou instale o Apache Maven."
}

Push-Location $runnerDir
try {
    & $mvnCmd -q -DskipTests clean package
}
finally {
    Pop-Location
}

if (-not (Test-Path $targetJar)) {
    throw "Jar não gerado: $targetJar"
}

if (-not $SkipCopy) {
    $outDir = Split-Path -Parent $outJar
    if (-not (Test-Path $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }
    Copy-Item -Path $targetJar -Destination $outJar -Force
    Write-Host "Runner copiado para $outJar"
}
