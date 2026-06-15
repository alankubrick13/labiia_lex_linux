
import logging
import math
import random
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)


class GephiNoverlap:
    """
    Python implementation of Gephi's Noverlap algorithm.
    Pushes nodes apart based on their exact visual radius.
    """

    def __init__(self, speed: float = 3.0, ratio: float = 1.2, margin: float = 5.0, max_iterations: int = 50):
        self.speed = speed
        self.ratio = ratio
        self.margin = margin
        self.max_iterations = max_iterations

    def run(self, positions: Dict[Any, Tuple[float, float]], sizes: Dict[Any, float]) -> Dict[Any, Tuple[float, float]]:
        nodes = list(positions.keys())
        n_nodes = len(nodes)
        if n_nodes < 2:
            return positions.copy()
            
        pos_arr = np.array([positions[n] for n in nodes], dtype=float)
        # Gephi size is treated as diameter usually, so radius is size / 2
        # But let's follow the standard interpretation: effective radius = (size/2) * ratio + margin
        size_arr = np.array([sizes.get(n, 10.0) / 2.0 for n in nodes], dtype=float)
        
        radii = size_arr * self.ratio + self.margin
        
        log.info("[Noverlap] Starting node collision resolution for %d nodes...", n_nodes)
        
        for it in range(self.max_iterations):
            # Pairwise differences
            diff_x = pos_arr[:, 0:1] - pos_arr[:, 0:1].T
            diff_y = pos_arr[:, 1:2] - pos_arr[:, 1:2].T
            dist_sq = diff_x**2 + diff_y**2
            dist = np.sqrt(dist_sq)
            
            min_dist = radii[:, None] + radii[None, :]
            
            mask = (dist < min_dist) & (dist > 0)
            np.fill_diagonal(mask, False)
            
            if not np.any(mask):
                break
                
            # Displacement = (min_dist - dist) * speed * 0.5
            pen = (min_dist - dist) * 0.5 * self.speed
            dist_safe = np.maximum(dist, 1e-9)
            
            dx_force = np.where(mask, (diff_x / dist_safe) * pen, 0.0)
            dy_force = np.where(mask, (diff_y / dist_safe) * pen, 0.0)
            
            overlap_count = np.sum(mask, axis=1)
            overlap_count_safe = np.maximum(1, overlap_count)
            
            # Dampen the force and clamp max displacement to 10% of layout span
            dx_step = (np.sum(dx_force, axis=1) / overlap_count_safe) * 0.8
            dy_step = (np.sum(dy_force, axis=1) / overlap_count_safe) * 0.8
            span_x = pos_arr[:, 0].max() - pos_arr[:, 0].min()
            span_y = pos_arr[:, 1].max() - pos_arr[:, 1].min()
            max_dx = max(span_x * 0.10, 1.0)
            max_dy = max(span_y * 0.10, 1.0)
            dx_step = np.clip(dx_step, -max_dx, max_dx)
            dy_step = np.clip(dy_step, -max_dy, max_dy)
            pos_arr[:, 0] += dx_step
            pos_arr[:, 1] += dy_step
            
        return {n: (float(pos_arr[i, 0]), float(pos_arr[i, 1])) for i, n in enumerate(nodes)}


