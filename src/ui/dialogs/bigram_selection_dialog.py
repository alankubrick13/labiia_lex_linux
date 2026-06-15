"""Backward-compatible import path for the multiword selection dialog."""

from __future__ import annotations

from .multiword_selection_dialog import MultiwordSelectionDialog


class BigramSelectionDialog(MultiwordSelectionDialog):
    """Compatibility wrapper for older internal imports."""
