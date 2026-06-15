"""
Execute CHD/Similarity with IRaMuTeQ-like defaults and compare visuals.

Usage:
    python scripts/validate_iramuteq_clone.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.chd_reinert import CHDAnalysis
from src.analysis.similarity import SimilarityAnalysis
from src.core.corpus import Corpus
from src.core.lexicon import Lexicon, resolve_lexicon_path


REFERENCE_MAP = {
    "chd": ["dendograma.png", "chd_Plano Fatorial AFC.png"],
    "similarity": ["similitude.png", "analise-similitude.png", "arvore-similitude.png", "arvore-similitude-2.png"],
}

SMALL_CORPUS_UCE_THRESHOLD = 8


def build_corpus(corpus_file: Path, db_path: Path) -> Corpus:
    text = corpus_file.read_text(encoding="utf-8")
    lexicon = None
    try:
        lexicon_path = resolve_lexicon_path("portuguese")
        if lexicon_path.exists():
            lexicon = Lexicon()
            if int(lexicon.load(lexicon_path)) <= 0:
                lexicon = None
    except Exception:
        lexicon = None

    corpus = Corpus({"ucemethod": 1, "ucesize": 40}, lexicon=lexicon)
    if db_path.exists():
        db_path.unlink()
    corpus.connect(db_path)

    word_pattern = re.compile(r"\b[a-zA-ZÀ-ÿ]+\b")
    uci_id = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("****"):
            uci = corpus.add_uci(line)
            uci_id = uci.ident
            continue
        if uci_id is None:
            uci = corpus.add_uci("**** *doc_1")
            uci_id = uci.ident
        uce = corpus.add_uce(uci_id, 0, line)
        for word in word_pattern.findall(line.lower()):
            if len(word) > 2:
                corpus.add_word(word, uce_id=uce.ident)
    return corpus


def choose_chd_validation_params(corpus: Corpus, min_freq: int) -> Dict[str, object]:
    """Choose a stable CHD smoke-validation profile for the current corpus size.

    The product path keeps the official 0.8a7 defaults. This helper only protects
    the standalone validation script from using an unstable class split on tiny
    corpora such as tests/fixtures/exemplo.txt.
    """

    uce_count = int(corpus.getucenb())
    params: Dict[str, object] = {
        "min_freq": int(min_freq),
        "use_native_chd": True,
        "native_fallback_legacy": True,
        "tailleuc1": 12,
        "tailleuc2": 14,
        "max_actives": 20000,
        "typegraph": "png",
        "width": 1400,
        "height": 1000,
        "validation_profile": "native",
        "corpus_uces": uce_count,
    }

    if uce_count <= SMALL_CORPUS_UCE_THRESHOLD:
        params.update(
            {
                "nb_classes": 2,
                "classif_mode": 0,
                "svd_method": "svdR",
                "validation_profile": "native_small_corpus_smoke",
            }
        )
        return params

    params.update(
        {
            "nb_classes": 4,
            "classif_mode": 1,
        }
    )
    return params


def image_features(path: Path) -> Dict[str, object]:
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)
    h, w, _ = arr.shape
    total = float(h * w)

    white = np.all(arr > 245, axis=2).sum() / total
    red = ((arr[:, :, 0] > 170) & (arr[:, :, 1] < 120) & (arr[:, :, 2] < 120)).sum() / total
    gray = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2])
    gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
    grad = np.sqrt(gx * gx + gy * gy)
    edge_density = (grad > 25).sum() / total

    hist: List[float] = []
    for channel in range(3):
        hst, _ = np.histogram(arr[:, :, channel], bins=8, range=(0, 256), density=False)
        hist.extend(hst.tolist())
    hist_arr = np.array(hist, dtype=np.float64)
    hist_arr /= hist_arr.sum() if hist_arr.sum() else 1.0

    return {
        "size": [int(w), int(h)],
        "aspect": float(w / h if h else 0),
        "white": float(white),
        "red": float(red),
        "edge_density": float(edge_density),
        "hist": hist_arr,
    }


def visual_distance(a: Dict[str, object], b: Dict[str, object]) -> float:
    hist = float(np.linalg.norm(a["hist"] - b["hist"]))
    aspect = abs(float(a["aspect"]) - float(b["aspect"])) * 0.7
    white = abs(float(a["white"]) - float(b["white"])) * 0.8
    red = abs(float(a["red"]) - float(b["red"])) * 0.8
    edge = abs(float(a["edge_density"]) - float(b["edge_density"])) * 1.1
    return hist + aspect + white + red + edge


def compare_images(
    generated: Dict[str, Path],
    reference_dir: Path,
) -> Dict[str, object]:
    report: Dict[str, object] = {}
    for key, image_path in generated.items():
        if not image_path.exists():
            report[key] = {"ok": False, "error": f"missing image: {image_path}"}
            continue
        our_f = image_features(image_path)
        candidates: List[Dict[str, object]] = []
        for name in REFERENCE_MAP.get(key, []):
            ref_path = reference_dir / name
            if not ref_path.exists():
                continue
            ref_f = image_features(ref_path)
            score = visual_distance(our_f, ref_f)
            candidates.append(
                {
                    "reference": name,
                    "distance": round(score, 4),
                    "ref_size": ref_f["size"],
                }
            )
        candidates.sort(key=lambda item: item["distance"])
        report[key] = {
            "ok": True,
            "our_image": str(image_path),
            "our_size": our_f["size"],
            "our_white": round(float(our_f["white"]), 4),
            "our_edge_density": round(float(our_f["edge_density"]), 4),
            "best_matches": candidates[:3],
        }
    return report


def run_validation(
    corpus_file: Path,
    output_dir: Path,
    min_freq: int,
) -> Tuple[Dict[str, object], Dict[str, Path]]:
    corpus_file = corpus_file.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    corpus = build_corpus(corpus_file, output_dir / "validation.db")

    summary: Dict[str, object] = {}
    generated: Dict[str, Path] = {}

    try:
        chd_out = output_dir / "chd"
        chd_out.mkdir(parents=True, exist_ok=True)
        chd = CHDAnalysis(corpus, chd_out)
        chd_params = choose_chd_validation_params(corpus, min_freq=min_freq)
        chd_res = chd.run(chd_params)
        dendro = chd_res.dendrogram_path or (chd_out / "dendrogramme.png")
        generated["chd"] = dendro

        summary["chd"] = {
            "ok": bool(dendro and Path(dendro).exists()),
            "dendrogram": str(dendro) if dendro else None,
            "afc_graph": str(chd_res.afc_graph_path) if getattr(chd_res, "afc_graph_path", None) else None,
            "profile_afc": str(chd_res.profile_afc_path) if getattr(chd_res, "profile_afc_path", None) else None,
            "n_classes": chd_res.n_classes,
            "pipeline": str(chd_params.get("validation_profile", "native")),
            "corpus_uces": int(chd_params.get("corpus_uces", 0)),
            "params": {
                "nb_classes": int(chd_params.get("nb_classes", 0)),
                "classif_mode": int(chd_params.get("classif_mode", 0)),
                "svd_method": chd_params.get("svd_method"),
            },
        }
    except Exception as exc:
        summary["chd"] = {"ok": False, "error": str(exc)}

    try:
        sim_out = output_dir / "similarity"
        sim_out.mkdir(parents=True, exist_ok=True)
        sim = SimilarityAnalysis(corpus, sim_out)
        sim_res = sim.run(
            {
                "min_freq": min_freq,
                "coefficient": 0,
                "parity_profile": "official_0_8a7",
                "render_profile": "native",
                "layout": "frutch",
                "min_edge": 0,
                "arbremax": True,
                "detect_communities": False,
                "typegraph": "png",
                "width": int(OFFICIAL_SIMILARITY_DEFAULTS.get("width", 1000)),
                "height": int(OFFICIAL_SIMILARITY_DEFAULTS.get("height", 1000)),
            }
        )
        sim_image = sim_res.graph_path or (sim_out / "similarity.png")
        generated["similarity"] = sim_image
        summary["similarity"] = {
            "ok": bool(sim_image and Path(sim_image).exists()),
            "graph": str(sim_image) if sim_image else None,
            "has_communities": bool(sim_res.communities),
            "has_centrality": bool(sim_res.centrality),
        }
    except Exception as exc:
        summary["similarity"] = {"ok": False, "error": str(exc)}
    finally:
        corpus.close()

    return summary, generated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate LabiiaLex vs IRaMuTeQ visual outputs.")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=PROJECT_ROOT / "tests" / "fixtures" / "exemplo.txt",
        help="Corpus in IRaMuTeQ-like text format.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "tmp_visual_validation",
        help="Folder for generated outputs.",
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=PROJECT_ROOT.parent / "iramuteq-exemplos-visuais",
        help="Folder with IRaMuTeQ reference images.",
    )
    parser.add_argument(
        "--min-freq",
        type=int,
        default=1,
        help="Minimum frequency for validation run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary, generated = run_validation(
        corpus_file=args.corpus,
        output_dir=args.output_dir,
        min_freq=int(args.min_freq),
    )

    comparison = compare_images(generated, args.reference_dir.resolve())

    summary_path = args.output_dir / "run_summary.json"
    compare_path = args.output_dir / "visual_comparison_report.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    compare_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")

    print(summary_path.resolve())
    print(compare_path.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