class GephiLabelAdjust:
    """
    Python implementation of Gephi's Label Adjust algorithm.
    
    This algorithm iteratively moves nodes to preventing their labels (assumed to be bounding boxes) 
    from overlapping. It is a post-processing step after the main layout.
    """

    def __init__(self, speed: float = 1.0, max_iterations: int = 500, margin: float = 2.0):
        self.speed = speed
        self.max_iterations = max_iterations
        self.margin = margin  # Margin in pixels (or units) around label

    def run(
        self,
        positions: Dict[Any, Tuple[float, float]],
        sizes: Dict[Any, Tuple[float, float]],
        fixed_nodes: Optional[List[Any]] = None
    ) -> Dict[Any, Tuple[float, float]]:
        """
        Adjust positions to remove label overlaps.
        
        Args:
            positions: Dict {node_id: (x, y)}
            sizes: Dict {node_id: (width, height)} - Label dimensions
            fixed_nodes: List of nodes that should not move (optional)
        
        Returns:
            New positions dict.
        """
        nodes = list(positions.keys())
        n_nodes = len(nodes)
        
        if n_nodes < 2:
            return positions.copy()
            
        # Convert to numpy arrays for speed
        # pos_arr: [[x, y], ...]
        # size_arr: [[w, h], ...]
        pos_arr = np.zeros((n_nodes, 2))
        size_arr = np.zeros((n_nodes, 2))
        
        node_to_idx = {n: i for i, n in enumerate(nodes)}
        
        for i, n in enumerate(nodes):
            x, y = positions[n]
            pos_arr[i] = [x, y]
            w, h = sizes.get(n, (0.0, 0.0))
            # Add margin
            size_arr[i] = [w + self.margin, h + self.margin]
            
        fixed_mask = np.zeros(n_nodes, dtype=bool)
        if fixed_nodes:
            for fn in fixed_nodes:
                if fn in node_to_idx:
                    fixed_mask[node_to_idx[fn]] = True
                    
        # Main Loop
        speed = self.speed
        
        for it in range(self.max_iterations):
            if it == 0:
                 log.info("[LabelAdjust] Starting label overlap correction for %d labels...", n_nodes)
            displacement = np.zeros((n_nodes, 2))
            overlaps_found = 0
            
            # Naive N^2 check is fine for typical label counts (<500).
            # For larger, Spatial Hashing (Grid) is needed.
            # Let's assess if we need optimization.
            # If N=500, N^2 = 250,000 checks. Done in ms in C++, fast enough in Numpy?
            # Creating a distance matrix is fast.
            # But checking box overlap is specific.
            # Let's try vectorized approach.
            
            # Broadcasting:
            # x1 (N,1), x2 (1,N)
            
            inputs_x = pos_arr[:, 0]
            inputs_y = pos_arr[:, 1]
            inputs_w = size_arr[:, 0]
            inputs_h = size_arr[:, 1]
            
            # Bounding box coords
            # Left, Right, Bottom, Top
            # Assuring centered at x,y
            l = inputs_x - inputs_w / 2
            r = inputs_x + inputs_w / 2
            b = inputs_y - inputs_h / 2
            t = inputs_y + inputs_h / 2
            
            # Matrices (N, N)
            # L[i, j] = l[i]
            # We want to check if i and j overlap.
            # Overlap condition:
            # not (r1 < l2 or l1 > r2 or t1 < b2 or b1 > t2)
            # dist_x = center_dist_x - (w1 + w2)/2
            # dist_y = center_dist_y - (h1 + h2)/2
            # If dist_x < 0 and dist_y < 0 -> overlap
            
            diff_x = inputs_x[:, None] - inputs_x[None, :] # (N, N) x_i - x_j
            abs_diff_x = np.abs(diff_x)
            sum_w_half = (inputs_w[:, None] + inputs_w[None, :]) / 2.0
            
            diff_y = inputs_y[:, None] - inputs_y[None, :]
            abs_diff_y = np.abs(diff_y)
            sum_h_half = (inputs_h[:, None] + inputs_h[None, :]) / 2.0
            
            overlap_x = abs_diff_x < sum_w_half
            overlap_y = abs_diff_y < sum_h_half
            
            masks = overlap_x & overlap_y
            
            # Ignore self-overlap (diagonal)
            np.fill_diagonal(masks, False)
            
            if not np.any(masks):
                break # Converged
                
            # Compute forces for overlapping pairs
            # We push apart on the axis of *minimal* penetration (usually easier to fix).
            # Penetration depth:
            pen_x = sum_w_half - abs_diff_x
            pen_y = sum_h_half - abs_diff_y
            
            # Only where mask is True
            # To avoid messing up logic, let's iterate indices where mask is True.
            # (Or vector logic)
            
            # Determine axis:
            # If pen_x < pen_y: move X
            # Else: move Y
            
            # Vectorized axis choice
            move_x_mask = masks & (pen_x < pen_y)
            move_y_mask = masks & (pen_x >= pen_y)
            
            # Calculate displacements
            # If moving X: direction is sign(diff_x). 
            # If diff_x is 0 (exact center overlap), random direction.
            
            # X displacement
            # Force magnitude = pen_x * speed? Or simply pen_x to resolve?
            # Standard Noverlap: Force = overlap
            
            dx_force = np.zeros_like(diff_x)
            dy_force = np.zeros_like(diff_y)
            
            # Handle X moves
            sx = np.sign(diff_x)
            # Fix zeros
            sx[sx==0] = 1.0 # arbitrary
            
            # We want to move i away from j.
            # If x_i > x_j, diff > 0, sign +1. We move +1 (right). Correct.
            
            dx_force[move_x_mask] = sx[move_x_mask] * pen_x[move_x_mask] * speed
            
            # Handle Y moves
            sy = np.sign(diff_y)
            sy[sy==0] = 1.0
            
            dy_force[move_y_mask] = sy[move_y_mask] * pen_y[move_y_mask] * speed
            
            # Total displacement per node
            overlap_count = np.sum(masks, axis=1)
            overlap_count_safe = np.maximum(1, overlap_count)
            
            # Vectorized sum of forces — clamped to prevent scattering
            disp_x_sum = (np.sum(dx_force, axis=1) / overlap_count_safe) * 0.5
            disp_y_sum = (np.sum(dy_force, axis=1) / overlap_count_safe) * 0.5

            # Clamp max displacement to 15% of layout span
            span_x = pos_arr[:, 0].max() - pos_arr[:, 0].min()
            span_y = pos_arr[:, 1].max() - pos_arr[:, 1].min()
            max_dx = max(span_x * 0.15, 1.0)
            max_dy = max(span_y * 0.15, 1.0)
            disp_x_sum = np.clip(disp_x_sum, -max_dx, max_dx)
            disp_y_sum = np.clip(disp_y_sum, -max_dy, max_dy)

            # Apply fixed mask
            disp_x_sum[fixed_mask] = 0
            disp_y_sum[fixed_mask] = 0
            
            pos_arr[:, 0] += disp_x_sum
            pos_arr[:, 1] += disp_y_sum
            
        # Result
        new_positions = {}
        for i, n in enumerate(nodes):
            new_positions[n] = (float(pos_arr[i, 0]), float(pos_arr[i, 1]))
            
        return new_positions
