
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx

from .forceatlas2 import ForceAtlas2
from .noverlap import NoverlapLayout
from .label_adjust import LabelAdjust

log = logging.getLogger(__name__)


class GephiPipeline:
    """
    Orchestrates the Gephi-like layout pipeline.
    
    Sequence:
    1. ForceAtlas2 (Global Layout)
    2. Noverlap (Prevent Node overlap)
    3. LabelAdjust (Prevent Label overlap)
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def run(
        self,
        graph: nx.Graph,
        params: Dict[str, Any],
        initial_pos: Optional[Dict[Any, Tuple[float, float]]] = None,
        node_sizes: Optional[Dict[Any, float]] = None,
        label_sizes: Optional[Dict[Any, Tuple[float, float]]] = None,
        fixed_nodes: Optional[List[Any]] = None,
    ) -> Dict[Any, Tuple[float, float]]:
        """
        Run the full layout pipeline.

        Args:
            graph: NetworkX graph.
            params: Configuration dict (see defaults below).
            initial_pos: Optional initial positions.
            node_sizes: Dict {node_id: radius} for Noverlap.
            label_sizes: Dict {node_id: (w, h)} for LabelAdjust.
            fixed_nodes: List of fixed nodes.

        Returns:
            Final positions dict {node_id: (x, y)}.
        """
        # 1. Extract Parameters
        # ForceAtlas2
        fa2_iter = int(params.get("fa2_iterations", 3000))
        fa2_scaling = float(params.get("fa2_scaling", 50.0))
        fa2_gravity = float(params.get("fa2_gravity", 0.8))
        # Note: adjust_sizes in FA2 is for *node* overlap during layout.
        # usually we want Noverlap as a separate step for better control.
        fa2_adjust_sizes = bool(params.get("adjust_sizes", False)) 
        
        # Noverlap
        noverlap_enabled = bool(params.get("noverlap_enabled", True))
        noverlap_iter = int(params.get("noverlap_iterations", 100))
        noverlap_margin = float(params.get("noverlap_margin", 5.0))
        noverlap_speed = float(params.get("noverlap_speed", 3.0))
        noverlap_ratio = float(params.get("noverlap_ratio", 1.2))
        
        # LabelAdjust
        label_adjust_enabled = bool(
            params.get("label_adjust", params.get("label_adjust_enabled", True))
        )
        label_adjust_iter = int(params.get("label_adjust_iterations", 500))
        label_adjust_speed = float(params.get("label_adjust_speed", 1.0))
        label_margin = float(params.get("label_margin", 2.0))
        
        # 2. Run ForceAtlas2
        if self.verbose:
            log.info("Starting ForceAtlas2...")
            
        fa2 = ForceAtlas2(
            scaling_ratio=fa2_scaling,
            gravity=fa2_gravity,
            adjust_sizes=fa2_adjust_sizes,
            lin_log_mode=bool(params.get("fa2_lin_log", False)),
            outbound_attraction_distribution=bool(params.get("fa2_outbound_attraction", True)),
            edge_weight_influence=float(params.get("fa2_edge_weight_influence", 0.8)),
            verbose=self.verbose
        )
        
        positions = fa2.run(
            graph,
            iterations=fa2_iter,
            pos=initial_pos,
            weight_attr="weight",
            node_sizes=node_sizes # Used if adjust_sizes=True
        )
        
        # 3. Run Noverlap (Node Collision)
        if noverlap_enabled and node_sizes:
            if self.verbose:
                log.info("Starting Noverlap...")
            no = NoverlapLayout(
                margin=noverlap_margin,
                ratio=noverlap_ratio,
                speed=noverlap_speed,
                max_iterations=noverlap_iter,
                verbose=self.verbose
            )
            positions = no.run(positions, node_sizes, fixed_nodes)
            
        # 4. Run LabelAdjust (Text Collision)
        if label_adjust_enabled and label_sizes:
            if self.verbose:
                log.info("Starting LabelAdjust...")
            la = LabelAdjust(
                speed=label_adjust_speed,
                max_iterations=label_adjust_iter,
                margin=label_margin,
                verbose=self.verbose
            )
            positions = la.run(positions, label_sizes, fixed_nodes)
            
        return positions
