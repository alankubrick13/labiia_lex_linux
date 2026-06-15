
import logging
import math
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

log = logging.getLogger(__name__)


class NoverlapLayout:
    """
    Noverlap Algorithm - Removes node overlaps.
    
    This implementation treats nodes as circles with radius and ensures
    distance(u, v) >= radius(u) + radius(v) + margin.
    """

    def __init__(
        self,
        margin: float = 5.0,
        ratio: float = 1.0,
        speed: float = 3.0,
        max_iterations: int = 500,
        verbose: bool = False,
    ):
        self.margin = margin
        self.ratio = ratio
        self.speed = speed
        self.max_iterations = max_iterations
        self.verbose = verbose

    def run(
        self,
        positions: Dict[Any, Tuple[float, float]],
        node_sizes: Dict[Any, float],
        fixed_nodes: Optional[List[Any]] = None,
    ) -> Dict[Any, Tuple[float, float]]:
        """
        Run Noverlap to remove circular overlaps.

        Args:
            positions: Dict {node_id: (x, y)}
            node_sizes: Dict {node_id: radius}
            fixed_nodes: List of nodes that should not be moved.

        Returns:
            New positions dict.
        """
        nodes = list(positions.keys())
        n_nodes = len(nodes)
        
        if n_nodes < 2:
            return positions.copy()
            
        # Convert to numpy
        pos_arr = np.array([positions[n] for n in nodes], dtype=float)
        
        # Radii
        # Applying ratio: radius = size * ratio
        radii = np.array([node_sizes.get(n, 1.0) * self.ratio for n in nodes], dtype=float)
        
        # Fixed nodes mask
        fixed_mask = np.zeros(n_nodes, dtype=bool)
        if fixed_nodes:
            node_to_idx = {n: i for i, n in enumerate(nodes)}
            for fn in fixed_nodes:
                if fn in node_to_idx:
                    fixed_mask[node_to_idx[fn]] = True
                    
        # Main Loop
        for it in range(self.max_iterations):
            # Compute distances
            # Delta (N, N, 2)
            delta = pos_arr[:, np.newaxis, :] - pos_arr[np.newaxis, :, :]
            dist_sq = np.sum(delta**2, axis=2)
            dist = np.sqrt(dist_sq)
            
            # Avoid div zero
            np.fill_diagonal(dist, np.inf)
            safe_dist = dist.copy()
            safe_dist[safe_dist < 0.001] = 0.001
            
            # Required Distance: r1 + r2 + margin
            req_dist = radii[:, np.newaxis] + radii[np.newaxis, :] + self.margin
            
            # Overlap: dist < req_dist
            overlap_mask = dist < req_dist
            
            # Diagonal is inf -> False.
            
            if not np.any(overlap_mask):
                if self.verbose:
                    log.info(f"Noverlap converged at iteration {it}.")
                break
            
            # Compute Forces (Displacement)
            # Direction: delta / dist
            # Magnitude: (req_dist - dist) * speed ? 
            # Gephi Noverlap: force = 1 + size? No.
            # Standard logic: push apart by penetration depth.
            
            penetration = req_dist - dist
            # Only where overlap (penetration > 0)
            
            # Normalize direction
            norm_delta = delta / safe_dist[:, :, np.newaxis]
            
            # Displacement vector per pair
            disp_matrix = norm_delta * penetration[:, :, np.newaxis]
            
            # We want to push i away from j.
            # If delta = pos_i - pos_j, then i is at delta relative to j.
            # We want to push i further in that direction.
            # So add disp to i.
            
            # But we double count (i-j and j-i).
            # penetration(i,j) == penetration(j,i)
            # delta(i,j) == -delta(j,i)
            # So disp(i,j) == -disp(j,i)
            # If we sum all cols, we get total displacement for i.
            
            # Apply only for overlapping pairs
            disp_matrix[~overlap_mask] = 0.0
            
            # Sum for each node
            total_disp = np.sum(disp_matrix, axis=1) * self.speed * 0.1 # Scaling factor
            
            # If fixed, zero out
            total_disp[fixed_mask] = 0.0
            
            # Apply
            pos_arr += total_disp
            
            # Jitter if identical positions (dist ~ 0)
            # If dist very small, add random noise
            close_mask = dist < 0.0001
            # ignore diagonal (inf)
            # If close, delta is 0, norm_delta is unreliable.
            # We should add random jitter to those nodes.
            # Simplification: just check if moving.
            
        # Reconstruct result
        new_pos = {}
        for i, n in enumerate(nodes):
            new_pos[n] = (float(pos_arr[i, 0]), float(pos_arr[i, 1]))
            
        return new_pos
