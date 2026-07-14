# labiia_lex_linux

[![Version](https://img.shields.io/badge/version-1.0.9-blue.svg)](VERSION)
[![Python](https://img.shields.io/badge/python-3.11+-green.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)

O `labiia_lex_linux` é um software de análise textual computacional adaptado para **Linux** (baseado no fork de `cardososampaio/labiia_lex`), desenvolvido em Python, R e CustomTkinter. O foco do projeto é a estabilidade na importação, preparação opcional do corpus e execução de análises textuais com fluxos visuais acessíveis para usuários não técnicos.

## O que o software faz

- Importa corpus em `TXT`, `PDF`, `DOCX`, `XLSX`, `CSV` e `ZIP`
- Oferece preparação opcional do corpus com expressões compostas e entidades leves
- Executa estatísticas, CHD, similitude, AFC, nuvem de palavras, mapa temático e análises auxiliares
- Empacota ajuda local, tutorial guiado e recursos de interface para uso offline
- Usa a instalação do R e do Java do sistema para processamentos pesados e renderização de grafos

## Requisitos do Sistema (Linux)

- **Python**: Versão 3.11 ou superior com suporte a Tkinter
- **R**: Versão 4.0 ou superior (com `r-base-dev` para compilação de pacotes R)
- **Java (JRE)**: Versão 11 ou superior (necessário para o layout ForceAtlas2 do Gephi)
- **Bibliotecas do Sistema**: `libxml2`, `libssl`, `libcurl`, `libfontconfig`, `libcairo`
- **Git** e **Git LFS** (para arquivos binários e de dados grandes)

## Clonar o código-fonte

Certifique-se de ter o Git LFS instalado antes de clonar:

```bash
git lfs install
git clone https://github.com/alankubrick13/labiia_lex_linux.git
cd labiia_lex_linux
git lfs pull
```

## Preparar ambiente e instalar no Linux

O repositório inclui um script instalador automático (`install.sh`) que gerencia a instalação de dependências de sistema (via `apt`, `dnf` ou `pacman`), configura o ambiente virtual Python e cria o atalho no menu de aplicativos do sistema:

```bash
bash install.sh
```

Em seguida, instale ou repare os pacotes R necessários para as análises:

```bash
source venv/bin/activate
python main.py --repair-r-packages
```

## Executar o software

Após a conclusão da instalação, você pode abrir o software diretamente pelo menu de aplicativos pesquisando por **LabiiaLex**, ou via terminal:

```bash
source venv/bin/activate
python main.py
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

## Verificações úteis

```bash
export PYTHONPATH=$(pwd)

python3 -m py_compile main.py src/ui/main_window.py src/core/version.py
python3 -m pytest -q tests
python3 main.py --self-test --json-out tmp_self_test_public.json
```

## Instalador Linux e Integração

O script `install.sh` cria um arquivo de entrada de desktop `.desktop` no padrão do Linux (localizado em `~/.local/share/applications/labiialex.desktop`), integrando o atalho do aplicativo ao menu do sistema operacional. Para quem estuda empacotamento, a estrutura original do instalador Windows Inno Setup é mantida no diretório `installer/`.

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
