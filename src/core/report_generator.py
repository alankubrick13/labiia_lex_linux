"""HTML report generation for analysis outputs."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import html
import mimetypes
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


class ReportGeneratorError(Exception):
    """Friendly error for report generation."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class ReportGenerator:
    """Generate formatted HTML reports for analysis results."""

    TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ font-family: "Segoe UI", Arial, sans-serif; max-width: 1100px; margin: 24px auto; color: #1f2937; }}
    h1, h2, h3 {{ color: #0f172a; }}
    h1 {{ border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
    .meta {{ color: #64748b; margin-bottom: 16px; }}
    .card {{ border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; margin: 12px 0; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f1f5f9; }}
    .muted {{ color: #6b7280; font-size: 0.95em; }}
    .positive {{ background: #dcfce7; }}
    .negative {{ background: #fee2e2; }}
    img {{ max-width: 100%; border: 1px solid #e2e8f0; border-radius: 8px; }}
    pre {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <div class="meta">Gerado em {generated_at}</div>
  {content}
</body>
</html>
"""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_statistics_report(
        self,
        stats: Dict[str, Any],
        graphs: Optional[Dict[str, Path]] = None,
        analysis_name: str = "Estatísticas",
        params: Optional[Dict[str, Any]] = None,
    ) -> Path:
        sections: List[str] = []
        sections.append(self._card("Resumo", self._kv_table(stats)))
        if params:
            sections.append(self._card("Parâmetros", self._kv_table(params)))

        graph_html = self._images_block(graphs or {})
        if graph_html:
            sections.append(self._card("Gráficos", graph_html))

        return self._write_html(
            title=f"{analysis_name} - Relatório",
            content="\n".join(sections),
            stem="statistics_report",
        )

    def generate_chd_report(
        self,
        result: Any,
        analysis_name: str = "CHD",
        params: Optional[Dict[str, Any]] = None,
        result_path: Optional[Path] = None,
    ) -> Path:
        sections: List[str] = []
        if params:
            sections.append(self._card("Parâmetros", self._kv_table(params)))

        class_sizes = getattr(result, "class_sizes", {}) or {}
        if class_sizes:
            sections.append(self._card("Tamanho das Classes", self._kv_table(class_sizes)))

        profiles = getattr(result, "profiles", {}) or {}
        if profiles:
            sections.append(self._card("Perfis Lexicais (Top 12)", self._render_chd_profiles(profiles, top_n=12)))

        images: Dict[str, Path] = {}
        dendrogram = getattr(result, "dendrogram_path", None) or result_path
        afc = getattr(result, "afc_graph_path", None) or getattr(result, "profile_afc_path", None)
        if dendrogram and Path(dendrogram).exists():
            images["Dendrograma"] = Path(dendrogram)
        if afc and Path(afc).exists():
            images["AFC pós-CHD"] = Path(afc)
        if images:
            sections.append(self._card("Visualizações", self._images_block(images)))

        metadata_profiles = getattr(result, "metadata_profiles_path", None)
        if metadata_profiles and Path(metadata_profiles).exists():
            sections.append(
                self._card(
                    "Perfil de Variáveis",
                    self._csv_table(Path(metadata_profiles), delimiter=";", max_rows=80),
                )
            )

        typical_segments = getattr(result, "typical_segments", {}) or {}
        if typical_segments:
            sections.append(
                self._card(
                    "Segmentos Típicos",
                    self._render_segments(typical_segments),
                )
            )

        return self._write_html(
            title=f"{analysis_name} - Relatório",
            content="\n".join(sections),
            stem="chd_report",
        )

    def generate_chi2_report(
        self,
        result: Any,
        analysis_name: str = "Qui-Quadrado",
        params: Optional[Dict[str, Any]] = None,
    ) -> Path:
        sections: List[str] = []
        if params:
            sections.append(self._card("Parâmetros", self._kv_table(params)))

        summary = {
            "variável_linha": getattr(result, "row_var", ""),
            "variável_coluna": getattr(result, "col_var", ""),
            "chi2": getattr(result, "chi2", ""),
            "dof": getattr(result, "dof", ""),
            "p_value": getattr(result, "p_value", ""),
        }
        sections.append(self._card("Resumo Estatístico", self._kv_table(summary)))

        graph_path = getattr(result, "graph_path", None)
        if graph_path:
            sections.append(self._card("Gráfico", self._images_block({"Mosaico": Path(graph_path)})))

        for label, path in (
            ("Tabela de Contingência", getattr(result, "contingency_csv_path", None)),
            ("Valores Esperados", getattr(result, "expected_csv_path", None)),
            ("Resíduos Padronizados", getattr(result, "residuals_csv_path", None)),
        ):
            if path and Path(path).exists():
                sections.append(self._card(label, self._csv_table(Path(path), delimiter=";", max_rows=80)))

        return self._write_html(
            title=f"{analysis_name} - Relatório",
            content="\n".join(sections),
            stem="chi2_report",
        )

    def generate_voyant_suite_report(
        self,
        *,
        result: Any,
        analysis_name: str = "Pacote Voyant",
        params: Optional[Dict[str, Any]] = None,
    ) -> Path:
        sections: List[str] = []
        if params:
            sections.append(self._card("Parâmetros", self._kv_table(params)))

        payload = getattr(result, "voyant_suite_payload_v1", {}) if result is not None else {}
        if not isinstance(payload, dict):
            payload = {}
        meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
        if meta:
            summary_meta = {
                "corpus": meta.get("corpus_name", ""),
                "documentos": meta.get("doc_count", ""),
                "tokens": meta.get("tokens", ""),
                "bins": meta.get("bins", ""),
                "janela_contexto": meta.get("context_window", ""),
                "modo": meta.get("mode", ""),
                "gerado_em": meta.get("generated_at", ""),
            }
            sections.append(self._card("Resumo da Suíte", self._kv_table(summary_meta)))

        panel_order = payload.get("graph_tabs", [])
        if not isinstance(panel_order, list) or not panel_order:
            panel_order = ["termsberry", "trends", "document_terms", "bubblelines", "cooccurrences"]
        graphs = payload.get("graphs", {}) if isinstance(payload.get("graphs", {}), dict) else {}
        tables = payload.get("tables", {}) if isinstance(payload.get("tables", {}), dict) else {}

        for panel_id in panel_order:
            graph_info = graphs.get(str(panel_id), {}) if isinstance(graphs.get(str(panel_id), {}), dict) else {}
            table_info = tables.get(str(panel_id), {}) if isinstance(tables.get(str(panel_id), {}), dict) else {}
            panel_title = str(
                graph_info.get("title_pt")
                or table_info.get("title_pt")
                or str(panel_id)
            )
            body_chunks: List[str] = []

            stats = graph_info.get("stats", {}) if isinstance(graph_info.get("stats", {}), dict) else {}
            if stats:
                body_chunks.append("<h3>Estatísticas do painel</h3>")
                body_chunks.append(self._kv_table(stats))

            graph_path = graph_info.get("image_path")
            if graph_path:
                image_path = Path(str(graph_path))
                body_chunks.append("<h3>Gráfico</h3>")
                body_chunks.append(self._images_block({"Gráfico": image_path}))
                body_chunks.append(
                    f"<p class=\"muted\">Arquivo: {html.escape(str(image_path))}</p>"
                )

            table_path = table_info.get("csv_path")
            if table_path:
                csv_path = Path(str(table_path))
                body_chunks.append("<h3>Tabela</h3>")
                body_chunks.append(self._csv_table(csv_path, delimiter=";", max_rows=80))
                body_chunks.append(
                    f"<p class=\"muted\">Arquivo: {html.escape(str(csv_path))}</p>"
                )

            extra_csv = table_info.get("extra_csv", [])
            if isinstance(extra_csv, list):
                for extra in extra_csv:
                    if not isinstance(extra, dict):
                        continue
                    extra_path = extra.get("csv_path")
                    if not extra_path:
                        continue
                    extra_title = str(extra.get("title_pt", extra.get("id", "Tabela complementar")))
                    csv_path = Path(str(extra_path))
                    body_chunks.append(f"<h3>{html.escape(extra_title)}</h3>")
                    body_chunks.append(self._csv_table(csv_path, delimiter=";", max_rows=80))
                    body_chunks.append(
                        f"<p class=\"muted\">Arquivo: {html.escape(str(csv_path))}</p>"
                    )

            if not body_chunks:
                body_chunks.append('<p class="muted">Sem dados disponíveis para este painel.</p>')
            sections.append(self._card(panel_title, "".join(body_chunks)))

        return self._write_html(
            title=f"{analysis_name} - Relatório",
            content="\n".join(sections),
            stem="voyant_suite_report",
        )

    def generate_generic_report(
        self,
        analysis_name: str,
        analysis_type: str,
        params: Optional[Dict[str, Any]],
        result: Any,
        result_path: Optional[Path] = None,
    ) -> Path:
        sections: List[str] = []
        if params:
            sections.append(self._card("Parâmetros", self._kv_table(params)))

        summary = self._extract_scalar_attrs(result)
        if summary:
            sections.append(self._card("Resumo", self._kv_table(summary)))

        images, tables, texts = self._collect_result_artifacts(
            result=result,
            result_path=Path(result_path) if result_path else None,
        )
        if images:
            sections.append(self._card("Visualizações", self._images_block(images)))
        if tables:
            table_chunks: List[str] = []
            for label, path in tables.items():
                suffix = path.suffix.lower()
                table_chunks.append(f"<h3>{html.escape(label)}</h3>")
                if suffix == ".csv":
                    table_chunks.append(self._csv_table(path, delimiter=";", max_rows=120))
                else:
                    table_chunks.append(
                        f'<p class="muted">Arquivo de dados: {html.escape(str(path))}</p>'
                    )
            sections.append(self._card("Tabelas", "".join(table_chunks)))
        if texts:
            text_chunks: List[str] = []
            for label, path in texts.items():
                text_chunks.append(f"<h3>{html.escape(label)}</h3>")
                if path.suffix.lower() in {".txt", ".log", ".md"}:
                    try:
                        content = path.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        content = ""
                    if content:
                        text_chunks.append(f"<pre>{html.escape(content[:12000])}</pre>")
                    else:
                        text_chunks.append(
                            f'<p class="muted">Arquivo textual: {html.escape(str(path))}</p>'
                        )
                else:
                    text_chunks.append(
                        f'<p class="muted">Arquivo: {html.escape(str(path))}</p>'
                    )
            sections.append(self._card("Saídas textuais", "".join(text_chunks)))

        return self._write_html(
            title=f"{analysis_name} - Relatório",
            content="\n".join(sections),
            stem=f"{analysis_type or 'analysis'}_report",
        )

    def _write_html(self, title: str, content: str, stem: str) -> Path:
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            path = self.output_dir / f"{stem}_{timestamp}.html"
            rendered = self.TEMPLATE.format(
                title=html.escape(title),
                generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                content=content,
            )
            path.write_text(rendered, encoding="utf-8")
            return path
        except OSError as exc:
            raise ReportGeneratorError(
                what="Falha ao salvar relatório HTML.",
                why=str(exc),
                how="Verifique permissões de escrita na pasta de saída.",
            ) from exc

    @staticmethod
    def _card(title: str, body: str) -> str:
        return f'<section class="card"><h2>{html.escape(title)}</h2>{body}</section>'

    @staticmethod
    def _kv_table(data: Dict[str, Any]) -> str:
        rows = []
        for key, value in data.items():
            rows.append(
                f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
            )
        if not rows:
            return '<p class="muted">Sem dados.</p>'
        return "<table><tbody>" + "".join(rows) + "</tbody></table>"

    def _images_block(self, images: Dict[str, Path]) -> str:
        blocks: List[str] = []
        for label, path in images.items():
            if not path or not Path(path).exists():
                continue
            uri = self._image_to_data_uri(Path(path))
            if not uri:
                continue
            blocks.append(
                f"<h3>{html.escape(label)}</h3><img src=\"{uri}\" alt=\"{html.escape(label)}\" />"
            )
        return "".join(blocks) if blocks else '<p class="muted">Sem imagens disponíveis.</p>'

    @staticmethod
    def _image_to_data_uri(path: Path) -> Optional[str]:
        try:
            data = path.read_bytes()
        except OSError:
            return None
        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "application/octet-stream"
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @staticmethod
    def _csv_table(path: Path, delimiter: str = ";", max_rows: int = 100) -> str:
        import csv

        try:
            with path.open("r", encoding="utf-8", newline="") as file:
                sample = file.read(2048)
                file.seek(0)
                if delimiter not in sample and "," in sample:
                    delimiter = ","
                reader = csv.reader(file, delimiter=delimiter)
                rows = list(reader)
        except OSError:
            return '<p class="muted">Falha ao ler tabela CSV.</p>'

        if not rows:
            return '<p class="muted">Tabela vazia.</p>'

        header = rows[0]
        body_rows = rows[1:max_rows + 1]
        header_html = "".join(f"<th>{html.escape(str(col))}</th>" for col in header)
        lines = [f"<table><thead><tr>{header_html}</tr></thead><tbody>"]
        for row in body_rows:
            cells = "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row)
            lines.append(f"<tr>{cells}</tr>")
        lines.append("</tbody></table>")
        if len(rows) > max_rows + 1:
            lines.append(f'<p class="muted">Mostrando {max_rows} de {len(rows)-1} linhas.</p>')
        return "".join(lines)

    @staticmethod
    def _render_chd_profiles(profiles: Dict[int, Any], top_n: int = 12) -> str:
        chunks: List[str] = []
        for class_id in sorted(profiles.keys()):
            rows = profiles.get(class_id, [])[:top_n]
            chunks.append(f"<h3>Classe {class_id}</h3>")
            chunks.append("<table><thead><tr><th>Palavra</th><th>Chi²</th><th>Freq</th><th>% Classe</th><th>Sinal</th></tr></thead><tbody>")
            for word, chi2, freq, pct, sign in rows:
                klass = "positive" if str(sign) == "+" else "negative"
                chunks.append(
                    "<tr>"
                    f"<td>{html.escape(str(word))}</td>"
                    f"<td class=\"{klass}\">{float(chi2):.4f}</td>"
                    f"<td>{int(freq)}</td>"
                    f"<td>{float(pct):.2f}</td>"
                    f"<td>{html.escape(str(sign))}</td>"
                    "</tr>"
                )
            chunks.append("</tbody></table>")
        return "".join(chunks) if chunks else '<p class="muted">Sem perfis disponíveis.</p>'

    @staticmethod
    def _render_segments(segments_by_class: Dict[int, Iterable[Any]]) -> str:
        blocks: List[str] = []
        for class_id in sorted(segments_by_class.keys()):
            blocks.append(f"<h3>Classe {class_id}</h3>")
            lines = []
            for idx, item in enumerate(list(segments_by_class.get(class_id, []))[:12], start=1):
                text, score = item
                lines.append(f"{idx:02d}. score={float(score):.3f} | {str(text).strip()}")
            if lines:
                blocks.append("<pre>" + html.escape("\n".join(lines)) + "</pre>")
            else:
                blocks.append('<p class="muted">Sem segmentos.</p>')
        return "".join(blocks) if blocks else '<p class="muted">Sem segmentos típicos.</p>'

    @staticmethod
    def _extract_scalar_attrs(result: Any) -> Dict[str, Any]:
        if result is None:
            return {}
        summary: Dict[str, Any] = {}
        for attr in dir(result):
            if attr.startswith("_"):
                continue
            try:
                value = getattr(result, attr)
            except Exception:
                continue
            if callable(value):
                continue
            if isinstance(value, (str, int, float, bool)):
                summary[attr] = value
            elif hasattr(value, "shape"):
                try:
                    shape = getattr(value, "shape")
                    if isinstance(shape, tuple):
                        summary[f"{attr}_shape"] = "x".join(str(int(x)) for x in shape)
                except Exception:
                    continue
        return summary

    def _collect_result_artifacts(
        self,
        *,
        result: Any,
        result_path: Optional[Path],
    ) -> Tuple[Dict[str, Path], Dict[str, Path], Dict[str, Path]]:
        images: Dict[str, Path] = {}
        tables: Dict[str, Path] = {}
        texts: Dict[str, Path] = {}
        seen: Set[str] = set()

        def normalize_label(raw: str) -> str:
            text = str(raw or "").strip().replace("_", " ")
            return text[:1].upper() + text[1:] if text else "Resultado"

        def register(label: str, path_value: Any) -> None:
            if not path_value:
                return
            candidate = Path(str(path_value))
            if not candidate.exists() or not candidate.is_file():
                return
            try:
                key = str(candidate.resolve())
            except Exception:
                key = str(candidate)
            if key in seen:
                return
            seen.add(key)
            suffix = candidate.suffix.lower()
            if suffix in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"}:
                images[normalize_label(label)] = candidate
            elif suffix in {".csv", ".tsv", ".xlsx"}:
                tables[normalize_label(label)] = candidate
            elif suffix in {".txt", ".log", ".json", ".html", ".htm", ".md", ".net"}:
                texts[normalize_label(label)] = candidate

        def walk(name: str, value: Any) -> None:
            if value is None:
                return
            if isinstance(value, (str, Path)):
                register(name, value)
                return
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    walk(f"{name} {child_key}".strip(), child_value)
                return
            if isinstance(value, (list, tuple, set)):
                for idx, item in enumerate(value, start=1):
                    walk(f"{name} {idx}".strip(), item)
                return

        if result_path is not None:
            register("Resultado", result_path)

        if isinstance(result, dict):
            for key, value in result.items():
                key_name = str(key)
                is_artifact_key = (
                    "path" in key_name.lower()
                    or "file" in key_name.lower()
                    or key_name.lower() in {"graphs", "tables"}
                )
                if is_artifact_key:
                    walk(key_name, value)
            return images, tables, texts

        if result is None:
            return images, tables, texts

        for attr in dir(result):
            if attr.startswith("_"):
                continue
            lowered = attr.lower()
            if "path" not in lowered and "file" not in lowered:
                continue
            try:
                value = getattr(result, attr)
            except Exception:
                continue
            walk(attr, value)

        return images, tables, texts
