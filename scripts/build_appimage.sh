#!/usr/bin/env bash
# =============================================================================
# build_appimage.sh — Empacota labiia_lex como AppImage para Linux
#
# Pré-requisitos:
#   - Python 3.11+ com venv criado via install_linux.sh
#   - R instalado (para validação)
#   - Java 11+ instalado (para Gephi runner)
#   - appimagetool instalado em /usr/local/bin/ ou no PATH
#
# Uso: bash scripts/build_appimage.sh [--version X.Y.Z]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/venv"
DIST_DIR="$PROJECT_ROOT/dist"
APPDIR="$DIST_DIR/LabiiaLex.AppDir"

# Versão
APP_VERSION="${APP_VERSION:-$(python3 -c "import sys; sys.path.insert(0, '$PROJECT_ROOT'); from src.core.version import APP_VERSION; print(APP_VERSION)" 2>/dev/null || echo "1.0.0")}"
APP_NAME="labiia_lex"
APPIMAGE_OUT="$DIST_DIR/${APP_NAME}-${APP_VERSION}-x86_64.AppImage"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()    { echo -e "\033[1;34m[INFO]\033[0m $*"; }
success() { echo -e "\033[1;32m[ OK ]\033[0m $*"; }
warn()    { echo -e "\033[1;33m[WARN]\033[0m $*"; }
error()   { echo -e "\033[1;31m[ERR]\033[0m $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Verificações
# ---------------------------------------------------------------------------
preflight_checks() {
    info "Verificações pré-build..."
    [[ -d "$VENV_DIR" ]] || error "Ambiente virtual não encontrado em $VENV_DIR. Execute install_linux.sh primeiro."
    command -v pyinstaller &>/dev/null || "$VENV_DIR/bin/pip" install pyinstaller --quiet
    command -v appimagetool &>/dev/null || error "appimagetool não encontrado no PATH. Baixe de https://github.com/AppImage/AppImageKit/releases"
    success "Verificações OK."
}

# ---------------------------------------------------------------------------
# 2. PyInstaller — gera executável Linux
# ---------------------------------------------------------------------------
run_pyinstaller() {
    info "Rodando PyInstaller..."
    local spec_file="$PROJECT_ROOT/labiialex_app_linux.spec"

    # Gera spec se não existir
    if [[ ! -f "$spec_file" ]]; then
        info "Gerando spec do PyInstaller..."
        "$VENV_DIR/bin/pyinstaller" \
            --name "$APP_NAME" \
            --windowed \
            --noconfirm \
            --distpath "$DIST_DIR/pyinstaller" \
            --add-data "$PROJECT_ROOT/src:src" \
            --add-data "$PROJECT_ROOT/Rscripts:Rscripts" \
            --add-data "$PROJECT_ROOT/resources:resources" \
            --add-data "$PROJECT_ROOT/dictionaries:dictionaries" \
            --add-data "$PROJECT_ROOT/docs:docs" \
            --hidden-import "customtkinter" \
            --hidden-import "PIL" \
            --hidden-import "networkx" \
            --collect-all "customtkinter" \
            "$PROJECT_ROOT/main.py"
    else
        "$VENV_DIR/bin/pyinstaller" --noconfirm "$spec_file"
    fi
    success "PyInstaller concluído."
}

# ---------------------------------------------------------------------------
# 3. Montagem do AppDir
# ---------------------------------------------------------------------------
assemble_appdir() {
    info "Montando AppDir em $APPDIR..."
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/bin"
    mkdir -p "$APPDIR/usr/lib"
    mkdir -p "$APPDIR/usr/share/applications"
    mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

    # Copia executável PyInstaller
    local pyinstaller_build="$DIST_DIR/pyinstaller/$APP_NAME"
    if [[ -d "$pyinstaller_build" ]]; then
        cp -r "$pyinstaller_build"/* "$APPDIR/usr/bin/"
    else
        error "Build do PyInstaller não encontrado em $pyinstaller_build"
    fi

    # Copia ícone (cria placeholder se não existir)
    local icon_src="$PROJECT_ROOT/resources/icons/labiia_lex_256.png"
    if [[ ! -f "$icon_src" && -f "$PROJECT_ROOT/assets/icon.png" ]]; then
        icon_src="$PROJECT_ROOT/assets/icon.png"
    fi

    if [[ -f "$icon_src" ]]; then
        cp "$icon_src" "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"
        cp "$icon_src" "$APPDIR/$APP_NAME.png"
    else
        info "Gerando ícone placeholder..."
        "$VENV_DIR/bin/python" -c "
from PIL import Image
img = Image.new('RGB', (256, 256), color = (73, 109, 137))
img.save('$APPDIR/$APP_NAME.png')
"
        cp "$APPDIR/$APP_NAME.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"
    fi

    # .desktop file
    cat > "$APPDIR/$APP_NAME.desktop" <<EOF
[Desktop Entry]
Name=LabiiaLex
Comment=Análise Textual e Lexicométrica
Exec=$APP_NAME
Icon=$APP_NAME
Type=Application
Categories=Education;Science;Office;
Keywords=análise;textual;lexicometria;IRaMuTeQ;corpus;NLP;
StartupWMClass=LabiiaLex
EOF

    # Copia também para usr/share/applications
    cp "$APPDIR/$APP_NAME.desktop" "$APPDIR/usr/share/applications/"

    # AppRun — entry point
    cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
# AppRun — entry point do AppImage
APPDIR="$(dirname "$(readlink -f "$0")")"
export PATH="$APPDIR/usr/bin:$PATH"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:${LD_LIBRARY_PATH:-}"
# Dados do usuário via XDG (fora do AppImage, persistente)
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
# Fallback para R e Java do sistema se não embutidos
if [[ -z "${RSCRIPT_PATH:-}" ]]; then
    RSCRIPT_SYS=$(command -v Rscript 2>/dev/null || true)
    [[ -n "$RSCRIPT_SYS" ]] && export RSCRIPT_PATH="$RSCRIPT_SYS"
fi
exec "$APPDIR/usr/bin/labiia_lex" "$@"
EOF
    chmod +x "$APPDIR/AppRun"

    success "AppDir montado."
}

# ---------------------------------------------------------------------------
# 4. Geração do AppImage
# ---------------------------------------------------------------------------
generate_appimage() {
    info "Gerando AppImage: $APPIMAGE_OUT"
    mkdir -p "$DIST_DIR"
    ARCH=x86_64 appimagetool "$APPDIR" "$APPIMAGE_OUT"
    chmod +x "$APPIMAGE_OUT"
    success "AppImage gerado: $APPIMAGE_OUT"
    info "Tamanho: $(du -sh "$APPIMAGE_OUT" | cut -f1)"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    info "=== Build AppImage do labiia_lex v$APP_VERSION ==="
    preflight_checks
    run_pyinstaller
    assemble_appdir
    generate_appimage

    echo ""
    success "=== Build concluído! ==="
    info "Para testar: ./$APPIMAGE_OUT"
}

main "$@"
