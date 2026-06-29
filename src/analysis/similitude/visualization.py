"""
Layer 3: Similarity graph visualization — dual renderer.

Primary renderer: R/igraph via subprocess (IRaMuTeQ-style raw output).
Fallback renderer: matplotlib with Bézier curves (when R unavailable).

The R renderer uses:
  - igraph::plot() with edge.curved=FALSE and mark.groups for halos
  - SNA Fruchterman-Reingold layout
  - Cairo PNG rendering (96 DPI, pointsize 8)
  - text() overlay for labels (like IRaMuTeQ simi.R)
  - layout_raw.json export for the readable presentation pass

The matplotlib fallback uses:
  - Quadratic Bézier curved edges via LineCollection
  - Rank-based font sizing
  - ConvexHull + Catmull-Rom halos
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from scipy.spatial import ConvexHull

from .models import SimilitudeConfig, SimilitudeGraph, SimilitudeMatrix
from src.core.network_renderer import _bbox_overlaps_any, _bezier_points
from src.core.r_executor import RExecutor

import logging

log = logging.getLogger(__name__)

_STRICT_R_PACKAGES = ("igraph", "sna", "network", "intergraph", "jsonlite")
_RAW_OUTPUT_NAME = "similitude_raw_iramuteq.png"
_LAYOUT_RAW_NAME = "layout_raw.json"
_LABEL_ADJUSTMENTS_NAME = "label_adjustments.json"


# ---------------------------------------------------------------------------
# R detection
# ---------------------------------------------------------------------------

def _find_rscript() -> Optional[Path]:
    """
    Find Rscript on the system.

    Search order:
    1. PATH (shutil.which) — funciona em todos os SOs
    2. Locais típicos Windows: C:\\Program Files\\R\\*\\bin\\Rscript.exe
    3. Locais típicos Linux: /usr/lib/R, /usr/local/lib/R, /opt/R/*/
    4. macOS: /Library/Frameworks/R.framework
    """
    # 1. PATH — funciona em Linux, macOS e Windows
    which_result = shutil.which("Rscript") or shutil.which("rscript")
    if which_result:
        return Path(which_result)

    import sys
    if sys.platform == "win32":
        # 2. Locais padrão Windows
        for base in [Path(r"C:\Program Files\R"), Path(r"C:\Program Files (x86)\R")]:
            if base.is_dir():
                versions = sorted(base.iterdir(), reverse=True)
                for ver_dir in versions:
                    rscript = ver_dir / "bin" / "Rscript.exe"
                    if rscript.is_file():
                        return rscript
    elif sys.platform != "darwin":
        # 3. Linux: locais típicos de instalação
        linux_homes = [
            Path("/usr/lib/R"),
            Path("/usr/lib64/R"),
            Path("/usr/local/lib/R"),
            Path("/usr/local/lib64/R"),
        ]
        for home in linux_homes:
            rscript = home / "bin" / "Rscript"
            if rscript.is_file():
                return rscript
        # rig: /opt/R/R-x.y.z/
        opt_r = Path("/opt/R")
        if opt_r.is_dir():
            for ver_dir in sorted(opt_r.iterdir(), reverse=True):
                rscript = ver_dir / "bin" / "Rscript"
                if rscript.is_file():
                    return rscript
    else:
        # 4. macOS: R.framework
        fw_rscript = Path("/Library/Frameworks/R.framework/Versions/Current/Resources/bin/Rscript")
        if fw_rscript.is_file():
            return fw_rscript

    return None


def _probe_r_environment(rscript_exe: Path, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Probe the R runtime required for strict IRaMuTeQ rendering.

    Returns a serializable dict with package availability, versions,
    graphics capabilities, and session info.
    """
    r_code = r"""
required <- c("igraph", "sna", "network", "intergraph", "jsonlite")
cat(sprintf("version|%s\n", R.version$version.string))
for (pkg in required) {
    found <- requireNamespace(pkg, quietly = TRUE)
    ver <- if (found) as.character(packageVersion(pkg)) else ""
    cat(sprintf("pkg|%s|%s|%s\n", pkg, found, ver))
}
for (cap in c("cairo", "png", "jpeg")) {
    cat(sprintf("cap|%s|%s\n", cap, capabilities(cap)))
}
session_txt <- paste(capture.output(sessionInfo()), collapse = "\n")
session_txt <- gsub("\r", "", session_txt, fixed = TRUE)
session_txt <- gsub("\n", "\\\\n", session_txt, fixed = TRUE)
cat(sprintf("session|%s\n", session_txt))
"""
    probe_script: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix="_lexianalyst_probe.R",
            delete=False,
            dir=tempfile.gettempdir(),
        ) as handle:
            handle.write(r_code)
            probe_script = Path(handle.name)

        result = subprocess.run(
            [str(rscript_exe), str(probe_script)],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    finally:
        if probe_script is not None:
            try:
                probe_script.unlink(missing_ok=True)
            except OSError:
                pass
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to probe R environment: "
            + (result.stderr.strip() or result.stdout.strip() or "unknown error")
        )

    env: Dict[str, Any] = {
        "r_version": "",
        "packages": {},
        "capabilities": {},
        "session_info": "",
        "missing_packages": [],
    }

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("|", 3)
        kind = parts[0]
        if kind == "version" and len(parts) >= 2:
            env["r_version"] = parts[1]
        elif kind == "pkg" and len(parts) >= 4:
            pkg_name = parts[1]
            available = parts[2].strip().upper() == "TRUE"
            env["packages"][pkg_name] = {
                "available": available,
                "version": parts[3],
            }
        elif kind == "cap" and len(parts) >= 3:
            env["capabilities"][parts[1]] = parts[2].strip().upper() == "TRUE"
        elif kind == "session" and len(parts) >= 2:
            env["session_info"] = parts[1].replace("\\n", "\n")

    env["missing_packages"] = [
        pkg for pkg in _STRICT_R_PACKAGES
        if not env["packages"].get(pkg, {}).get("available", False)
    ]
    env["strict_ready"] = (
        not env["missing_packages"]
        and bool(env["capabilities"].get("cairo"))
    )
    return env


# ---------------------------------------------------------------------------
# R/igraph renderer (primary — IRaMuTeQ-identical output)
# ---------------------------------------------------------------------------

def _render_with_r(
    graph: SimilitudeGraph,
    output_path: Path,
    config: SimilitudeConfig,
    rscript_exe: Path,
    matrix: Optional[SimilitudeMatrix] = None,
    env: Optional[Dict[str, str]] = None,
) -> Optional[Path]:
    """
    Render the similitude graph using R/igraph via subprocess.

    Exports matrix + frequencies as CSV, calls similitude_render.R,
    reads back the PNG. Returns output path on success, None on failure.
    """
    try:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="lexianalyst_simi_") as tmpdir:
            tmpdir_path = Path(tmpdir)

            matrix_csv = tmpdir_path / "matrix.csv"
            freq_csv = tmpdir_path / "freq.csv"
            params_json = tmpdir_path / "params.json"
            raw_output = tmpdir_path / _RAW_OUTPUT_NAME
            layout_output = tmpdir_path / _LAYOUT_RAW_NAME
            sensitivity_json = tmpdir_path / "community_sensitivity.json"

            # Export association matrix as CSV (full matrix from SimilitudeMatrix)
            _export_matrix_csv(graph, matrix_csv, matrix=matrix)

            # Export term frequencies as CSV (colSums of binary matrix)
            _export_freq_csv(graph, freq_csv, matrix=matrix)

            # Map community method
            comm_method = getattr(config, "community_method", "louvain") or "louvain"

            # Map coefficient to method
            coeff = getattr(config, "coefficient", "cooccurrence") or "cooccurrence"
            method = "cooc" if coeff == "cooccurrence" else coeff

            # Write params JSON — aligned with IRaMuTeQ simitxt.cfg defaults
            params = {
                "matrix_file": str(matrix_csv),
                "freq_file": str(freq_csv),
                "output_file": str(raw_output),
                "width": config.width,
                "height": config.height,
                "method": method,
                "max_tree": True,                           # R does MST from full matrix
                "layout_type": "frutch",                    # SNA Fruchterman-Reingold
                "vcexmin": 1.0,                             # IRaMuTeQ: vcexmin=10 ÷ 10
                "vcexmax": 2.5,                             # IRaMuTeQ: vcexmax=25 ÷ 10
                "coeff_edge_min": 0.6,
                "coeff_edge_max": 4.0,
                "community_method": comm_method,
                "halo": bool(config.show_halo),
                "edge_curved": bool(getattr(config, "edge_curved", True)),
                "grayscale": bool(config.grayscale),
                "show_edge_labels": bool(config.show_edge_labels),
                "dpi": 96,
                "alpha": 20,                                # IRaMuTeQ: alpha=20
                "graph_word": str(getattr(config, "graph_word", "") or "").strip(),
                "community_sensitivity_file": str(sensitivity_json),
                "layout_output_file": str(layout_output),
            }
            params_json.write_text(json.dumps(params, ensure_ascii=False), encoding="utf-8")

            # Find R script
            script_path = Path(__file__).resolve().parents[3] / "Rscripts" / "similitude_render.R"
            if not script_path.is_file():
                log.warning("R script not found: %s", script_path)
                return None

            # Run R
            log.info("Rendering similitude with R/igraph: %s", rscript_exe)
            result = subprocess.run(
                [str(rscript_exe), str(script_path), str(params_json)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(tmpdir_path),
                env=env,
            )

            (output_path.parent / "render_stdout.log").write_text(
                result.stdout or "",
                encoding="utf-8",
            )
            (output_path.parent / "render_stderr.log").write_text(
                result.stderr or "",
                encoding="utf-8",
            )

            if result.returncode != 0:
                log.warning("R script failed (exit %d): %s", result.returncode, result.stderr[:500])
                return None

            if not raw_output.is_file():
                log.warning("R script produced no output file")
                return None

            raw_target = output_path.parent / _RAW_OUTPUT_NAME
            shutil.copy2(str(raw_output), str(raw_target))
            if layout_output.is_file():
                shutil.copy2(
                    str(layout_output),
                    str(output_path.parent / _LAYOUT_RAW_NAME),
                )
            if sensitivity_json.is_file():
                shutil.copy2(
                    str(sensitivity_json),
                    str(output_path.parent / "community_sensitivity.json"),
                )

            log.info("R/igraph rendering complete: %s", raw_target)
            return raw_target

    except subprocess.TimeoutExpired:
        log.warning("R script timed out after 60s")
        return None
    except Exception as e:
        log.warning("R rendering failed: %s", e)
        return None


def _r_executor_for_rscript(rscript_exe: Path) -> RExecutor:
    return RExecutor(r_path=str(rscript_exe))


def _r_env_for_executor(executor: RExecutor) -> Dict[str, str]:
    return executor._build_r_env()


def _probe_and_repair_strict_r(rscript_exe: Path, output_dir: Path) -> tuple[Dict[str, Any], Dict[str, str]]:
    """Probe strict renderer packages and install missing CRAN packages for current R."""
    executor = _r_executor_for_rscript(rscript_exe)
    env = _r_env_for_executor(executor)
    env_info = _probe_r_environment(rscript_exe, env=env)
    missing = list(env_info.get("missing_packages", []) or [])
    if missing:
        log.info("Installing missing strict similitude R packages for %s: %s", rscript_exe, missing)
        install_ok = executor.install_packages(missing)
        env_info = _probe_r_environment(rscript_exe, env=env)
        env_info["repair_attempted"] = True
        env_info["repair_requested_packages"] = missing
        env_info["repair_success"] = bool(install_ok and not env_info.get("missing_packages"))
    else:
        env_info["repair_attempted"] = False
        env_info["repair_success"] = True
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    (Path(output_dir) / "similitude_env.json").write_text(
        json.dumps(env_info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return env_info, env


def _export_matrix_csv(
    graph: SimilitudeGraph,
    path: Path,
    matrix: Optional[SimilitudeMatrix] = None,
) -> None:
    """Export the association matrix as CSV with row/col names.

    When SimilitudeMatrix is available, exports the FULL association matrix
    (all terms, pre-MST). This lets R compute MST + layout from scratch,
    replicating the exact IRaMuTeQ pipeline (simi.R reads full matrix).

    Falls back to reconstructing from graph edges (post-MST) when matrix
    is not available.
    """
    if matrix is not None and hasattr(matrix, "association"):
        # Use full association matrix (pre-MST) — IRaMuTeQ approach
        vocab = list(matrix.vocabulary)
        assoc = matrix.association
        n = len(vocab)
        log.info("Exporting full association matrix: %d x %d terms", n, n)
    else:
        # Fallback: reconstruct from graph edges (post-MST)
        vocab = list(graph.vocabulary)
        n = len(vocab)
        G = graph.graph
        vocab_idx = {w: i for i, w in enumerate(vocab)}
        assoc = np.zeros((n, n), dtype=np.float64)
        for u, v, data in G.edges(data=True):
            i = vocab_idx.get(u)
            j = vocab_idx.get(v)
            if i is not None and j is not None:
                w = data.get("weight", 0.0)
                assoc[i, j] = w
                assoc[j, i] = w
        log.info("Exporting graph-reconstructed matrix: %d x %d terms", n, n)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([""] + vocab)
        for i in range(n):
            row = [vocab[i]]
            for j in range(n):
                val = assoc[i, j]
                row.append(f"{val:.6f}" if val != 0 else "0")
            writer.writerow(row)


def _export_freq_csv(
    graph: SimilitudeGraph,
    path: Path,
    matrix: Optional[SimilitudeMatrix] = None,
) -> None:
    """Export term frequencies as CSV.

    When SimilitudeMatrix is available, uses matrix.term_frequencies
    (colSums of binary matrix = number of UCEs containing each term).
    This matches IRaMuTeQ: cs <- colSums(dm); mat.eff <- cs
    """
    if matrix is not None and hasattr(matrix, "term_frequencies"):
        vocab = list(matrix.vocabulary)
        freqs = matrix.term_frequencies
    else:
        vocab = list(graph.vocabulary)
        freqs = graph.term_frequencies

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["word", "frequency"])
        for i, word in enumerate(vocab):
            writer.writerow([word, int(freqs[i])])


# ---------------------------------------------------------------------------
# IRaMuTeQ-inspired color palette
# ---------------------------------------------------------------------------

_COMMUNITY_COLORS = [
    {"halo": "#FFCCCC", "text": "#BB0000", "edge": "#DD6666"},  # Red
    {"halo": "#CCE5FF", "text": "#0044AA", "edge": "#6699CC"},  # Blue
    {"halo": "#CCFFCC", "text": "#006600", "edge": "#66AA66"},  # Green
    {"halo": "#FFE5CC", "text": "#BB5500", "edge": "#CC9966"},  # Orange
    {"halo": "#E5CCFF", "text": "#6600AA", "edge": "#9966CC"},  # Purple
    {"halo": "#FFFFCC", "text": "#777700", "edge": "#AAAA66"},  # Yellow
    {"halo": "#FFCCE5", "text": "#990055", "edge": "#CC6699"},  # Pink
    {"halo": "#CCFFE5", "text": "#006644", "edge": "#66AA88"},  # Teal
    {"halo": "#FFD9CC", "text": "#884400", "edge": "#AA7744"},  # Brown
    {"halo": "#D9CCFF", "text": "#440099", "edge": "#7766BB"},  # Violet
    {"halo": "#CCFFFF", "text": "#005555", "edge": "#668888"},  # Cyan
    {"halo": "#DDDDDD", "text": "#444444", "edge": "#999999"},  # Gray
]


def _get_community_style(community_id: int) -> Dict[str, str]:
    return _COMMUNITY_COLORS[community_id % len(_COMMUNITY_COLORS)]


# ---------------------------------------------------------------------------
# Bézier curve generation
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Organic halo drawing
# ---------------------------------------------------------------------------

def _draw_organic_halo(
    ax: Axes, points: np.ndarray, color: str,
    alpha: float = 0.25, padding: float = 0.12, smoothness: int = 80,
) -> None:
    if len(points) < 1:
        return
    if len(points) == 1:
        ax.add_patch(mpatches.Circle(
            (points[0, 0], points[0, 1]), radius=padding * 4.0,
            facecolor=color, edgecolor="none", alpha=alpha, zorder=0))
        return
    if len(points) == 2:
        cx = (points[0, 0] + points[1, 0]) / 2
        cy = (points[0, 1] + points[1, 1]) / 2
        dx = points[1, 0] - points[0, 0]
        dy = points[1, 1] - points[0, 1]
        length = math.sqrt(dx * dx + dy * dy)
        angle = math.degrees(math.atan2(dy, dx))
        ax.add_patch(mpatches.Ellipse(
            (cx, cy), width=length + padding * 8, height=padding * 6,
            angle=angle, facecolor=color, edgecolor="none", alpha=alpha, zorder=0))
        return

    try:
        hull = ConvexHull(points)
        hull_pts = points[hull.vertices]
    except Exception:
        hull_pts = points

    cx, cy = hull_pts[:, 0].mean(), hull_pts[:, 1].mean()
    dists = np.sqrt((hull_pts[:, 0] - cx) ** 2 + (hull_pts[:, 1] - cy) ** 2)
    max_dist = max(np.max(dists), 1e-6)

    expanded = []
    for pt in hull_pts:
        dx, dy = pt[0] - cx, pt[1] - cy
        dist = max(math.sqrt(dx * dx + dy * dy), 1e-6)
        scale = 1.0 + 0.6 * (1.0 - dist / max_dist)
        pad = padding * scale
        expanded.append((pt[0] + dx / dist * pad, pt[1] + dy / dist * pad))

    expanded = np.array(expanded)
    n_seg = max(6, smoothness // max(1, len(expanded)))
    smooth_pts = _catmull_rom_closed(expanded, n_per_segment=n_seg)
    ax.add_patch(mpatches.Polygon(
        smooth_pts, closed=True, facecolor=color, edgecolor=color,
        linewidth=0.8, alpha=alpha, zorder=0))


def _catmull_rom_closed(points: np.ndarray, n_per_segment: int = 10) -> np.ndarray:
    n = len(points)
    if n < 3:
        return points
    n_per_segment = max(4, n_per_segment)
    result = []
    for i in range(n):
        p0 = points[(i - 1) % n]
        p1 = points[i]
        p2 = points[(i + 1) % n]
        p3 = points[(i + 2) % n]
        for t_idx in range(n_per_segment):
            t = t_idx / n_per_segment
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2*p1[0]) + (-p0[0]+p2[0])*t + (2*p0[0]-5*p1[0]+4*p2[0]-p3[0])*t2 + (-p0[0]+3*p1[0]-3*p2[0]+p3[0])*t3)
            y = 0.5 * ((2*p1[1]) + (-p0[1]+p2[1])*t + (2*p0[1]-5*p1[1]+4*p2[1]-p3[1])*t2 + (-p0[1]+3*p1[1]-3*p2[1]+p3[1])*t3)
            result.append((x, y))
    return np.array(result)


# ---------------------------------------------------------------------------
# Label overlap resolution
# ---------------------------------------------------------------------------

def _resolve_label_overlaps(
    ax: Axes, labels_info: List[Dict[str, Any]],
    max_iterations: int = 2000, speed: float = 1.8,
) -> None:
    fig = ax.get_figure()
    renderer = fig.canvas.get_renderer()
    n = len(labels_info)
    if n < 2:
        return

    labels_info.sort(key=lambda info: info["x"])
    for iteration in range(max_iterations):
        t = iteration / max_iterations
        spd = speed * (1.0 - 0.5 * t)
        moved = False
        inv = ax.transData.inverted()
        for info in labels_info:
            bb = inv.transform_bbox(info["text_obj"].get_window_extent(renderer=renderer))
            info["_x0"], info["_y0"] = bb.x0, bb.y0
            info["_x1"], info["_y1"] = bb.x1, bb.y1

        for i in range(n):
            ix0, iy0, ix1, iy1 = labels_info[i]["_x0"], labels_info[i]["_y0"], labels_info[i]["_x1"], labels_info[i]["_y1"]
            for j in range(i + 1, n):
                jx0 = labels_info[j]["_x0"]
                if jx0 > ix1:
                    break
                jy0, jx1, jy1 = labels_info[j]["_y0"], labels_info[j]["_x1"], labels_info[j]["_y1"]
                if iy0 >= jy1 or iy1 <= jy0:
                    continue
                ox = min(ix1, jx1) - max(ix0, jx0)
                oy = min(iy1, jy1) - max(iy0, jy0)
                dx = (jx0 + jx1) * 0.5 - (ix0 + ix1) * 0.5
                dy = (jy0 + jy1) * 0.5 - (iy0 + iy1) * 0.5
                if abs(dx) < 1e-4 and abs(dy) < 1e-4:
                    dx = 0.01 * (1 if i % 2 == 0 else -1)
                    dy = 0.005
                fi = labels_info[i].get("fontsize", 10)
                fj = labels_info[j].get("fontsize", 10)
                ri = fj / max(fi + fj, 1)
                rj = fi / max(fi + fj, 1)
                if ox < oy:
                    push = (ox * 0.6 + 0.003) * spd
                    s = 1.0 if dx >= 0 else -1.0
                    labels_info[i]["x"] -= s * push * ri
                    labels_info[j]["x"] += s * push * rj
                    labels_info[i]["_x0"] -= s * push * ri
                    labels_info[i]["_x1"] -= s * push * ri
                    labels_info[j]["_x0"] += s * push * rj
                    labels_info[j]["_x1"] += s * push * rj
                else:
                    push = (oy * 0.6 + 0.003) * spd
                    s = 1.0 if dy >= 0 else -1.0
                    labels_info[i]["y"] -= s * push * ri
                    labels_info[j]["y"] += s * push * rj
                    labels_info[i]["_y0"] -= s * push * ri
                    labels_info[i]["_y1"] -= s * push * ri
                    labels_info[j]["_y0"] += s * push * rj
                    labels_info[j]["_y1"] += s * push * rj
                moved = True
        for info in labels_info:
            info["text_obj"].set_position((info["x"], info["y"]))
        labels_info.sort(key=lambda info: info["x"])
        if not moved:
            break

    # Phase 2: Spiral search
    labels_info.sort(key=lambda info: info.get("fontsize", 0), reverse=True)
    inv = ax.transData.inverted()
    placed_bboxes = []
    for info in labels_info:
        bb = inv.transform_bbox(info["text_obj"].get_window_extent(renderer=renderer))
        if not _bbox_overlaps_any(bb, placed_bboxes):
            placed_bboxes.append(bb)
            continue
        orig_x, orig_y = info["x"], info["y"]
        step = max(bb.width, bb.height) * 0.35
        found = False
        for ring in range(1, 60):
            r = step * ring
            n_angles = max(8, ring * 8)
            for ai in range(n_angles):
                angle = 2 * math.pi * ai / n_angles
                nx_ = orig_x + r * math.cos(angle)
                ny_ = orig_y + r * math.sin(angle)
                info["text_obj"].set_position((nx_, ny_))
                bb2 = inv.transform_bbox(info["text_obj"].get_window_extent(renderer=renderer))
                if not _bbox_overlaps_any(bb2, placed_bboxes):
                    info["x"], info["y"] = nx_, ny_
                    placed_bboxes.append(bb2)
                    found = True
                    break
            if found:
                break
        if not found:
            info["text_obj"].set_position((orig_x, orig_y))
            placed_bboxes.append(inv.transform_bbox(info["text_obj"].get_window_extent(renderer=renderer)))




def _bbox_overlap_area(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return width * height


def _load_layout_payload(layout_path: Path) -> Dict[str, Any]:
    payload = json.loads(Path(layout_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("layout_raw.json must contain an object payload")
    return payload


def _project_nodes_to_pixels(
    nodes: List[Dict[str, Any]],
    width: int,
    height: int,
) -> List[Dict[str, Any]]:
    if not nodes:
        return []

    xs = [float(node.get("x", 0.0) or 0.0) for node in nodes]
    ys = [float(node.get("y", 0.0) or 0.0) for node in nodes]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xspan = max(xmax - xmin, 1e-6)
    yspan = max(ymax - ymin, 1e-6)

    margin = max(60.0, min(width, height) * 0.10)
    usable_w = max(width - 2 * margin, 1.0)
    usable_h = max(height - 2 * margin, 1.0)
    scale = min(usable_w / xspan, usable_h / yspan)
    cx = (xmin + xmax) * 0.5
    cy = (ymin + ymax) * 0.5

    projected: List[Dict[str, Any]] = []
    for node in nodes:
        x = float(node.get("x", 0.0) or 0.0)
        y = float(node.get("y", 0.0) or 0.0)
        projected.append(
            {
                **node,
                "x_px": (width * 0.5) + ((x - cx) * scale),
                "y_px": (height * 0.5) + ((y - cy) * scale),
            }
        )
    return projected


def _build_preferred_direction(
    node: Dict[str, Any],
    community_centers: Dict[int, Tuple[float, float]],
    global_center: Tuple[float, float],
) -> Tuple[float, float]:
    community = int(node.get("community", 0) or 0)
    anchor_x = float(node.get("x_px", 0.0) or 0.0)
    anchor_y = float(node.get("y_px", 0.0) or 0.0)
    center = community_centers.get(community, global_center)
    dx = anchor_x - center[0]
    dy = anchor_y - center[1]
    norm = math.hypot(dx, dy)
    if norm < 1e-6:
        dx = anchor_x - global_center[0]
        dy = anchor_y - global_center[1]
        norm = math.hypot(dx, dy)
    if norm < 1e-6:
        return (1.0, 0.0)
    return (dx / norm, dy / norm)


def _resolve_label_overlaps_radially(
    fig: plt.Figure,
    labels: List[Dict[str, Any]],
) -> None:
    if len(labels) < 2:
        return

    renderer = fig.canvas.get_renderer()
    for _ in range(180):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        bboxes: Dict[str, Tuple[float, float, float, float]] = {}
        moved = False
        for item in labels:
            bb = item["text_obj"].get_window_extent(renderer=renderer)
            bboxes[item["term"]] = (bb.x0, bb.y0, bb.x1, bb.y1)

        for i, left in enumerate(labels):
            left_box = bboxes[left["term"]]
            for right in labels[i + 1 :]:
                right_box = bboxes[right["term"]]
                overlap = _bbox_overlap_area(left_box, right_box)
                if overlap <= 0:
                    continue

                moved = True
                push_px = min(8.0, max(1.5, math.sqrt(overlap) * 0.12))
                for item, sign in ((left, -1.0), (right, 1.0)):
                    pref_x, pref_y = item["preferred_dir"]
                    new_dx = item["dx"] + (pref_x * push_px * sign)
                    new_dy = item["dy"] + (pref_y * push_px * sign)
                    displacement = math.hypot(new_dx, new_dy)
                    if displacement > item["max_displacement"]:
                        factor = item["max_displacement"] / max(displacement, 1e-6)
                        new_dx *= factor
                        new_dy *= factor
                    item["dx"] = new_dx
                    item["dy"] = new_dy
                    item["x"] = item["anchor_x"] + item["dx"]
                    item["y"] = item["anchor_y"] + item["dy"]
                    item["text_obj"].set_position((item["x"], item["y"]))

        if not moved:
            break


def _compute_overlap_metrics(
    fig: plt.Figure,
    labels: List[Dict[str, Any]],
    width: int,
    height: int,
) -> Dict[str, float]:
    if not labels:
        return {
            "overlap_area_ratio": 0.0,
            "central_label_area_share": 0.0,
            "max_label_height_px": 0.0,
            "label_height_ratio_p95_p50": 0.0,
        }

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bboxes = []
    heights = []
    total_area = 0.0
    overlap_area = 0.0
    center_area = 0.0
    center_box = (
        width * 0.35,
        height * 0.35,
        width * 0.65,
        height * 0.65,
    )

    for item in labels:
        bb = item["text_obj"].get_window_extent(renderer=renderer)
        box = (bb.x0, bb.y0, bb.x1, bb.y1)
        bboxes.append(box)
        heights.append(bb.height)
        area = max(0.0, bb.width) * max(0.0, bb.height)
        total_area += area
        center_area += _bbox_overlap_area(box, center_box)

    for i, left in enumerate(bboxes):
        for right in bboxes[i + 1 :]:
            overlap_area += _bbox_overlap_area(left, right)

    height_array = np.asarray(heights, dtype=float)
    return {
        "overlap_area_ratio": float(overlap_area / total_area) if total_area > 0 else 0.0,
        "central_label_area_share": float(center_area / total_area) if total_area > 0 else 0.0,
        "max_label_height_px": float(np.max(height_array)) if height_array.size else 0.0,
        "label_height_ratio_p95_p50": float(
            np.percentile(height_array, 95) / max(np.percentile(height_array, 50), 1e-6)
        ) if height_array.size else 0.0,
    }


def _render_readable_from_layout(
    layout_path: Path,
    output_path: Path,
    config: SimilitudeConfig,
) -> Path:
    payload = _load_layout_payload(layout_path)
    device = payload.get("device") or {}
    width = int(device.get("width", config.width) or config.width)
    height = int(device.get("height", config.height) or config.height)
    dpi = int(device.get("dpi", 96) or 96)
    pointsize = float(device.get("pointsize", 8) or 8)
    nodes_raw = payload.get("nodes") or []
    edges = payload.get("edges") or []
    nodes = _project_nodes_to_pixels(list(nodes_raw), width, height)

    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    nodes_by_term = {str(node.get("term", "")): node for node in nodes}

    if config.show_halo and not config.grayscale:
        grouped: Dict[int, List[np.ndarray]] = {}
        for node in nodes:
            cid = int(node.get("community", 0) or 0)
            grouped.setdefault(cid, []).append(np.array([node["x_px"], node["y_px"]], dtype=float))
        for cid, points in grouped.items():
            if not points:
                continue
            style = _get_community_style(cid)
            point_matrix = np.vstack(points)
            _draw_organic_halo(
                ax,
                point_matrix,
                color=style["halo"],
                alpha=0.24,
                padding=max(width, height) * 0.035,
            )

    if edges:
        weights = [float(edge.get("weight", 1.0) or 1.0) for edge in edges]
        min_w = min(weights)
        max_w = max(weights)
        span = max(max_w - min_w, 1e-6)
        segments = []
        widths = []
        for edge in edges:
            source = nodes_by_term.get(str(edge.get("source", "")))
            target = nodes_by_term.get(str(edge.get("target", "")))
            if source is None or target is None:
                continue
            segments.append(
                [
                    (float(source["x_px"]), float(source["y_px"])),
                    (float(target["x_px"]), float(target["y_px"])),
                ]
            )
            weight = float(edge.get("weight", min_w) or min_w)
            widths.append(0.6 + (((weight - min_w) / span) * 3.4))
        if segments:
            ax.add_collection(
                LineCollection(
                    segments,
                    colors="#B7B7B7",
                    linewidths=widths,
                    alpha=0.9,
                    zorder=1,
                    capstyle="round",
                )
            )

    if nodes:
        global_center = (
            float(np.mean([node["x_px"] for node in nodes])),
            float(np.mean([node["y_px"] for node in nodes])),
        )
    else:
        global_center = (width * 0.5, height * 0.5)

    community_centers: Dict[int, Tuple[float, float]] = {}
    if nodes:
        for cid in {int(node.get("community", 0) or 0) for node in nodes}:
            members = [node for node in nodes if int(node.get("community", 0) or 0) == cid]
            community_centers[cid] = (
                float(np.mean([node["x_px"] for node in members])),
                float(np.mean([node["y_px"] for node in members])),
            )

    labels: List[Dict[str, Any]] = []
    for node in sorted(nodes, key=lambda item: float(item.get("label_cex", 1.0) or 1.0), reverse=True):
        term = str(node.get("term", ""))
        community = int(node.get("community", 0) or 0)
        font_points = pointsize * float(node.get("label_cex", 1.0) or 1.0)
        color = "#111111" if config.grayscale else _get_community_style(community)["text"]
        text_obj = ax.text(
            float(node["x_px"]),
            float(node["y_px"]),
            term,
            fontsize=font_points,
            color=color,
            fontweight="bold",
            fontfamily=config.font_family,
            ha="center",
            va="center",
            zorder=4,
        )
        labels.append(
            {
                "term": term,
                "community": community,
                "anchor_x": float(node["x_px"]),
                "anchor_y": float(node["y_px"]),
                "x": float(node["x_px"]),
                "y": float(node["y_px"]),
                "dx": 0.0,
                "dy": 0.0,
                "preferred_dir": _build_preferred_direction(node, community_centers, global_center),
                "max_displacement": 40.0,
                "text_obj": text_obj,
            }
        )

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for item in labels:
        bb = item["text_obj"].get_window_extent(renderer=renderer)
        item["max_displacement"] = min(40.0, 2.5 * max(bb.height, 1.0))

    _resolve_label_overlaps_radially(fig, labels)
    fig.canvas.draw()

    adjustments: Dict[str, Dict[str, Any]] = {}
    for item in labels:
        displacement = math.hypot(item["dx"], item["dy"])
        leader_line = displacement > 12.0
        if leader_line:
            ax.plot(
                [item["anchor_x"], item["x"]],
                [item["anchor_y"], item["y"]],
                color="#9A9A9A",
                linewidth=0.6,
                alpha=0.9,
                zorder=3,
            )
        adjustments[item["term"]] = {
            "dx": round(float(item["dx"]), 4),
            "dy": round(float(item["dy"]), 4),
            "leader_line": leader_line,
            "anchor_x": round(float(item["anchor_x"]), 4),
            "anchor_y": round(float(item["anchor_y"]), 4),
            "label_x": round(float(item["x"]), 4),
            "label_y": round(float(item["y"]), 4),
        }

    metrics = _compute_overlap_metrics(fig, labels, width, height)
    metrics["label_count"] = len(labels)
    adjustments["__metrics__"] = metrics

    label_adjustments_path = output_path.parent / _LABEL_ADJUSTMENTS_NAME
    label_adjustments_path.write_text(
        json.dumps(adjustments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fmt = "svg" if config.typegraph == "svg" else "png"
    final_output = output_path if output_path.suffix.lower() == f".{fmt}" else output_path.with_suffix(f".{fmt}")
    fig.savefig(
        str(final_output),
        format=fmt,
        facecolor="white",
        dpi=dpi if fmt == "png" else 72,
    )
    plt.close(fig)
    return final_output


# ---------------------------------------------------------------------------
# Font size computation (rank-based)
# ---------------------------------------------------------------------------

def _compute_font_sizes(graph: SimilitudeGraph) -> Dict[str, float]:
    n = len(graph.vocabulary)
    if n == 0:
        return {}
    if n <= 15:
        fmin, fmax = 8.0, 62.0
    elif n <= 30:
        fmin, fmax = 6.0, 58.0
    elif n <= 50:
        fmin, fmax = 5.0, 54.0
    elif n <= 80:
        fmin, fmax = 4.0, 48.0
    elif n <= 120:
        fmin, fmax = 4.0, 40.0
    else:
        fmin, fmax = 3.5, 32.0

    freqs = graph.term_frequencies
    if n == 1 or freqs.max() <= freqs.min():
        return {v: (fmin + fmax) / 2 for v in graph.vocabulary}

    ranks = np.argsort(np.argsort(freqs)).astype(np.float64)
    normalized = (ranks / max(n - 1, 1)) ** 1.3
    sizes = fmin + normalized * (fmax - fmin)
    return {graph.vocabulary[i]: float(sizes[i]) for i in range(n)}


# ---------------------------------------------------------------------------
# Matplotlib fallback renderer
# ---------------------------------------------------------------------------

def _render_with_matplotlib(
    graph: SimilitudeGraph,
    output_path: Path,
    config: SimilitudeConfig,
) -> Path:
    """Matplotlib fallback renderer (used when R is not available)."""
    cfg = config
    output_path = Path(output_path)

    G = graph.graph
    pos = graph.positions
    communities = graph.communities
    n_nodes = G.number_of_nodes()
    nodes = list(G.nodes())

    dpi = 150
    fig, ax = plt.subplots(1, 1, figsize=(cfg.width / dpi, cfg.height / dpi), dpi=dpi)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    font_sizes = _compute_font_sizes(graph)

    all_x = [pos[n][0] for n in nodes if n in pos]
    all_y = [pos[n][1] for n in nodes if n in pos]
    if not all_x:
        plt.close(fig)
        raise ValueError("No node positions available")

    extent = max(max(all_x) - min(all_x), max(all_y) - min(all_y), 1.0) if len(all_x) > 1 else 1.0
    halo_padding = extent * 0.35

    # 1. Halos
    if cfg.show_halo and not cfg.grayscale:
        comm_nodes: Dict[int, List[str]] = {}
        for node, cid in communities.items():
            if node in pos:
                comm_nodes.setdefault(cid, []).append(node)
        for cid, node_list in comm_nodes.items():
            if len(node_list) < 1:
                continue
            points = np.array([[pos[n][0], pos[n][1]] for n in node_list])
            style = _get_community_style(cid)
            _draw_organic_halo(ax, points, color=style["halo"], alpha=0.30, padding=halo_padding)

    # 2. Bézier edges
    edge_data = list(G.edges(data=True))
    if edge_data:
        weights = [d.get("weight", 1.0) for _, _, d in edge_data]
        max_w, min_w = max(weights), min(weights)
        w_range = max(max_w - min_w, 1e-10)

        all_segs, all_widths, edge_labels = [], [], []
        for idx, (u, v, data) in enumerate(edge_data):
            if u not in pos or v not in pos:
                continue
            w = data.get("weight", 1.0)
            flip = bool(idx % 2)
            curve_pts = _bezier_points(pos[u], pos[v], curvature=0.25, n=20, flip=flip)
            all_segs.append(curve_pts)
            norm_w = (w - min_w) / w_range
            all_widths.append(2.0 + norm_w * 10.0)

            if cfg.show_edge_labels:
                mid_idx = len(curve_pts) // 2
                mx, my = curve_pts[mid_idx]
                if isinstance(w, float) and w == int(w):
                    label_text = str(int(w))
                elif w >= 10:
                    label_text = f"{w:.0f}"
                else:
                    label_text = f"{w:.2f}"
                edge_labels.append((mx, my, label_text))

        if all_segs:
            ax.add_collection(LineCollection(
                all_segs, colors="#333333", linewidths=all_widths,
                alpha=0.90, zorder=1, capstyle="round"))

        if cfg.show_edge_labels and edge_labels:
            for mx, my, lt in edge_labels:
                ax.text(mx, my, lt, fontsize=7.5, color="#111111", fontweight="bold",
                    ha="center", va="center", zorder=3, fontfamily=cfg.font_family,
                    bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="none", alpha=0.90))

    # 3. Axis limits
    xr = max(all_x) - min(all_x) if len(all_x) > 1 else 1.0
    yr = max(all_y) - min(all_y) if len(all_y) > 1 else 1.0
    ax.set_xlim(min(all_x) - xr * 0.20, max(all_x) + xr * 0.20)
    ax.set_ylim(min(all_y) - yr * 0.20, max(all_y) + yr * 0.20)

    # 4. Labels
    fig.canvas.draw()
    labels_info = []
    for node in sorted(nodes, key=lambda n: font_sizes.get(n, 0), reverse=True):
        if node not in pos:
            continue
        x, y = pos[node]
        fs = font_sizes.get(node, 5.0)
        col = "#333333" if cfg.grayscale else _get_community_style(communities.get(node, 0))["text"]
        fw = "bold" if fs > 7 else "normal"
        t = ax.text(x, y, str(node), fontsize=fs, fontfamily=cfg.font_family,
            fontweight=fw, color=col, ha="center", va="center", zorder=4)
        labels_info.append({"text_obj": t, "x": x, "y": y, "node": node, "fontsize": fs})

    # 5. Label overlap resolution
    fig.canvas.draw()
    _resolve_label_overlaps(ax, labels_info, max_iterations=800, speed=1.0)
    fig.canvas.draw()

    # 6. Expand axis
    inv = ax.transData.inverted()
    renderer = fig.canvas.get_renderer()
    lx_min, lx_max = float("inf"), float("-inf")
    ly_min, ly_max = float("inf"), float("-inf")
    for info in labels_info:
        bb = inv.transform_bbox(info["text_obj"].get_window_extent(renderer=renderer))
        lx_min, lx_max = min(lx_min, bb.x0), max(lx_max, bb.x1)
        ly_min, ly_max = min(ly_min, bb.y0), max(ly_max, bb.y1)
    if lx_min < float("inf"):
        ax.set_xlim(lx_min - (lx_max - lx_min) * 0.05, lx_max + (lx_max - lx_min) * 0.05)
        ax.set_ylim(ly_min - (ly_max - ly_min) * 0.05, ly_max + (ly_max - ly_min) * 0.05)
    fig.canvas.draw()

    # 7. Save
    fig.tight_layout(pad=0.3)
    fmt = "svg" if cfg.typegraph == "svg" else "png"
    if not str(output_path).lower().endswith(f".{fmt}"):
        output_path = output_path.with_suffix(f".{fmt}")
    fig.savefig(str(output_path), format=fmt, bbox_inches="tight",
        facecolor="white", dpi=dpi if fmt == "png" else 72)
    plt.close(fig)

    log.info(f"Similitude graph rendered (matplotlib): {n_nodes} nodes -> {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Main entry point — dual renderer
# ---------------------------------------------------------------------------

def render_similitude(
    graph: SimilitudeGraph,
    output_path: Path,
    config: Optional[SimilitudeConfig] = None,
    matrix: Optional[SimilitudeMatrix] = None,
) -> Path:
    """
    Render the similitude graph as a publication-quality image.

    Uses R/igraph when available to generate a raw auditable output and
    a readable presentation derived from layout_raw.json. Falls back to
    matplotlib only when explicitly requested or in auto mode.
    """
    cfg = config or graph.config
    output_path = Path(output_path)
    backend = str(getattr(cfg, "renderer_backend", "auto") or "auto").strip().lower()

    if backend == "python":
        return _render_with_matplotlib(graph, output_path, cfg)

    if backend == "iramuteq_r":
        rscript = _find_rscript()
        if rscript is None:
            raise RuntimeError(
                "R/igraph renderer is required in strict IRaMuTeQ mode, "
                "but Rscript was not found."
            )
        env_info, r_env = _probe_and_repair_strict_r(rscript, output_path.parent)
        missing_packages = env_info.get("missing_packages", [])
        if missing_packages:
            raise RuntimeError(
                "R/igraph renderer is required in strict IRaMuTeQ mode, "
                f"but these R packages are missing after repair attempt in the configured R: {', '.join(missing_packages)}. "
                "Install the packages in this R version or switch to the experimental Python renderer."
            )
        if not env_info.get("capabilities", {}).get("cairo", False):
            raise RuntimeError(
                "R/igraph renderer is required in strict IRaMuTeQ mode, "
                "but the R installation does not report cairo support."
            )
        result = _render_with_r(graph, output_path, cfg, rscript, matrix=matrix, env=r_env)
        if result is None:
            raise RuntimeError(
                "R/igraph renderer failed in strict IRaMuTeQ mode."
            )
        # In strict IRaMuTeQ mode, use the R-generated PNG directly
        # without re-rendering through matplotlib.  The R output uses
        # sna::gplot.layout.fruchtermanreingold + igraph::plot which
        # matches IRaMuTeQ's visual pipeline exactly.
        if getattr(cfg, "strict_iramuteq_style", False):
            shutil.copy2(str(result), str(output_path))
            return output_path
        layout_path = output_path.parent / _LAYOUT_RAW_NAME
        if layout_path.exists():
            return _render_readable_from_layout(layout_path, output_path, cfg)
        shutil.copy2(str(result), str(output_path))
        return output_path

    # Auto mode: try R/igraph first, then fall back to matplotlib.
    rscript = _find_rscript()
    if rscript is not None:
        log.info("R detected: %s — using R/igraph renderer", rscript)
        try:
            r_env = _r_env_for_executor(_r_executor_for_rscript(rscript))
        except Exception:
            r_env = None
        result = _render_with_r(graph, output_path, cfg, rscript, matrix=matrix, env=r_env)
        if result is not None:
            layout_path = output_path.parent / _LAYOUT_RAW_NAME
            if layout_path.exists():
                return _render_readable_from_layout(layout_path, output_path, cfg)
            shutil.copy2(str(result), str(output_path))
            return output_path
        log.warning("R rendering failed, falling back to matplotlib")
    else:
        log.info("R not found — using matplotlib renderer")

    # Fallback to matplotlib
    return _render_with_matplotlib(graph, output_path, cfg)
