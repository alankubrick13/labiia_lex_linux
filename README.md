# labiia_lex

[![Version](https://img.shields.io/badge/version-1.0.9-blue.svg)](VERSION)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)

`labiia_lex` e um software de analise textual computacional para Windows,
desenvolvido em Python, R e CustomTkinter. O foco da versao 1.0.9 e estabilidade
na importacao, preparacao opcional do corpus e execucao de analises textuais com
fluxos visuais acessiveis para usuarios nao tecnicos.

## O que o software faz

- Importa corpus em `TXT`, `PDF`, `DOCX`, `XLSX`, `CSV` e `ZIP`
- Oferece preparacao opcional do corpus com expressoes compostas e entidades leves
- Executa estatisticas, CHD, similitude, AFC, nuvem, mapa tematico e analises auxiliares
- Empacota ajuda local, tutorial guiado e recursos de interface para uso offline
- Usa o R instalado na maquina e pode reparar pacotes R sem exigir terminal

## Estado deste repositorio publico

Este repositorio publica o **codigo-fonte** do `labiia_lex`, a documentacao e os
scripts de build.

No momento, **nao ha arquivo `.exe` disponibilizado neste repositorio**. A pasta
`installer/` permanece versionada para que terceiros possam estudar, auditar e
reproduzir o processo de empacotamento.

## Requisitos

### Uso como aplicativo instalado no Windows

- Windows 10/11 64-bit
- R ja instalado no computador
- Internet durante instalacao ou reparo de pacotes R

O instalador do projeto foi desenhado para empacotar Python, bibliotecas Python,
Java/JRE, arquivos de ajuda, exemplos e demais recursos da aplicacao. Ele detecta
automaticamente a versao mais nova do R presente na maquina e usa essa instalacao.

### Desenvolvimento

- Python 3.9 ou superior
- Git
- Git LFS
- R instalado no Windows

## Clonar o codigo-fonte

```powershell
git lfs install
git clone https://github.com/cardososampaio/labiia_lex.git
cd labiia_lex
git lfs pull
```

## Preparar ambiente de desenvolvimento

O caminho recomendado e usar o bootstrap do proprio repositorio:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_dev_env.ps1 -VenvName venv -RunSmoke
```

Equivalente manual:

```powershell
py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Executar o software

```powershell
.\venv\Scripts\python.exe main.py
```

Tambem e possivel usar:

```powershell
.\LabiiaLex.pyw
.\LabiiaLex.vbs
```

## Uso rapido

1. Abra o software.
2. Clique em `Importar` para carregar o corpus.
3. Escolha o modo de importacao adequado ao seu arquivo.
4. Se quiser, rode `Preparar corpus` antes das analises.
5. Execute a analise desejada e exporte os resultados.

## Formato textual estruturado

O software aceita um formato textual estruturado com marcadores `****` para
documentos e metadados no padrao `*nome_valor`:

```text
**** *grupo_a *periodo_1
Texto do primeiro documento.

**** *grupo_b *periodo_2
Texto do segundo documento.
```

Regras praticas:

- cada documento comeca com `****`
- cada metadado comeca com `*`
- use letras, numeros e underscore nos nomes
- evite acentos e espacos em nomes de variaveis

## Estrutura do projeto

```text
labiia_lex/
├── main.py
├── src/
├── Rscripts/
├── installer/
├── resources/
├── docs/
├── tests/
└── scripts/
```

## Verificacoes uteis

```powershell
$env:PYTHONPATH=(Get-Location).Path

py -3 -m py_compile main.py src\ui\main_window.py src\core\version.py
py -3 -m pytest -q tests
py -3 main.py --self-test --json-out tmp_self_test_public.json
```

## Instalador

Os arquivos do instalador ficam em `installer/` e os scripts de build em
`scripts/`. Isso permite que outras pessoas reproduzam localmente o processo de
empacotamento do aplicativo.

Saida esperada do build local:

```text
installer\dist\labiia_lex-Setup-x64-<versao>.exe
```

Esse artefato **nao e publicado neste repositorio** nesta etapa.

## Documentacao

- [Manual do usuario](docs/manual_usuario.md)
- [Guia de instalacao](INSTALL.md)
- [Guia do instalador](installer/README-Instalador.md)

## Como contribuir

Leia [CONTRIBUTING.md](CONTRIBUTING.md) antes de abrir issue ou pull request.

## Licenca

Este projeto e distribuido sob a **GNU GPL v3 ou qualquer versao posterior**.
Veja [LICENSE](LICENSE).

## Suporte e contato

- Issues do GitHub: use para bugs, duvidas e sugestoes
- Email: `cardososampaio@gmail.com`
