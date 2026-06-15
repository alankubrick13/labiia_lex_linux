# Instalacao e Desenvolvimento - labiia_lex 1.0.9

Este guia cobre a preparacao do ambiente de desenvolvimento e a reproducao
local do empacotamento do `labiia_lex`.

## Escopo deste repositorio

O repositorio publico distribui o **codigo-fonte** e os arquivos de build.
Ele nao disponibiliza, nesta etapa, um `.exe` pronto para download.

## Pre-requisitos

- Windows 10/11 64-bit
- Python 3.9 ou superior
- Git
- Git LFS
- R instalado no Windows

O `labiia_lex` procura automaticamente instalacoes do R e usa a versao mais nova
encontrada no computador.

## Clonar o repositorio

```powershell
git lfs install
git clone https://github.com/cardososampaio/labiia_lex.git
cd labiia_lex
git lfs pull
```

O Git LFS e necessario porque recursos grandes, como `resources/jre17/**` e
`resources/gephi_runner/gephi-runner.jar`, fazem parte do projeto.

## Preparar o ambiente Python

Fluxo recomendado:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_dev_env.ps1 -VenvName venv -RunSmoke
```

Fluxo manual equivalente:

```powershell
py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Preparar o R

O aplicativo nao instala uma nova copia do R. Ele usa a instalacao mais nova ja
presente na maquina e pode instalar pacotes faltantes em uma biblioteca de
usuario isolada do `labiia_lex`.

Para desenvolvimento, trate como fonte de verdade:

- `installer/manifests/r_packages_core.json`
- `installer/manifests/r_packages_optional.json`

## Executar o aplicativo

```powershell
.\venv\Scripts\python.exe main.py
```

Tambem e possivel usar:

```powershell
.\LabiiaLex.pyw
.\LabiiaLex.vbs
```

## Rodar verificacoes

```powershell
$env:PYTHONPATH=(Get-Location).Path

py -3 -m py_compile main.py src\ui\main_window.py src\core\version.py
py -3 -m pytest -q tests
py -3 main.py --self-test --json-out tmp_self_test_install.json
```

## Reproduzir o build do instalador

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_release_installer.ps1
```

Saida esperada:

```text
installer\dist\labiia_lex-Setup-x64-<versao>.exe
```

Validacao sem assinatura e sem Inno Setup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_release_installer.ps1 -SkipInno -SkipSigning
```

## Problemas comuns

### Git LFS nao baixou os arquivos grandes

```powershell
git lfs install
git lfs pull
git lfs ls-files
```

### R nao foi encontrado

Verifique:

```powershell
Rscript --version
```

Se necessario, configure o caminho do R nas configuracoes do `labiia_lex`.

### Pacotes R faltando

No aplicativo instalado, use o atalho `Reparar pacotes R do labiia_lex`. Em
desenvolvimento, mantenha os manifests de `installer/manifests/` alinhados com
os pacotes realmente usados pelo aplicativo.
