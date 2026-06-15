"""Exportador de corpus colorido por classe CHD."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Dict

from ..core.corpus import Corpus


class ColoredCorpusExporter:
    """Gera HTML navegável com UCEs coloridas por classe."""

    _PALETTE = [
        "#FFE8E8",
        "#E8F5FF",
        "#EAFCE8",
        "#FFF5D9",
        "#F3E8FF",
        "#FFEFE0",
        "#E0FFF8",
        "#FDEBFF",
    ]

    def export_html(
        self,
        corpus: Corpus,
        cluster_assignments: Dict[int, int],
        output_path: Path,
    ) -> Path:
        """Exporta corpus com segmentos coloridos por classe."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "<!doctype html>",
            "<html lang='pt-BR'>",
            "<head>",
            "  <meta charset='utf-8'>",
            "  <title>Corpus Colorido CHD</title>",
            "  <style>",
            "    body { font-family: Arial, sans-serif; margin: 24px; line-height: 1.45; }",
            "    h1 { margin-bottom: 8px; }",
            "    .uci { margin: 22px 0; padding: 12px; border: 1px solid #ddd; border-radius: 8px; }",
            "    .uci-meta { color: #444; font-size: 13px; margin-bottom: 8px; }",
            "    .uce { margin: 6px 0; padding: 8px; border-radius: 6px; }",
            "    .badge { display: inline-block; font-weight: 700; margin-right: 8px; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <h1>Corpus Colorido por Classe CHD</h1>",
            "  <p>Cada segmento (UCE) está destacado pela classe atribuída.</p>",
        ]

        for idx, uci in enumerate(corpus.ucis, start=1):
            meta = " ".join(str(token) for token in (uci.etoiles or [])).strip()
            meta = meta if meta else f"**** *uci_{idx}"
            lines.append("  <section class='uci'>")
            lines.append(f"    <div class='uci-meta'><strong>UCI {idx}:</strong> {escape(meta)}</div>")

            uce_ids = [uce.ident for uce in uci.uces]
            for uce_id, uce_text in corpus.getconcorde(uce_ids):
                class_id = int(cluster_assignments.get(int(uce_id), 0))
                color_idx = class_id % len(self._PALETTE) if class_id > 0 else 0
                background = self._PALETTE[color_idx]
                safe_text = escape(str(uce_text or "").strip())
                badge = f"Classe {class_id}" if class_id > 0 else "Sem classe"
                lines.append(
                    "    <div class='uce' "
                    f"style='background-color: {background};'>"
                    f"<span class='badge'>{escape(badge)}</span>{safe_text}</div>"
                )
            lines.append("  </section>")

        lines.extend(["</body>", "</html>"])
        output.write_text("\n".join(lines), encoding="utf-8")
        return output

