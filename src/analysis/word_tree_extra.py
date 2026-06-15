"""Word tree analysis focused on contextual branching around one term."""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.corpus import Corpus
from ..core.text_processor import TextProcessor
from ..utils.logger import get_logger


TOKEN_PATTERN = re.compile(r"\b[a-zA-ZÀ-ÿ]+(?:_[a-zA-ZÀ-ÿ]+)*\b")


@dataclass
class WordTreeExtraResult:
    """Result payload for word tree analysis."""

    graph_path: Optional[Path]
    table_path: Optional[Path]
    root_term: str
    root_frequency: int
    n_nodes: int
    n_edges: int


class WordTreeExtraAnalysisError(Exception):
    """Friendly error for word tree analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class WordTreeExtraAnalysis:
    """Build a word tree centered on a keyword from UCE contexts."""

    DEFAULT_PARAMS = {
        "keyword": "",
        "min_freq": 3,
        "max_depth": 4,
        "min_branch_freq": 2,
        "top_branches": 120,
        "use_lemmas": True,
        "active_only": True,
        "width": 1400,
        "height": 1000,
    }

    def __init__(self, corpus: Corpus, output_dir: Path):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._logger = get_logger(__name__)
        self.processor = TextProcessor(corpus)

    def run(self, params: Optional[Dict[str, Any]] = None) -> WordTreeExtraResult:
        """Execute word tree extraction and plotting."""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        config = {**self.DEFAULT_PARAMS, **(params or {})}
        min_freq = max(1, int(config.get("min_freq", 3)))
        max_depth = max(1, min(8, int(config.get("max_depth", 4))))
        min_branch_freq = max(1, int(config.get("min_branch_freq", 2)))
        top_branches = max(20, min(500, int(config.get("top_branches", 120))))
        use_lemmas = bool(config.get("use_lemmas", True))
        active_only = bool(config.get("active_only", True))
        keyword_raw = str(config.get("keyword", "") or "").strip().lower()

        tokenized_uces = self._build_tokenized_uces(
            min_freq=min_freq,
            use_lemmas=use_lemmas,
            active_only=active_only,
        )
        if not tokenized_uces:
            raise WordTreeExtraAnalysisError(
                what="Nao foi possivel gerar a arvore de palavras.",
                why="Nenhum segmento possui termos validos apos o filtro lexical.",
                how="Reduza a frequencia minima ou desative filtros lexicais mais restritivos.",
            )

        token_counter: Counter[str] = Counter()
        for tokens in tokenized_uces:
            token_counter.update(tokens)
        if not token_counter:
            raise WordTreeExtraAnalysisError(
                what="Nao foi possivel gerar a arvore de palavras.",
                why="Nao ha termos suficientes no corpus para montar ramificacoes.",
                how="Use um corpus com mais texto ou reduza os filtros de frequencia.",
            )

        keyword = keyword_raw if keyword_raw in token_counter else ""
        if not keyword:
            keyword = token_counter.most_common(1)[0][0]

        edge_counter = self._build_branch_edges(
            tokenized_uces=tokenized_uces,
            root=keyword,
            max_depth=max_depth,
        )
        edge_counter = {
            key: freq for key, freq in edge_counter.items() if int(freq) >= min_branch_freq
        }
        if not edge_counter:
            raise WordTreeExtraAnalysisError(
                what="Nao foi possivel gerar a arvore de palavras.",
                why="As ramificacoes ficaram abaixo do limiar minimo de frequencia.",
                how="Reduza o limiar de ramo ou selecione outro termo central.",
            )

        edge_counter = self._trim_branches(edge_counter=edge_counter, root=keyword, top_branches=top_branches)

        node_frequency = Counter()
        for (parent, child), weight in edge_counter.items():
            node_frequency[parent] += int(weight)
            node_frequency[child] += int(weight)
        node_frequency[("ROOT", (keyword,))] = max(
            int(token_counter.get(keyword, 0)),
            int(node_frequency.get(("ROOT", (keyword,)), 0)),
        )

        positions = self._layout_nodes(edge_counter=edge_counter, root=keyword, node_frequency=node_frequency)
        if not positions:
            raise WordTreeExtraAnalysisError(
                what="Nao foi possivel gerar a arvore de palavras.",
                why="A malha de layout ficou vazia apos aplicar os filtros.",
                how="Reduza os filtros ou troque o termo central.",
            )

        graph_path = self.output_dir / "word_tree_extra.png"
        table_path = self.output_dir / "word_tree_branches.csv"

        self._plot_word_tree(
            graph_path=graph_path,
            positions=positions,
            edge_counter=edge_counter,
            node_frequency=node_frequency,
            root=keyword,
            width=int(config.get("width", 1400)),
            height=int(config.get("height", 1000)),
        )
        self._export_edges_csv(table_path=table_path, edge_counter=edge_counter, root=keyword)

        return WordTreeExtraResult(
            graph_path=graph_path if graph_path.exists() else None,
            table_path=table_path if table_path.exists() else None,
            root_term=keyword,
            root_frequency=int(token_counter.get(keyword, 0)),
            n_nodes=len(positions),
            n_edges=len(edge_counter),
        )

    def _build_tokenized_uces(
        self,
        *,
        min_freq: int,
        use_lemmas: bool,
        active_only: bool,
    ) -> List[List[str]]:
        """Tokenize UCE texts and keep only vocabulary terms selected by TextProcessor."""
        self.processor.build_dtm(
            min_freq=min_freq,
            use_lemmas=use_lemmas,
            active_only=active_only,
        )
        allowed = set(self.processor.vocabulary)
        if not allowed:
            return []

        tokenized: List[List[str]] = []
        for _uce_id, text in self.corpus.get_uces():
            tokens = []
            for token in TOKEN_PATTERN.findall(str(text or "").lower()):
                normalized = self._normalize_token(token, use_lemmas=use_lemmas, active_only=active_only)
                if not normalized:
                    continue
                if normalized in allowed:
                    tokens.append(normalized)
            if tokens:
                tokenized.append(tokens)
        return tokenized

    def _normalize_token(self, token: str, *, use_lemmas: bool, active_only: bool) -> str:
        """Normalize token according to lemma and lexical activity settings."""
        clean = str(token or "").strip().lower()
        if not clean:
            return ""
        if use_lemmas:
            forme = self.corpus.formes.get(clean)
            if forme is not None and getattr(forme, "lem", None):
                clean = str(forme.lem).strip().lower()
            lem = self.corpus.lems.get(clean)
            if active_only and lem is not None and int(getattr(lem, "act", 1)) != 1:
                return ""
        else:
            forme = self.corpus.formes.get(clean)
            if active_only and forme is not None and int(getattr(forme, "act", 1)) != 1:
                return ""
        return clean

    @staticmethod
    def _build_branch_edges(
        *,
        tokenized_uces: List[List[str]],
        root: str,
        max_depth: int,
    ) -> Dict[Tuple[Tuple[str, Tuple[str, ...]], Tuple[str, Tuple[str, ...]]], int]:
        """Build directed edge frequency map for left/right contextual branches."""
        edge_counter: Dict[
            Tuple[Tuple[str, Tuple[str, ...]], Tuple[str, Tuple[str, ...]]], int
        ] = defaultdict(int)
        root_key = ("ROOT", (root,))

        for tokens in tokenized_uces:
            if root not in tokens:
                continue
            for idx, token in enumerate(tokens):
                if token != root:
                    continue

                parent = root_key
                right_path: List[str] = []
                for depth in range(1, max_depth + 1):
                    pos = idx + depth
                    if pos >= len(tokens):
                        break
                    right_path.append(tokens[pos])
                    child = ("R", tuple(right_path))
                    edge_counter[(parent, child)] += 1
                    parent = child

                parent = root_key
                left_path: List[str] = []
                for depth in range(1, max_depth + 1):
                    pos = idx - depth
                    if pos < 0:
                        break
                    left_path.append(tokens[pos])
                    child = ("L", tuple(left_path))
                    edge_counter[(parent, child)] += 1
                    parent = child

        return edge_counter

    @staticmethod
    def _trim_branches(
        *,
        edge_counter: Dict[Tuple[Tuple[str, Tuple[str, ...]], Tuple[str, Tuple[str, ...]]], int],
        root: str,
        top_branches: int,
    ) -> Dict[Tuple[Tuple[str, Tuple[str, ...]], Tuple[str, Tuple[str, ...]]], int]:
        """Keep the strongest branches and retain ancestors for continuity."""
        root_key = ("ROOT", (root,))
        child_strength = Counter()
        parent_of: Dict[Tuple[str, Tuple[str, ...]], Tuple[str, Tuple[str, ...]]] = {}
        for (parent, child), weight in edge_counter.items():
            child_strength[child] += int(weight)
            parent_of[child] = parent

        strongest_nodes = [
            node
            for node, _score in child_strength.most_common(max(1, top_branches))
        ]
        keep_nodes = {root_key}
        for node in strongest_nodes:
            current = node
            keep_nodes.add(current)
            while current in parent_of and parent_of[current] not in keep_nodes:
                current = parent_of[current]
                keep_nodes.add(current)

        filtered = {
            (parent, child): int(weight)
            for (parent, child), weight in edge_counter.items()
            if parent in keep_nodes and child in keep_nodes
        }
        return filtered

    @staticmethod
    def _layout_nodes(
        *,
        edge_counter: Dict[Tuple[Tuple[str, Tuple[str, ...]], Tuple[str, Tuple[str, ...]]], int],
        root: str,
        node_frequency: Counter,
    ) -> Dict[Tuple[str, Tuple[str, ...]], Tuple[float, float]]:
        """Position word-tree nodes in symmetric left/right columns by depth."""
        root_key = ("ROOT", (root,))
        nodes = {root_key}
        for parent, child in edge_counter.keys():
            nodes.add(parent)
            nodes.add(child)

        by_side_depth: Dict[Tuple[str, int], List[Tuple[str, Tuple[str, ...]]]] = defaultdict(list)
        for node in nodes:
            side, path = node
            if side == "ROOT":
                continue
            depth = len(path)
            by_side_depth[(side, depth)].append(node)

        positions: Dict[Tuple[str, Tuple[str, ...]], Tuple[float, float]] = {root_key: (0.0, 0.0)}
        for (side, depth), node_list in by_side_depth.items():
            node_list.sort(
                key=lambda item: (
                    -int(node_frequency.get(item, 0)),
                    str(item[1][-1] if item[1] else ""),
                )
            )
            count = len(node_list)
            spacing = 1.0 + min(2.0, depth * 0.08)
            start_y = (count - 1) / 2.0
            x_value = float(depth if side == "R" else -depth)
            for idx, node in enumerate(node_list):
                y_value = (start_y - idx) * spacing
                positions[node] = (x_value, y_value)

        return positions

    def _plot_word_tree(
        self,
        *,
        graph_path: Path,
        positions: Dict[Tuple[str, Tuple[str, ...]], Tuple[float, float]],
        edge_counter: Dict[Tuple[Tuple[str, Tuple[str, ...]], Tuple[str, Tuple[str, ...]]], int],
        node_frequency: Counter,
        root: str,
        width: int,
        height: int,
    ) -> None:
        """Render word tree to an image file."""
        import matplotlib.pyplot as plt

        fig_w = max(12.0, float(width) / 100.0)
        fig_h = max(8.0, float(height) / 100.0)
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        ax.set_facecolor("#f5f5f5")

        max_weight = max((int(w) for w in edge_counter.values()), default=1)
        for (parent, child), weight in edge_counter.items():
            if parent not in positions or child not in positions:
                continue
            x0, y0 = positions[parent]
            x1, y1 = positions[child]
            line_alpha = 0.22 + 0.58 * (float(weight) / float(max_weight))
            line_width = 0.6 + 3.0 * (float(weight) / float(max_weight))
            ax.plot(
                [x0, x1],
                [y0, y1],
                color="#7c8894",
                linewidth=line_width,
                alpha=min(0.9, line_alpha),
                solid_capstyle="round",
                zorder=1,
            )

        root_key = ("ROOT", (root,))
        root_x, root_y = positions.get(root_key, (0.0, 0.0))
        ax.text(
            root_x,
            root_y,
            root,
            fontsize=26,
            fontweight="bold",
            color="#111827",
            ha="center",
            va="center",
            zorder=3,
        )

        max_node_score = max((int(v) for v in node_frequency.values()), default=1)
        for node, (x_pos, y_pos) in positions.items():
            if node == root_key:
                continue
            label = str(node[1][-1] if node[1] else "")
            score = float(node_frequency.get(node, 1))
            font_size = 8.5 + 7.5 * (score / float(max_node_score))
            ax.text(
                x_pos,
                y_pos,
                label,
                fontsize=max(8.0, min(18.0, font_size)),
                color="#1f2937",
                ha="center",
                va="center",
                zorder=2,
            )

        ax.axis("off")
        ax.set_title("Árvore de Palavras", fontsize=16, color="#111827", pad=10)
        fig.tight_layout()
        fig.savefig(graph_path, dpi=220, bbox_inches="tight", facecolor="#f5f5f5")
        plt.close(fig)

    @staticmethod
    def _export_edges_csv(
        *,
        table_path: Path,
        edge_counter: Dict[Tuple[Tuple[str, Tuple[str, ...]], Tuple[str, Tuple[str, ...]]], int],
        root: str,
    ) -> None:
        """Export branch edges for table/statistics viewing."""
        root_key = ("ROOT", (root,))
        rows = []
        for (parent, child), weight in edge_counter.items():
            child_side, child_path = child
            rows.append(
                {
                    "side": "root" if child_side == "ROOT" else ("right" if child_side == "R" else "left"),
                    "depth": int(len(child_path) if child_side != "ROOT" else 0),
                    "parent": " ".join(parent[1]) if parent != root_key else root,
                    "child": " ".join(child[1]) if child != root_key else root,
                    "parent_term": str(parent[1][-1] if parent[1] else root),
                    "child_term": str(child[1][-1] if child[1] else root),
                    "weight": int(weight),
                }
            )

        rows.sort(key=lambda item: (-int(item["weight"]), int(item["depth"]), str(item["child"])))
        with table_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["side", "depth", "parent", "child", "parent_term", "child_term", "weight"],
                delimiter=";",
            )
            writer.writeheader()
            writer.writerows(rows)

