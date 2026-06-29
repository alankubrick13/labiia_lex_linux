#!/usr/bin/env bash
# =============================================================================
# install_linux.sh — Instala dependências de sistema para o labiia_lex no Linux
#
# Suporta: Debian/Ubuntu (apt), Fedora/RHEL (dnf), Arch Linux (pacman)
# Uso:   bash scripts/install_linux.sh
# =============================================================================
set -euo pipefail

PYTHON_MIN="3.11"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()    { echo -e "\033[1;34m[INFO]\033[0m $*"; }
success() { echo -e "\033[1;32m[ OK ]\033[0m $*"; }
warn()    { echo -e "\033[1;33m[WARN]\033[0m $*"; }
error()   { echo -e "\033[1;31m[ERR]\033[0m $*" >&2; exit 1; }

require_cmd() {
    command -v "$1" &>/dev/null || error "Comando '$1' não encontrado. Instale-o e tente novamente."
}

# ---------------------------------------------------------------------------
# Detecção do gerenciador de pacotes
# ---------------------------------------------------------------------------
detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v pacman &>/dev/null; then
        echo "pacman"
    else
        echo "unknown"
    fi
}

PKG_MGR="$(detect_pkg_manager)"
info "Gerenciador de pacotes detectado: $PKG_MGR"

# ---------------------------------------------------------------------------
# Instalação de dependências de sistema
# ---------------------------------------------------------------------------
install_system_deps() {
    info "Instalando dependências de sistema..."

    case "$PKG_MGR" in
        apt)
            sudo apt-get update -q
            sudo apt-get install -y \
                python3 python3-venv python3-tk python3-dev \
                r-base r-base-dev \
                default-jre-headless \
                libxml2-dev libssl-dev libcurl4-openssl-dev \
                libfontconfig1-dev libfreetype6-dev \
                libharfbuzz-dev libfribidi-dev \
                libtiff5-dev libjpeg-dev libpng-dev \
                libcairo2-dev \
                git git-lfs curl wget
            ;;
        dnf)
            sudo dnf install -y \
                python3 python3-devel python3-tkinter \
                R R-devel \
                java-17-openjdk-headless \
                libxml2-devel openssl-devel libcurl-devel \
                fontconfig-devel freetype-devel \
                harfbuzz-devel fribidi-devel \
                libtiff-devel libjpeg-devel libpng-devel \
                cairo-devel \
                git git-lfs curl wget
            ;;
        pacman)
            sudo pacman -Sy --noconfirm \
                python tk \
                r \
                jre17-openjdk-headless \
                libxml2 openssl curl \
                fontconfig freetype2 \
                harfbuzz fribidi \
                libtiff libjpeg-turbo libpng \
                cairo \
                git git-lfs curl wget
            ;;
        *)
            warn "Gerenciador de pacotes desconhecido. Instale manualmente:"
            warn "  Python >= 3.11 com suporte a Tkinter"
            warn "  R >= 4.0 com r-base-dev"
            warn "  Java >= 11 (JRE headless)"
            warn "  Bibliotecas: libxml2, libssl, libcurl, libfontconfig, libcairo"
            warn "  Git LFS (git-lfs)"
            ;;
    esac
    success "Dependências de sistema instaladas."
}

# ---------------------------------------------------------------------------
# Ambiente Python virtual
# ---------------------------------------------------------------------------
create_venv() {
    VENV_DIR="$PROJECT_ROOT/venv"
    info "Criando ambiente virtual Python em $VENV_DIR..."

    if [[ -d "$VENV_DIR" ]]; then
        warn "Ambiente virtual já existe em $VENV_DIR. Pulando criação."
    else
        python3 -m venv "$VENV_DIR"
        success "Ambiente virtual criado."
    fi

    info "Instalando dependências Python..."
    "$VENV_DIR/bin/pip" install --upgrade pip --quiet
    "$VENV_DIR/bin/pip" install -r "$PROJECT_ROOT/requirements.txt" --quiet
    success "Dependências Python instaladas."
}

# ---------------------------------------------------------------------------
# Verificação do R e Java
# ---------------------------------------------------------------------------
verify_r() {
    info "Verificando R..."
    if command -v Rscript &>/dev/null; then
        R_VER=$(Rscript --version 2>&1 | grep -oP '\d+\.\d+\.\d+' | head -1)
        success "R encontrado: Rscript (versão $R_VER)"
    else
        warn "Rscript não encontrado no PATH. Instale o R e certifique-se que está no PATH."
        warn "Debian/Ubuntu: sudo apt-get install r-base"
        warn "Fedora/RHEL:  sudo dnf install R"
        warn "Arch Linux:   sudo pacman -S r"
    fi
}

verify_java() {
    info "Verificando Java..."
    if command -v java &>/dev/null; then
        JAVA_VER=$(java -version 2>&1 | grep -oP '(?<=version ")[^"]+' | head -1)
        success "Java encontrado: java (versão $JAVA_VER)"
    else
        warn "Java não encontrado no PATH. O layout Gephi ForceAtlas2 requer Java >= 11."
        warn "Debian/Ubuntu: sudo apt-get install default-jre-headless"
        warn "Fedora/RHEL:  sudo dnf install java-17-openjdk-headless"
        warn "Arch Linux:   sudo pacman -S jre17-openjdk-headless"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    info "=== Instalação do labiia_lex para Linux ==="
    info "Projeto em: $PROJECT_ROOT"
    echo ""

    install_system_deps
    create_venv
    verify_r
    verify_java

    echo ""
    success "=== Instalação concluída! ==="
    info "Para executar o labiia_lex:"
    info "  source venv/bin/activate"
    info "  python main.py"
    echo ""
    info "Para instalar pacotes R necessários, execute dentro do projeto:"
    info "  python main.py --repair-r-packages"
}

main "$@"
