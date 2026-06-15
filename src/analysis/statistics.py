"""
Estatisticas basicas do corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

from ..core.corpus import Corpus
from ..core.text_processor import TextProcessor
from ..core.r_executor import RExecutor, RExecutionError, RNotFoundError, RTimeoutError
from ..utils.logger import get_logger


@dataclass
class CorpusStatistics:
    """Estatisticas do corpus."""

    total_ucis: int
    total_uces: int
    total_formes: int
    total_occurrences: int
    total_hapax: int
    mean_words_per_uce: float
    vocabulary_richness: float


class StatisticsError(Exception):
    """
    Erro amigavel para estatisticas.

    Segue o padrao: o que aconteceu, por que aconteceu, como resolver.
    """

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class StatisticsAnalysis:
    """Analise de estatisticas basicas."""

    def __init__(self, corpus: Corpus, r_executor: Optional[RExecutor] = None):
        self.corpus = corpus
        self.processor = TextProcessor(corpus)
        self.r_executor = r_executor or RExecutor()
        self._logger = get_logger(__name__)

    def get_corpus_statistics(self) -> CorpusStatistics:
        """Calcula estatisticas gerais do corpus."""
        total_ucis = self.corpus.getucinb()
        total_uces = self.corpus.getucenb()
        total_formes = self.corpus.getwordnb()
        total_occurrences = self.corpus.gettokennb()
        total_hapax = len(self.corpus.get_hapaxes())

        mean_words_per_uce = (
            total_occurrences / total_uces if total_uces > 0 else 0.0
        )
        vocabulary_richness = (
            total_hapax / total_formes if total_formes > 0 else 0.0
        )

        return CorpusStatistics(
            total_ucis=total_ucis,
            total_uces=total_uces,
            total_formes=total_formes,
            total_occurrences=total_occurrences,
            total_hapax=total_hapax,
            mean_words_per_uce=mean_words_per_uce,
            vocabulary_richness=vocabulary_richness,
        )

    def get_word_frequencies(self, top_n: int = 100) -> List[Tuple[str, int]]:
        """Retorna as N palavras mais frequentes."""
        freqs = self.processor.get_word_frequencies()
        if top_n is None or top_n <= 0:
            return freqs
        return freqs[:top_n]

    def get_frequency_distribution(self) -> Dict[int, int]:
        """Distribuicao de frequencias (freq -> quantidade de palavras)."""
        distribution: Dict[int, int] = {}
        for word in self.corpus.formes.values():
            distribution[word.freq] = distribution.get(word.freq, 0) + 1
        return dict(sorted(distribution.items(), key=lambda x: x[0]))

    def get_hapax_list(self) -> List[str]:
        """Lista de hapax legomena."""
        return self.corpus.get_hapaxes()

    def export_statistics_report(self, output_path: str) -> str:
        """Exporta relatorio de estatisticas em formato texto."""
        stats = self.get_corpus_statistics()
        output = Path(output_path)

        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("w", encoding="utf-8") as file:
                file.write("LabiiaLex - Estatisticas do Corpus\n")
                file.write("=" * 40 + "\n\n")
                file.write(f"Total de UCIs: {stats.total_ucis}\n")
                file.write(f"Total de UCEs: {stats.total_uces}\n")
                file.write(f"Palavras unicas (formas): {stats.total_formes}\n")
                file.write(f"Total de ocorrencias: {stats.total_occurrences}\n")
                file.write(f"Hapax legomena: {stats.total_hapax}\n")
                file.write(
                    f"Media de palavras por UCE: {stats.mean_words_per_uce:.2f}\n"
                )
                file.write(
                    f"Riqueza vocabular (hapax/formas): {stats.vocabulary_richness:.4f}\n\n"
                )

                file.write("Distribuicao de frequencias (freq -> palavras):\n")
                for freq, count in self.get_frequency_distribution().items():
                    file.write(f"  {freq}: {count}\n")

                file.write("\nTop 100 palavras:\n")
                for word, freq in self.get_word_frequencies(100):
                    file.write(f"  {word}: {freq}\n")

            self._logger.info("Relatorio de estatisticas exportado: %s", output)
            return str(output)

        except OSError as exc:
            raise StatisticsError(
                what="Nao foi possivel salvar o relatorio de estatisticas.",
                why=str(exc),
                how="Verifique se o caminho de saida existe e se ha permissao de escrita.",
            ) from exc

    def generate_graphs(
        self,
        output_dir: Path,
        typegraph: str = "png",
        width: int = 800,
        height: int = 600,
    ) -> Dict[str, Path]:
        """
        Gera graficos de estatisticas via R (Zipf e distribuicao de tamanho de UCE).

        Returns:
            Dict com caminhos existentes para:
            - zipf
            - uce_size_distribution
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        graph_type = str(typegraph or "png").strip().lower()
        if graph_type not in {"png", "svg"}:
            graph_type = "png"

        freq_csv = out_dir / "statistics_freq.csv"
        sizes_csv = out_dir / "statistics_uce_sizes.csv"
        zipf_out = out_dir / f"statistics_zipf.{graph_type}"
        sizes_out = out_dir / f"statistics_uce_sizes.{graph_type}"

        try:
            self._write_frequency_csv(freq_csv)
            self._write_uce_sizes_csv(sizes_csv)
            script_path = self._write_statistics_script(
                output_dir=out_dir,
                freq_csv=freq_csv,
                sizes_csv=sizes_csv,
                zipf_out=zipf_out,
                sizes_out=sizes_out,
                typegraph=graph_type,
                width=int(width),
                height=int(height),
            )

            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(out_dir),
                timeout=300,
            )
        except RNotFoundError as exc:
            raise StatisticsError(
                what="R nao encontrado para gerar graficos de estatisticas.",
                why=str(exc),
                how="Instale/configure o R e tente novamente.",
            ) from exc
        except RTimeoutError as exc:
            raise StatisticsError(
                what="Tempo limite excedido ao gerar graficos de estatisticas.",
                why=str(exc),
                how="Tente novamente com corpus menor ou ajuste o ambiente.",
            ) from exc
        except RExecutionError as exc:
            raise StatisticsError(
                what="Falha ao executar script R de estatisticas.",
                why=str(exc),
                how="Verifique pacotes R instalados e tente novamente.",
            ) from exc
        except OSError as exc:
            raise StatisticsError(
                what="Falha ao preparar dados de estatisticas para grafico.",
                why=str(exc),
                how="Verifique permissao de escrita no diretorio de saida.",
            ) from exc

        generated: Dict[str, Path] = {}
        if zipf_out.exists():
            generated["zipf"] = zipf_out
        if sizes_out.exists():
            generated["uce_size_distribution"] = sizes_out
        return generated

    def _write_frequency_csv(self, path: Path) -> None:
        freqs = self.processor.get_word_frequencies()
        with path.open("w", encoding="utf-8") as file:
            file.write("word;freq\n")
            for word, freq in freqs:
                sanitized = str(word).replace(";", ",")
                file.write(f"{sanitized};{int(freq)}\n")

    def _write_uce_sizes_csv(self, path: Path) -> None:
        token_pattern = re.compile(r"\b[a-zA-ZÀ-ÿ]+\b")
        with path.open("w", encoding="utf-8") as file:
            file.write("size\n")
            for _uce_id, text in self.corpus.get_uces():
                size = sum(
                    1 for token in token_pattern.findall((text or "").lower())
                    if len(token) > 0
                )
                file.write(f"{int(size)}\n")

    @staticmethod
    def _write_statistics_script(
        output_dir: Path,
        freq_csv: Path,
        sizes_csv: Path,
        zipf_out: Path,
        sizes_out: Path,
        typegraph: str,
        width: int,
        height: int,
    ) -> Path:
        def open_device(path: Path) -> str:
            if typegraph == "svg":
                return f"svg('{path.name}', width={max(width, 200)}/72, height={max(height, 200)}/72)"
            return f"png('{path.name}', width={max(width, 200)}, height={max(height, 200)}, units='px', res=200)"

        lines = [
            "# Generated by LabiiaLex - Statistics Graphs",
            f"setwd('{output_dir.as_posix()}')",
            f"freq <- read.csv('{freq_csv.name}', sep=';', header=TRUE, stringsAsFactors=FALSE)",
            "freq <- freq[order(-freq$freq), ]",
            "if (nrow(freq) > 0) {",
            f"  {open_device(zipf_out)}",
            "  rank <- 1:nrow(freq)",
            "  y <- pmax(as.numeric(freq$freq), 1)",
            "  plot(log(rank), log(y), type='l', lwd=2, col='steelblue',",
            "       xlab='log(rank)', ylab='log(freq)', main='Distribuição de Zipf')",
            "  grid()",
            "  dev.off()",
            "}",
            "",
            f"sizes <- read.csv('{sizes_csv.name}', sep=';', header=TRUE, stringsAsFactors=FALSE)",
            "if (nrow(sizes) > 0) {",
            f"  {open_device(sizes_out)}",
            "  barplot(table(sizes$size), col='gray70', border='white',",
            "          xlab='Número de formas por UCE', ylab='Frequência',",
            "          main='Distribuição de tamanho das UCEs')",
            "  dev.off()",
            "}",
        ]
        script_path = output_dir / "statistics_graphs_script.R"
        script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return script_path
