# Instalador Windows do labiia_lex

Este diretorio documenta e preserva o processo de empacotamento do aplicativo.
O repositorio publico nao publica, nesta etapa, um `.exe` pronto para download.

## Objetivo

Gerar um instalador `.exe` via Inno Setup 6.x que:

- instala o labiia_lex por usuario em `%LOCALAPPDATA%\Programs\LabiiaLex`;
- exige apenas R 4.0+ como pre-requisito externo;
- escolhe automaticamente o R mais novo instalado no computador;
- instala automaticamente os pacotes R em biblioteca versionada dentro de
  `%LOCALAPPDATA%\LabiiaLex\R\library`;
- valida a instalacao usando `LabiiaLex.exe --self-test`;
- mantem o aplicativo instalado se pacotes R ou autoteste falharem, mostrando
  aviso claro e oferecendo reparo sem terminal pelo Menu Iniciar.

## Pre-requisitos de build

- Windows 10/11 x64
- Python do projeto com dependencias de runtime e `PyInstaller`
- Inno Setup 6.x (`ISCC.exe`)
- R 4.0+ disponivel para os testes locais
- Internet para provisao de pacotes R durante validacao completa

## Comandos de build

Build completo sem assinatura:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release_installer.ps1
```

Build reutilizando `dist\LabiiaLex` atual e compilando apenas o instalador:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -SkipPyInstaller -SkipSigning
```

Somente montar stage e validar contratos sem chamar o Inno Setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release_installer.ps1 -SkipInno -SkipSigning
```

Saida esperada:

- App empacotado: `dist\LabiiaLex\`
- Setup final: `installer\dist\labiia_lex-Setup-x64-<versao>.exe`

## Assinatura digital

Para assinar o executavel principal e o setup final, defina:

- `LEXI_SIGN_PFX_PATH`
- `LEXI_SIGN_PFX_PASSWORD`
- `LEXI_SIGN_TIMESTAMP_URL`

Sem essas variaveis, o build de release nao exige assinatura. O Windows
SmartScreen pode alertar que o aplicativo e desconhecido ate que exista
assinatura/reputacao Authenticode.

## Fluxo do instalador

1. Exibe a pagina "Verificacao do R".
2. Roda `installer\scripts\check_r.ps1`.
3. Bloqueia apenas se:
   - R nao for encontrado;
   - a versao for menor que 4.0.
4. Se o CRAN estiver inacessivel, avisa e continua a instalacao.
5. Copia os arquivos do app.
6. Executa `install_r_packages.R` com:
   - `R_LIBS_USER=%LOCALAPPDATA%\LabiiaLex\R\library`
   - fallback `binary -> source`
   - mirrors alternativos
   - lock `r_environment_lock.json`
7. Executa `LabiiaLex.exe --self-test --json-out ...`.
8. Se pacotes R ou autoteste falharem, mostra aviso com o caminho dos logs e
   preserva a instalacao.

## Validacao manual apos instalar

Validar o app instalado:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\scripts\validate_install.ps1 -ExePath "$env:LOCALAPPDATA\Programs\LabiiaLex\LabiiaLex.exe" -JsonOut "$env:TEMP\labiialex_validate_install.json"
```

Validar e abrir o app se tudo passar:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\scripts\validate_install.ps1 -ExePath "$env:LOCALAPPDATA\Programs\LabiiaLex\LabiiaLex.exe" -RunApp
```

## Instalacao silenciosa

```powershell
.\labiia_lex-Setup-x64-1.0.9.exe /VERYSILENT /NORESTART /LOG="$env:TEMP\labiialex_setup.log"
```

## Desinstalacao silenciosa

```powershell
& "$env:LOCALAPPDATA\Programs\LabiiaLex\unins000.exe" /VERYSILENT /NORESTART
```

O desinstalador remove:

- `%LOCALAPPDATA%\Programs\LabiiaLex`
- `%LOCALAPPDATA%\LabiiaLex`
- atalhos do Desktop e Menu Iniciar

## Troubleshooting

### R nao encontrado

- Instale o R em [CRAN for Windows](https://cran.r-project.org/bin/windows/base/).
- Reabra o instalador do labiia_lex.

### CRAN bloqueado

- Verifique proxy, firewall ou VPN.
- Confirme acesso a `https://cloud.r-project.org`.
- A instalacao nao deve ser removida por esse motivo. Apos restaurar internet,
  use o atalho **Reparar pacotes R do labiia_lex** no Menu Iniciar.

### Pacotes R falharam

- Consulte `%LOCALAPPDATA%\LabiiaLex\logs\r_package_install.log`.
- Use o atalho **Reparar pacotes R do labiia_lex** no Menu Iniciar.
- Se necessario, atualize o R manualmente e rode o reparo de novo; o labiia_lex
  usara automaticamente a versao mais nova instalada.

### SmartScreen

- Sem assinatura digital, o Windows pode exibir aviso do SmartScreen.
- Para distribuicao publica, assine o setup e o `LabiiaLex.exe`.

## Roteiro minimo de VM

- Windows 10 limpa com apenas R instalado
- Windows 11 limpa com apenas R instalado
- Testar:
  - bloqueio sem R
  - bloqueio com R menor que 4.0
  - instalacao completa com internet
  - instalacao sem CRAN acessivel, confirmando aviso e app preservado
  - reparo de pacotes R pelo Menu Iniciar
  - `validate_install.ps1`
  - WordCloud `cardioid`
  - CHD + AFC
  - uninstall e reinstall
