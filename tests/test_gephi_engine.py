
import pytest
import networkx as nx
import numpy as np
import logging
import sys
from pathlib import Path

# Ensure src imports resolve when pytest is launched from project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Fix imports if needed? 
# Pytest adds root to sys.path usually.
# We import from src.analysis.gephi.pipeline
from src.analysis.gephi.pipeline import GephiPipeline
from src.analysis.gephi.forceatlas2 import ForceAtlas2
from src.analysis.gephi.noverlap import NoverlapLayout
from src.analysis.gephi.label_adjust import LabelAdjust

log = logging.getLogger(__name__)

def test_forceatlas2_initialization():
    fa2 = ForceAtlas2(scaling_ratio=10.0)
    assert fa2.scaling_ratio == 10.0

def test_forceatlas2_run_basic():
    G = nx.erdos_renyi_graph(20, 0.2, seed=42)
    fa2 = ForceAtlas2()
    pos = fa2.run(G, iterations=50)
    assert len(pos) == 20
    assert isinstance(pos[0], tuple)

def test_noverlap_run_basic():
    G = nx.Graph()
    G.add_node(0)
    G.add_node(1)
    
    # Place nodes overlapping
    pos = {0: (0.0, 0.0), 1: (1.0, 0.0)}
    sizes = {0: 5.0, 1: 5.0} # Radius 5, sum 10. Dist 1. Overlap!
    
    no = NoverlapLayout(max_iterations=50, margin=0.0)
    new_pos = no.run(pos, sizes)
    
    p0 = new_pos[0]
    p1 = new_pos[1]
    dist = np.sqrt((p0[0]-p1[0])**2 + (p0[1]-p1[1])**2)
    
    # Should be pushed to at least 10.0
    assert dist >= 9.9 # allow small float error or incomplete convergence

def test_label_adjust_run_basic():
    G = nx.Graph()
    # Overlapping labels
    pos = {0: (0.0, 0.0), 1: (2.0, 0.0)}
    sizes = {0: (10.0, 5.0), 1: (10.0, 5.0)} # Width 10. Half 5.
    # Node 0: x=0. Range [-5, 5]
    # Node 1: x=2. Range [-3, 7]
    # Overlap interval [-3, 5]. Overlap!
    
    la = LabelAdjust(max_iterations=50)
    new_pos = la.run(pos, sizes)
    
    x0, y0 = new_pos[0]
    x1, y1 = new_pos[1]
    
    # Check if overlap is resolved
    # Required distance (sum of half dims)
    # Width 10 -> half 5. Height 5 -> half 2.5.
    # Margin is default 2.0 -> added to size? 
    # LabelAdjust adds margin to size internally.
    # internal_w = 10 + 2 = 12. half_w = 6.
    # internal_h = 5 + 2 = 7. half_h = 3.5.
    
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    
    # Must be separated in at least one dimension
    # accounting for small float error
    separated_x = dx >= (6.0 + 6.0 - 0.1) 
    separated_y = dy >= (3.5 + 3.5 - 0.1)
    
    assert separated_x or separated_y, f"Still overlapping! dx={dx}, dy={dy}"
    
def test_full_pipeline_visual_artifact():
    """Generates a visual artifact to verify the hairball fix."""
    G = nx.Graph()
    G.add_edge("Hub", "A", weight=10)
    G.add_edge("Hub", "B", weight=10)
    G.add_edge("Hub", "C", weight=10)
    # Cluster A
    for i in range(5):
        G.add_edge("A", f"A{i}", weight=2)
    
    pipeline = GephiPipeline(verbose=True)
    pos = pipeline.run(
        G, 
        params={
            "fa2_scaling": 20.0, 
            "fa2_gravity": 1.0,
            "noverlap_enabled": True,
            "label_adjust": True
        },
        node_sizes={n: 2.0 for n in G.nodes()},
        label_sizes={n: (10.0, 5.0) for n in G.nodes()}
    )
    
    assert len(pos) == len(G.nodes())
    
    # Save dummy plot
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    for n, (x, y) in pos.items():
        ax.text(x, y, n, ha='center', va='center', bbox=dict(facecolor='white', alpha=0.5))
        ax.scatter([x], [y])
        
    out = Path("tmp_verify/gephi_test_artifact.png")
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out)
    print(f"Artifact saved to {out}")

