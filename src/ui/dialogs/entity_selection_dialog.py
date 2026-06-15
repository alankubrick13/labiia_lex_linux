"""Dialog for selecting optional light named entities to preserve."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable

from .multiword_selection_dialog import MultiwordSelectionDialog


class EntitySelectionDialog(MultiwordSelectionDialog):
    """Compatibility wrapper that reuses the candidate table for entities."""

    def __init__(
        self,
        parent,
        candidates: List[Dict[str, Any]],
        on_confirm: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        title: str = "Selecionar entidades nomeadas",
    ):
        self._raw_entities = [dict(item or {}) for item in candidates or []]
        rows = []
        for item in self._raw_entities:
            entity = str(item.get("entity", "") or "").strip()
            if not entity:
                continue
            rows.append(
                {
                    "expression": entity,
                    "replacement": str(item.get("replacement", "") or entity.replace(" ", "_")),
                    "n_tokens": len([part for part in entity.split() if part]) or 1,
                    "frequency": int(item.get("frequency", 0) or 0),
                    "doc_count": int(item.get("doc_count", 0) or 0),
                    "is_score": float(item.get("score", 0.0) or 0.0),
                    "is_norm": float(item.get("score", 0.0) or 0.0),
                    "method": str(item.get("entity_type", "light_named_entity") or "light_named_entity"),
                    "selected_default": bool(item.get("selected_default", False)),
                    "context_examples": list(item.get("context_examples", []) or []),
                }
            )
        self._entity_by_name = {str(item.get("entity", "") or "").strip(): item for item in self._raw_entities}
        super().__init__(
            parent,
            rows,
            on_confirm=None,
            title=title,
            min_freq=1,
            min_is_norm=0.0,
            header_text="Entidades nomeadas",
            description_text=(
                "Selecione nomes, instituições e siglas que devem ser preservados por underscore (_). "
                "A seleção só será aplicada depois da confirmação."
            ),
            apply_button_text="Aplicar entidades",
            item_label_singular="entidade",
            item_label_plural="entidades",
        )
        if on_confirm and self.was_confirmed():
            on_confirm(self.get_selected_entities())

    def get_selected_entities(self) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        for row in self.get_selected_bigrams():
            expression = str(row.get("expression", "") or "").strip()
            raw = dict(self._entity_by_name.get(expression, {}))
            if raw:
                selected.append(raw)
        return selected
