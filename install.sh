#!/usr/bin/env bash
# =============================================================================
# install.sh — Instalador do LabiiaLex para Linux
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Cores
info()    { echo -e "\033[1;34m[INFO]\033[0m $*"; }
success() { echo -e "\033[1;32m[ OK ]\033[0m $*"; }
warn()    { echo -e "\033[1;33m[WARN]\033[0m $*"; }
error()   { echo -e "\033[1;31m[ERR]\033[0m $*" >&2; exit 1; }

info "=== Iniciando a instalação do LabiiaLex ==="

# 1. Executar o script de instalação de dependências do sistema e venv
if [[ -f "$SCRIPT_DIR/scripts/install_linux.sh" ]]; then
    info "Executando scripts/install_linux.sh para configurar dependências e venv..."
    bash "$SCRIPT_DIR/scripts/install_linux.sh"
else
    error "Script scripts/install_linux.sh não encontrado!"
fi

# 1.5. Configurar Git LFS e baixar arquivos grandes
if command -v git-lfs &>/dev/null; then
    info "Configurando Git LFS e baixando arquivos grandes do repositório..."
    git lfs install
    git lfs pull || warn "Não foi possível rodar 'git lfs pull'. Verifique a conexão com a internet."
else
    warn "Git LFS não está instalado. Alguns arquivos binários (como gephi-runner.jar) podem estar ausentes."
fi

# 2. Gerar o ícone PNG a partir do ICO (usando Pillow instalado no venv)
info "Gerando ícone PNG a partir do ICO..."
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
ICO_PATH="$SCRIPT_DIR/assets/icon.ico"
PNG_PATH="$SCRIPT_DIR/assets/icon.png"

if [[ -f "$VENV_PYTHON" ]]; then
    if [[ -f "$ICO_PATH" ]]; then
        "$VENV_PYTHON" -c "
from PIL import Image
try:
    with Image.open('$ICO_PATH') as img:
        img.save('$PNG_PATH', 'PNG')
    print('Ícone PNG gerado com sucesso.')
except Exception as e:
    print(f'Erro ao converter ícone: {e}')
"
    else
        warn "Ícone ICO não encontrado em $ICO_PATH. O atalho usará um ícone padrão."
    fi
else
    error "Ambiente virtual Python não encontrado em $VENV_PYTHON. Instalação de dependências falhou."
fi

# 3. Criar o arquivo .desktop para integração com o menu de aplicativos
info "Criando atalho de desktop..."
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

DESKTOP_FILE="$DESKTOP_DIR/labiialex.desktop"

# Configurar o ícone a ser exibido
ICON_VAL="$PNG_PATH"
if [[ ! -f "$PNG_PATH" ]]; then
    ICON_VAL="$ICO_PATH"
fi

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=LabiiaLex
Comment=Análise Textual e Lexicométrica
Exec=$VENV_PYTHON $SCRIPT_DIR/main.py
Icon=$ICON_VAL
Type=Application
Terminal=false
Categories=Education;Science;Office;
Keywords=análise;textual;lexicometria;IRaMuTeQ;corpus;NLP;
StartupWMClass=LabiiaLex
EOF

chmod +x "$DESKTOP_FILE"
success "Atalho criado com sucesso em: $DESKTOP_FILE"

# 4. Registrar/atualizar banco de dados de atalhos se possível
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo ""
success "=== Instalação e integração com o sistema concluídas com sucesso! ==="
info "Você já pode pesquisar por 'LabiiaLex' no menu de aplicativos do seu sistema Linux."
