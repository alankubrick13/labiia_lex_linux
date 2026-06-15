
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

log = logging.getLogger(__name__)


class LabelAdjust:
    """
    LabelAdjust Algorithm - Removes rectangular label overlaps.
    
    This is a post-processing step. It treats labels as Axis-Aligned Bounding Boxes (AABB)
    and pushes them apart.
    """

    def __init__(
        self,
        speed: float = 1.0,
        max_iterations: int = 500,
        margin: float = 2.0,
        verbose: bool = False,
    ):
        self.speed = speed
        self.max_iterations = max_iterations
        self.margin = margin
        self.verbose = verbose

    def run(
        self,
        positions: Dict[Any, Tuple[float, float]],
        sizes: Dict[Any, Tuple[float, float]], # (width, height)
        fixed_nodes: Optional[List[Any]] = None,
    ) -> Dict[Any, Tuple[float, float]]:
        """
        Run LabelAdjust.

        Args:
            positions: Dict {node_id: (x, y)} (Center of the label)
            sizes: Dict {node_id: (width, height)}
            fixed_nodes: List of nodes/labels that should not move.

        Returns:
            New positions dict.
        """
        nodes = list(positions.keys())
        n_nodes = len(nodes)
        
        if n_nodes < 2:
            return positions.copy()
            
        # Convert to arrays
        # Pos: (N, 2)
        pos_arr = np.array([positions[n] for n in nodes], dtype=float)
        
        # Sizes: (N, 2) [w, h]
        # Add margin to size
        size_arr = np.array([sizes.get(n, (0.0, 0.0)) for n in nodes], dtype=float)
        size_arr += self.margin
        
        # Fixed mask
        fixed_mask = np.zeros(n_nodes, dtype=bool)
        if fixed_nodes:
            idx_map = {n: i for i, n in enumerate(nodes)}
            for fn in fixed_nodes:
                if fn in idx_map:
                    fixed_mask[idx_map[fn]] = True
        
        # Precompute half-sizes for AABB
        half_sizes = size_arr / 2.0
        
        # Constants
        speed = self.speed
        
        for it in range(self.max_iterations):
            # Broadcast positions
            # x (N, 1) and (1, N)
            x = pos_arr[:, 0]
            y = pos_arr[:, 1]
            
            # Distance between centers
            dx = x[:, np.newaxis] - x[np.newaxis, :] # x_i - x_j
            dy = y[:, np.newaxis] - y[np.newaxis, :]
            
            # Absolute distance
            abs_dx = np.abs(dx)
            abs_dy = np.abs(dy)
            
            # Required distance (sum of half widths)
            w_sum = half_sizes[:, 0][:, np.newaxis] + half_sizes[:, 0][np.newaxis, :]
            h_sum = half_sizes[:, 1][:, np.newaxis] + half_sizes[:, 1][np.newaxis, :]
            
            # Check overlap logic
            # Overlap if abs_dx < w_sum AND abs_dy < h_sum
            overlap_x = abs_dx < w_sum
            overlap_y = abs_dy < h_sum
            
            overlap_mask = overlap_x & overlap_y
            
            # Ignore self
            np.fill_diagonal(overlap_mask, False)
            
            if self.verbose and it == 0:
                log.info(f"Iter 0 Overlaps: {np.sum(overlap_mask)}")
                # print(f"DEBUG: Overlap Mask:\n{overlap_mask}")
                # print(f"DEBUG: dx:\n{dx}")
                # print(f"DEBUG: w_sum:\n{w_sum}")
            
            if not np.any(overlap_mask):
                if self.verbose:
                    log.info(f"LabelAdjust converged at iteration {it}.")
                break
            
            # Compute Penetration
            pen_x = w_sum - abs_dx
            pen_y = h_sum - abs_dy
            
            # Only where overlapping
            pen_x[~overlap_mask] = 0
            pen_y[~overlap_mask] = 0
            
            # Push Logic:
            # We push along the axis of MINIMAL penetration (easiest way out)
            # If pen_x < pen_y: Push X
            # Else: Push Y
            
            push_x_mask = overlap_mask & (pen_x < pen_y)
            push_y_mask = overlap_mask & (pen_x >= pen_y)
            
            # Displacement Accumulator
            disp_x = np.zeros((n_nodes, n_nodes))
            disp_y = np.zeros((n_nodes, n_nodes))
            
            # Direction of push
            # If i overlaps j:
            # If x_i > x_j (dx > 0), push i Right (+).
            # If x_i < x_j (dx < 0), push i Left (-).
            sig_x = np.sign(dx)
            sig_y = np.sign(dy)
            
            # Fix zeros (exact overlap)
            # Use indices to break ties deterministically
            # i (rows) vs j (cols)
            # If i > j: push positive. If i < j: push negative.
            
            indices_i = np.arange(n_nodes)[:, np.newaxis]
            indices_j = np.arange(n_nodes)[np.newaxis, :]
            
            # Mask where diff is zero
            zero_x = (dx == 0)
            zero_y = (dy == 0)
            
            if np.any(zero_x):
                # Where dx=0, use index comparison
                tie_break = 2.0 * (indices_i > indices_j).astype(float) - 1.0
                # ONLY apply where dx==0.
                sig_x[zero_x] = tie_break[zero_x]
                
            if np.any(zero_y):
                tie_break = 2.0 * (indices_i > indices_j).astype(float) - 1.0
                sig_y[zero_y] = tie_break[zero_y]
            
            # Force Magnitude = Penetration
            # Applying speed factor
            
            # Push X
            # Disp[i, j] = sig_x * pen_x * speed
            # But we want total displacement on i.
            # disp_x[i] = sum_j ( repulsion from j )
            
            # Where push_x_mask is True:
            disp_x[push_x_mask] = sig_x[push_x_mask] * pen_x[push_x_mask] * speed
            
            # Push Y
            disp_y[push_y_mask] = sig_y[push_y_mask] * pen_y[push_y_mask] * speed
            
            # Sum for each node
            total_dx = np.sum(disp_x, axis=1)
            total_dy = np.sum(disp_y, axis=1)
            
            # Apply Fixed Mask
            total_dx[fixed_mask] = 0
            total_dy[fixed_mask] = 0
            
            # Update
            # We might overshoot if speed is high. 
            # A damping factor (0.1?) helps stability.
            # Standard Gephi Noverlap uses coefficient.
            # Let's dampen slightly to avoid oscillation.
            
            damp = 0.2
            pos_arr[:, 0] += total_dx * damp
            pos_arr[:, 1] += total_dy * damp
            
        # Result
        new_pos = {}
        for i, n in enumerate(nodes):
            new_pos[n] = (float(pos_arr[i, 0]), float(pos_arr[i, 1]))
            
        return new_pos
