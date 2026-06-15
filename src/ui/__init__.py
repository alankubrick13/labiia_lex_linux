"""
UI Package
==========

Interface grafica usando CustomTkinter.
"""

from .styles import (
    apply_theme,
    COLORS,
    FONTS,
    SIZES,
    get_font,
    get_color,
    get_current_colors,
    style_native_menu,
    get_token,
)
from .main_window import MainWindow, run_app
from .feedback import FeedbackService, MessageBoxBridge

__all__ = [
    'apply_theme',
    'COLORS',
    'FONTS',
    'SIZES',
    'get_font',
    'get_color',
    'get_token',
    'FeedbackService',
    'MessageBoxBridge',
    'MainWindow',
    'run_app',
]
