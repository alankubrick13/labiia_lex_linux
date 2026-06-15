# LabiiaLex.pyw — Launcher sem janela de console.
#
# O Windows associa a extensão .pyw ao pythonw.exe (sem console).
# Clique duplo ou atalho neste arquivo abre o LabiiaLex diretamente,
# sem nenhuma janela de CMD.
#
# Variáveis de ambiente úteis:
#   LEXIANALYST_SHOW_CONSOLE=1  →  mantém console (depuração)
#   LEXIANALYST_NO_DETACH=1     →  desativa detach automático

import runpy
import os
import sys
from pathlib import Path

# Garante que o CWD é a pasta do projeto
_here = Path(__file__).resolve().parent
os.chdir(_here)
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

runpy.run_path(str(_here / "main.py"), run_name="__main__")
