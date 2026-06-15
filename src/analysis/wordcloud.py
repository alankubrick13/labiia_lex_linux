"""
Geracao de nuvem de palavras.
Usa script R: Rgraph.R (via gerador de scripts).
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..core.corpus import Corpus
from ..core.text_processor import TextProcessor
from ..core.r_script_generator import RScriptGenerator
from ..core.r_executor import RExecutor, RExecutionError, RNotFoundError, RTimeoutError
from ..utils.logger import get_logger


def _trim_wordcloud_whitespace(image_path: Path, padding: int = 24) -> None:
    """Remove o excesso de borda branca ao redor da nuvem de palavras.

    O ``ggwordcloud`` salva a nuvem dentro de um PNG quadrado, mas o algoritmo
    de packing deixa bordas brancas consideraveis (topo/lados) pois o layout
    dos termos nao preenche o canvas inteiro. Ao cropar para o bounding box do
    conteudo nao-branco, a imagem final ocupa melhor a area da UI.

    Aplica apenas em PNGs; SVG e preservado. Falha silenciosamente se PIL nao
    estiver disponivel ou se a imagem ja estiver toda branca.
    """
    try:
        from PIL import Image, ImageChops
    except Exception:
        return
    try:
        if image_path.suffix.lower() != ".png":
            return
        with Image.open(image_path) as im:
            rgb = im.convert("RGB")
            # Calcula bounding box comparando contra um canvas branco puro.
            bg = Image.new("RGB", rgb.size, (255, 255, 255))
            diff = ImageChops.difference(rgb, bg)
            bbox = diff.getbbox()
            if not bbox:
                return
            left, top, right, bottom = bbox
            w, h = rgb.size
            # Restaura uma margem discreta ao redor do conteudo.
            left = max(0, left - padding)
            top = max(0, top - padding)
            right = min(w, right + padding)
            bottom = min(h, bottom + padding)
            cropped = im.crop((left, top, right, bottom))
            cropped.save(image_path, optimize=True)
    except Exception:
        # Trim e cosmetico; jamais bloqueia a analise.
        return


@dataclass
class WordCloudResult:
    """Resultado da geracao de word cloud."""

    image_path: Path
    word_frequencies: Dict[str, int]
    words_displayed: int


class WordCloudAnalysisError(Exception):
    """
    Erro amigavel para geracao de word cloud.

    Segue o padrao: o que aconteceu, por que aconteceu, como resolver.
    """

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class WordCloudAnalysis:
    """Geracao de nuvem de palavras."""

    DEFAULT_PARAMS = {
        "max_words":           100,
        "min_freq":            3,
        "active_only":         True,
        "use_lemmas":          True,
        "scale_max":           30,
        "rotation_percentage": 0.1,
        "typegraph":           "png",
        "width":               None,
        "height":              None,
        "shape":               "square",
        "eccentricity":        0.65,
        "sizing_mode":         "area",
        "colors":              "Dark2",
        "grid_size":           4,
        "max_steps":           100,
    }

    _REQUIRED_PACKAGES: List[str] = ["ggplot2", "ggwordcloud", "wordcloud2", "jsonlite"]
    _ALLOWED_SHAPES = {
        "cardioid",
        "diamond",
        "square",
        "triangle",
        "triangle-forward",
        "triangle-upright",
        "pentagon",
        "star",
    }
    _SHAPE_ALIASES = {
        "circular": "square",
        "circulo": "square",
        "círculo": "square",
        "circle": "square",
        "heart": "cardioid",
        "triangulo": "triangle",
        "triângulo": "triangle",
    }
    _ALLOWED_PALETTES = {"Dark2", "Set1", "Set2", "Paired", "Pastel1"}

    def __init__(self, corpus: Corpus, output_dir: Path, r_executor: Optional[RExecutor] = None):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.processor = TextProcessor(corpus)
        self.script_generator = RScriptGenerator()
        self.r_executor = r_executor or RExecutor()
        self._logger = get_logger(__name__)

    @staticmethod
    def _clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            parsed = int(default)
        return max(int(minimum), min(int(maximum), parsed))

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @classmethod
    def _normalize_shape(cls, value: Any, default: str = "square") -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return default
        normalized = cls._SHAPE_ALIASES.get(raw, raw)
        if normalized in cls._ALLOWED_SHAPES:
            return normalized
        return default

    def _write_render_metadata(
        self,
        output_dir: Path,
        shape_requested: str,
        shape_effective: str,
        sizing_mode: str,
        eccentricity: float,
        output_file: str,
        ok: bool,
        error: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Path:
        metadata_path = Path(output_dir) / "wordcloud_render_meta.json"
        payload: Dict[str, Any] = {}
        if metadata_path.exists():
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        payload.update({
            "shape_requested": str(shape_requested),
            "shape_effective": str(shape_effective),
            "sizing_mode": str(sizing_mode),
            "eccentricity": float(eccentricity),
            "output_file": str(output_file),
            "ok": bool(ok),
            "error": str(error or ""),
        })
        if extra:
            payload.update(extra)
        metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return metadata_path

    def _adaptive_dimensions(
        self,
        max_words: Any,
        shape: Any,
        sizing_mode: Any,
        eccentricity: Any,
    ) -> tuple[int, int]:
        words_n = self._clamp_int(max_words, minimum=20, maximum=2000, default=100)
        shape_name = str(shape or "square").strip().lower()
        mode_name = str(sizing_mode or "area").strip().lower()
        ecc = self._coerce_float(eccentricity, 0.65)

        base_words = min(words_n, 600)
        edge = 980 + int((base_words - 20) * 1.10)
        if words_n > 600:
            edge += int((words_n - 600) * 0.25)

        if shape_name in {"triangle", "triangle-forward", "triangle-upright"}:
            edge += 70
        elif shape_name in {"star", "diamond", "pentagon"}:
            edge += 50
        if mode_name == "height":
            edge += 40
        if ecc <= 0.5:
            edge += 30

        edge = max(980, min(1900, edge))
        return int(edge), int(edge)

    def _resolve_dimensions(self, config: Dict[str, Any], user_params: Optional[Dict[str, Any]]) -> tuple[int, int]:
        adaptive_w, adaptive_h = self._adaptive_dimensions(
            max_words=config.get("max_words", 100),
            shape=config.get("shape", "square"),
            sizing_mode=config.get("sizing_mode", "area"),
            eccentricity=config.get("eccentricity", 0.65),
        )
        raw_w = None if user_params is None else user_params.get("width")
        raw_h = None if user_params is None else user_params.get("height")
        if raw_w in (None, "", "None") and raw_h in (None, "", "None"):
            return adaptive_w, adaptive_h
        width = self._clamp_int(
            adaptive_w if raw_w in (None, "", "None") else raw_w,
            minimum=900,
            maximum=2400,
            default=adaptive_w,
        )
        height = self._clamp_int(
            adaptive_h if raw_h in (None, "", "None") else raw_h,
            minimum=900,
            maximum=2400,
            default=adaptive_h,
        )
        return width, height

    def _ensure_packages(self) -> None:
        """Verifica e instala ggplot2 + ggwordcloud antes da analise.

        Roda em subprocesso separado com timeout fixo de 5 minutos para
        evitar que a instalacao bloqueie indefinidamente.
        """
        status = self.r_executor.check_packages(self._REQUIRED_PACKAGES)
        missing = [p for p, ok in status.items() if not ok]
        if not missing:
            return

        self._logger.info("Instalando pacotes R ausentes: %s", missing)
        pkgs_r = ", ".join(f'"{p}"' for p in missing)
        install_code = (
            "options(timeout = 120)\n"
            ".lexi_type <- if (.Platform$OS.type == 'windows') 'binary' else 'source'\n"
            f"for (pkg in c({pkgs_r})) {{\n"
            "    if (!requireNamespace(pkg, quietly = TRUE)) {\n"
            "        install.packages(pkg,\n"
            "            repos = 'https://cloud.r-project.org',\n"
            "            type = .lexi_type,\n"
            "            dependencies = c('Depends', 'Imports', 'LinkingTo'),\n"
            "            quiet = TRUE)\n"
            "    }\n"
            "}\n"
            f"still <- c({pkgs_r})[!sapply(c({pkgs_r}), requireNamespace, quietly = TRUE)]\n"
            "if (length(still) > 0) stop(paste('Pacotes nao instalados:', paste(still, collapse=', ')))\n"
            "cat('OK\\n')\n"
        )
        tmp = Path(tempfile.mktemp(suffix=".R"))
        try:
            tmp.write_text(install_code, encoding="utf-8")
            self.r_executor.execute(str(tmp), timeout=300)
        except (RExecutionError, RTimeoutError) as exc:
            raise WordCloudAnalysisError(
                what=f"Pacotes R necessários não disponíveis: {', '.join(missing)}.",
                why="Instalação automática falhou ou excedeu 5 minutos.",
                how="Execute manualmente no R: install.packages(c('ggplot2', 'ggwordcloud'))",
            ) from exc
        finally:
            tmp.unlink(missing_ok=True)

    def run(self, params: Optional[Dict[str, Any]] = None) -> WordCloudResult:
        """Gera nuvem de palavras."""
        self._ensure_packages()
        user_params = dict(params or {})
        config = {**self.DEFAULT_PARAMS, **user_params}

        try:
            max_words = int(config.get("max_words", 100))
            min_freq = int(config.get("min_freq", 3))
            active_only = bool(config.get("active_only", True))
            use_lemmas = bool(config.get("use_lemmas", True))
            shape_requested = str(config.get("shape", "square")).strip()
            shape = self._normalize_shape(shape_requested, default="square")
            sizing_mode = str(config.get("sizing_mode", "area")).strip().lower()
            if sizing_mode not in {"area", "height"}:
                sizing_mode = "area"
            colors = str(config.get("colors", "Dark2")).strip()
            if colors not in self._ALLOWED_PALETTES:
                colors = "Dark2"
            ecc = self._coerce_float(config.get("eccentricity", 0.65), 0.65)
            ecc_candidates = [0.35, 0.65, 1.0]
            eccentricity = min(ecc_candidates, key=lambda candidate: abs(candidate - ecc))
            typegraph = str(config.get("typegraph", "png")).strip().lower()
            if typegraph not in {"png", "svg"}:
                typegraph = "png"
            graph_default = "wordcloud.svg" if typegraph == "svg" else "wordcloud.png"
            graph_out = str(config.get("graph_out") or graph_default)
            width, height = self._resolve_dimensions(config, user_params)

            freqs = self.processor.get_word_frequencies(
                use_lemmas=use_lemmas,
                active_only=active_only,
                exclude_stopwords=True,
            )
            filtered = [(w, f) for w, f in freqs if f >= min_freq]
            if max_words > 0:
                filtered = filtered[:max_words]

            data_file = self.output_dir / "words.csv"
            with data_file.open("w", encoding="utf-8") as file:
                file.write("word;freq\n")
                for word, freq in filtered:
                    file.write(f"{word};{freq}\n")

            script_params = {
                **config,
                "shape": shape,
                "shape_requested": shape_requested,
                "sizing_mode": sizing_mode,
                "colors": colors,
                "eccentricity": eccentricity,
                "width": width,
                "height": height,
                "typegraph": typegraph,
                "pathout": str(self.output_dir),
                "data_file": data_file.name,
                "graph_out": graph_out,
            }

            script_path = self.script_generator.generate_and_save(
                "wordcloud",
                script_params,
                self.output_dir / "wordcloud_script.R",
            )

            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(self.output_dir),
                timeout=600,
            )

            image_path = self.output_dir / graph_out
            
            # Verificar se o arquivo de imagem foi realmente criado
            if not image_path.exists():
                self._write_render_metadata(
                    output_dir=self.output_dir,
                    shape_requested=shape_requested,
                    shape_effective=shape,
                    sizing_mode=sizing_mode,
                    eccentricity=eccentricity,
                    output_file=graph_out,
                    ok=False,
                    error=f"arquivo de saída não encontrado: {image_path}",
                )
                raise WordCloudAnalysisError(
                    what="A imagem da nuvem de palavras nao foi gerada.",
                    why=f"O arquivo de saida nao foi encontrado: {image_path}",
                    how="Verifique se o R e os pacotes necessarios estao instalados corretamente.",
                )
            if image_path.stat().st_size <= 0:
                self._write_render_metadata(
                    output_dir=self.output_dir,
                    shape_requested=shape_requested,
                    shape_effective=shape,
                    sizing_mode=sizing_mode,
                    eccentricity=eccentricity,
                    output_file=graph_out,
                    ok=False,
                    error=f"arquivo de saída vazio: {image_path}",
                )
                raise WordCloudAnalysisError(
                    what="A imagem da nuvem de palavras foi gerada vazia.",
                    why=f"O arquivo de saida existe, mas sem conteúdo: {image_path}",
                    how="Verifique os parametros da nuvem e tente novamente.",
                )

            # Corta excesso de borda branca ao redor da nuvem (apenas PNG).
            _trim_wordcloud_whitespace(image_path)

            render_metadata: Dict[str, Any] = {}
            meta_file = self.output_dir / "wordcloud_render_meta.json"
            if meta_file.exists():
                try:
                    render_metadata = json.loads(meta_file.read_text(encoding="utf-8"))
                except Exception:
                    render_metadata = {}
            shape_effective = str(render_metadata.get("shape_effective", shape) or shape).strip().lower()
            if not shape_effective:
                shape_effective = shape
            render_metadata["shape_validation_ok"] = bool(shape_effective == shape)

            self._write_render_metadata(
                output_dir=self.output_dir,
                shape_requested=shape_requested,
                shape_effective=shape_effective,
                sizing_mode=sizing_mode,
                eccentricity=eccentricity,
                output_file=graph_out,
                ok=True,
                extra=render_metadata,
            )
            
            return WordCloudResult(
                image_path=image_path,
                word_frequencies={word: freq for word, freq in filtered},
                words_displayed=len(filtered),
            )

        except RNotFoundError as exc:
            raise WordCloudAnalysisError(
                what="R nao encontrado no sistema.",
                why=str(exc),
                how="Instale o R (4.0+) e verifique se o Rscript esta disponivel no PATH.",
            ) from exc
        except RTimeoutError as exc:
            raise WordCloudAnalysisError(
                what="Tempo limite excedido na geracao de word cloud.",
                why=str(exc),
                how="Tente reduzir o corpus ou aumente o tempo limite.",
            ) from exc
        except RExecutionError as exc:
            raise WordCloudAnalysisError(
                what="Falha na execucao do script de word cloud.",
                why=str(exc),
                how="Verifique se os pacotes R necessarios estao instalados.",
            ) from exc
        except Exception as exc:
            raise WordCloudAnalysisError(
                what="Falha ao gerar a word cloud.",
                why=str(exc),
                how="Verifique os dados exportados e tente novamente.",
            ) from exc

    def run_per_class(
        self,
        profiles: Dict[int, Any],
        output_dir: Optional[Path] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[int, Path]:
        """
        Gera nuvens por classe CHD a partir de perfis (chi2).

        O tamanho relativo da palavra e aproximado por |chi2|.
        """
        self._ensure_packages()
        user_params = dict(params or {})
        config = {**self.DEFAULT_PARAMS, **user_params}
        target_dir = Path(output_dir) if output_dir else self.output_dir / "classes"
        target_dir.mkdir(parents=True, exist_ok=True)
        generated: Dict[int, Path] = {}
        shape_requested = str(config.get("shape", "square")).strip()
        shape = self._normalize_shape(shape_requested, default="square")
        sizing_mode = str(config.get("sizing_mode", "area")).strip().lower()
        if sizing_mode not in {"area", "height"}:
            sizing_mode = "area"
        colors = str(config.get("colors", "Dark2")).strip()
        if colors not in self._ALLOWED_PALETTES:
            colors = "Dark2"
        ecc = self._coerce_float(config.get("eccentricity", 0.65), 0.65)
        ecc_candidates = [0.35, 0.65, 1.0]
        eccentricity = min(ecc_candidates, key=lambda candidate: abs(candidate - ecc))

        for class_id, rows in (profiles or {}).items():
            if not rows:
                continue

            class_words = []
            for row in rows:
                if len(row) < 2:
                    continue
                word = str(row[0]).strip()
                chi2 = abs(float(row[1]))
                if not word or chi2 <= 0:
                    continue
                pseudo_freq = max(1, int(round(chi2 * 10)))
                class_words.append((word, pseudo_freq))

            if not class_words:
                continue

            class_words.sort(key=lambda item: item[1], reverse=True)
            max_words = int(config.get("max_words", 200))
            if max_words > 0:
                class_words = class_words[:max_words]

            class_csv = target_dir / f"class_{class_id}_words.csv"
            with class_csv.open("w", encoding="utf-8") as file:
                file.write("word;freq\n")
                for word, freq in class_words:
                    file.write(f"{word};{freq}\n")

            typegraph = str(config.get("typegraph", "png")).strip().lower()
            if typegraph not in {"png", "svg"}:
                typegraph = "png"
            graph_name = (
                f"wordcloud_class_{class_id}.svg"
                if typegraph == "svg"
                else f"wordcloud_class_{class_id}.png"
            )
            width, height = self._resolve_dimensions(config, user_params)
            script_params = {
                **config,
                "shape": shape,
                "shape_requested": shape_requested,
                "sizing_mode": sizing_mode,
                "colors": colors,
                "eccentricity": eccentricity,
                "width": width,
                "height": height,
                "typegraph": typegraph,
                "pathout": str(target_dir),
                "class_label": str(class_id),
                "data_file": class_csv.name,
                "graph_out": graph_name,
            }

            script_path = self.script_generator.generate_and_save(
                "wordcloud_class",
                script_params,
                target_dir / f"wordcloud_class_{class_id}.R",
            )
            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(target_dir),
                timeout=600,
            )

            image_path = target_dir / graph_name
            if image_path.exists():
                _trim_wordcloud_whitespace(image_path)
                self._write_render_metadata(
                    output_dir=target_dir,
                    shape_requested=shape_requested,
                    shape_effective=shape,
                    sizing_mode=sizing_mode,
                    eccentricity=eccentricity,
                    output_file=graph_name,
                    ok=True,
                )
                generated[int(class_id)] = image_path

        return generated
