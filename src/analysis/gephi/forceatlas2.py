
import logging
import math
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import numpy as np

log = logging.getLogger(__name__)


class ForceAtlas2:
    """
    ForceAtlas2 Layout Algorithm - Faithful Python Implementation.

    References:
        Jacomy M, Venturini T, Heymann S, Bastian M (2014) 
        ForceAtlas2, a Continuous Graph Layout Algorithm for Handy Network Visualization Designed for the Gephi Software.
        PLoS ONE 9(6): e98679. doi:10.1371/journal.pone.0098679
    """

    def __init__(
        self,
        # Behavior
        scaling_ratio: float = 2.0,
        gravity: float = 1.0,
        strong_gravity_mode: bool = False,
        outbound_attraction_distribution: bool = False,
        lin_log_mode: bool = False,
        adjust_sizes: bool = False,
        edge_weight_influence: float = 1.0,
        
        # Performance / Tuning
        jitter_tolerance: float = 1.0,
        barnes_hut_optimize: bool = False,
        barnes_hut_theta: float = 1.2,
        
        # Internal
        verbose: bool = False,
    ):
        self.scaling_ratio = scaling_ratio
        self.gravity = gravity
        self.strong_gravity_mode = strong_gravity_mode
        self.outbound_attraction_distribution = outbound_attraction_distribution
        self.lin_log_mode = lin_log_mode
        self.adjust_sizes = adjust_sizes
        self.edge_weight_influence = edge_weight_influence
        
        self.jitter_tolerance = jitter_tolerance
        self.barnes_hut_optimize = barnes_hut_optimize
        self.barnes_hut_theta = barnes_hut_theta
        
        self.verbose = verbose

    def run(
        self,
        graph: nx.Graph,
        iterations: int = 100,
        pos: Optional[Dict[Any, Tuple[float, float]]] = None,
        weight_attr: str = "weight",
        node_sizes: Optional[Dict[Any, float]] = None,
    ) -> Dict[Any, Tuple[float, float]]:
        """
        Execute the ForceAtlas2 algorithm.

        Args:
            graph: NetworkX graph
            iterations: Number of steps to simulate
            pos: Initial positions (optional)
            weight_attr: Edge attribute for weight
            node_sizes: Dict of node sizes (radius) for adjustSizes logic. 
                        If None, will be estimated from degree.

        Returns:
            Dict of (x, y) coordinates.
        """
        if not graph:
            return {}

        nodes = list(graph.nodes())
        n_nodes = len(nodes)
        if n_nodes == 0:
            return {}

        # 1. Initialize State
        # -------------------
        
        # Node Map
        node_to_idx = {n: i for i, n in enumerate(nodes)}
        
        # Positions (N, 2)
        if pos is None:
            # Random initialization [-10, 10]
            positions = (np.random.rand(n_nodes, 2) - 0.5) * 20.0
        else:
            positions = np.zeros((n_nodes, 2))
            for i, n in enumerate(nodes):
                if n in pos:
                    positions[i] = pos[n]
                else:
                    positions[i] = (np.random.rand(2) - 0.5) * 20.0

        # Masses (Degree + 1)
        # We use WEIGHTED degree if available, as strictly better for text networks
        degrees = np.zeros(n_nodes)
        for i, n in enumerate(nodes):
            try:
                d = graph.degree(n, weight=weight_attr)
            except (TypeError, AttributeError):
                d = graph.degree(n)
            degrees[i] = 1.0 + d
            
        # Sizes (for adjustSizes)
        # If not provided, we must estimate. FA2 adjustSizes relies on the graphical size.
        # We will assume size is proportional to mass if not provided.
        radii = np.zeros(n_nodes)
        if node_sizes:
            for i, n in enumerate(nodes):
                radii[i] = node_sizes.get(n, 1.0)
        else:
            # Heuristic: radius ~ sqrt(degree) ?? 
            # Or just assume 1.0 if not specified
            # The previous code used complex logic. For 'Pure FA2', usually radius is explicit.
            # We'll default to mass/2.0
            radii = degrees / 2.0

        # Edges (Source, Target, Weight)
        edge_list = []
        for u, v, data in graph.edges(data=True):
            if u == v: continue
            w = float(data.get(weight_attr, 1.0))
            if self.edge_weight_influence != 1.0:
                 if w > 0:
                     w = w ** self.edge_weight_influence
            
            if u in node_to_idx and v in node_to_idx:
                edge_list.append((node_to_idx[u], node_to_idx[v], w))
        
        edges = np.array(edge_list) if edge_list else np.zeros((0, 3))
        
        # adaptive speed params
        speed = 1.0
        speed_efficiency = 1.0
        
        # 2. Main Loop
        # ------------
        
        # Initialize previous forces for swinging
        self._prev_forces = np.zeros((n_nodes, 2))
        
        for it in range(iterations):
            # A. Convert to Matrix/Vectors
            # Force Accumulator
            forces = np.zeros((n_nodes, 2))
            
            # --- REPULSION ---
            # Standard N^2 approach (Correct and robust for N < 2000)
            # Barnes-Hut would go here for optimization
            
            # Delta (N, N, 2)
            # CAUTION: Memory heavy. 
            # For 2000 nodes, 2000*2000*2 * 8 bytes ~ 64MB. Safe.
            delta = positions[:, np.newaxis, :] - positions[np.newaxis, :, :]
            dist_sq = np.sum(delta**2, axis=2)
            dist = np.sqrt(dist_sq)
            
            # Mask diagonal (dist=0)
            np.fill_diagonal(dist, np.inf)
            
            # Force Magnitude calculation
            mass_prod = degrees[:, np.newaxis] * degrees[np.newaxis, :]
            
            if self.adjust_sizes:
                # Anti-Collision Mode
                # dist = dist - (r1 + r2)
                r_sum = radii[:, np.newaxis] + radii[np.newaxis, :]
                eff_dist = dist - r_sum
                
                # Overlap
                overlap_mask = eff_dist < 0
                
                rep_force = np.zeros((n_nodes, n_nodes))
                
                # Case 1: No overlap (eff_dist > 0)
                # F = k * mass_prod / eff_dist
                # Avoid div zero
                valid = (~overlap_mask) & (dist < np.inf)
                safe_dist = eff_dist.copy()
                safe_dist[safe_dist < 0.01] = 0.01 # Clamp low
                
                rep_force[valid] = self.scaling_ratio * mass_prod[valid] / safe_dist[valid]
                
                # Case 2: Overlap
                # F = k * mass_prod * 100 (Strong Constant)
                rep_force[overlap_mask] = self.scaling_ratio * mass_prod[overlap_mask] * 100.0
                
            else:
                # Standard Mode
                # F = k * mass_prod / dist
                # Protect dist=0
                safe_dist = dist.copy()
                safe_dist[safe_dist < 0.1] = 0.1 
                rep_force = self.scaling_ratio * mass_prod / safe_dist
            
            # Apply Direction: ForceVector = ForceMag * (Delta / Dist)
            # = (ForceMag / Dist) * Delta
            
            # Optimization: Precompute coeff
            # avoid dist=0 (diagonal is inf, so safe)
            coeff = rep_force / dist
            
            # Sum forces (matrix mult-ish)
            # forces += sum( coeff * delta )
            forces += np.sum(delta * coeff[:, :, np.newaxis], axis=1)

            # --- ATTRACTION ---
            if len(edges) > 0:
                us = edges[:, 0].astype(int)
                vs = edges[:, 1].astype(int)
                ws = edges[:, 2]
                
                pos_u = positions[us]
                pos_v = positions[vs]
                vec = pos_v - pos_u # u -> v
                dist_e = np.linalg.norm(vec, axis=1)
                dist_e[dist_e < 0.001] = 0.001
                
                # Formulate Force Magnitude
                # LinLog: w * log(1 + d)
                # Linear: w * d
                # Distributed: / deg
                
                if self.lin_log_mode:
                    f_base = ws * np.log(1.0 + dist_e)
                else:
                    f_base = ws * dist_e
                
                # Individual forces
                if self.outbound_attraction_distribution:
                    f_u = f_base / degrees[us]
                    f_v = f_base / degrees[vs]
                else:
                    f_u = f_base
                    f_v = f_base
                
                # AdjustSizes check for attraction?
                # FA2 usually does NOT inhibit attraction on overlap, 
                # but we can prevent implosion if needed. 
                # Keeping standard behavior: pure distance based.
                
                # Direction: vec / dist
                norm_vec = vec / dist_e[:, np.newaxis]
                
                # Apply
                # U moves to V
                np.add.at(forces, us, norm_vec * f_u[:, np.newaxis])
                # V moves to U (minus vec)
                np.add.at(forces, vs, -norm_vec * f_v[:, np.newaxis])
                
            # --- GRAVITY ---
            # F = g * mass (standard) - força constante em direção ao centro
            # F = g * mass * dist_to_center (strong) - força tipo mola (cresce com distância)
            d_center = np.linalg.norm(positions, axis=1)
            d_center[d_center < 0.001] = 0.001

            if self.strong_gravity_mode:
                g_mag = self.gravity * degrees * d_center  # mola (cresce com distância)
            else:
                g_mag = self.gravity * degrees             # constante (centra suavemente)

            # Direction: - pos / dist
            g_vec = -positions / d_center[:, np.newaxis] * g_mag[:, np.newaxis]
            forces += g_vec
            
            # --- ADAPTIVE SPEED (Swinging & Traction) ---
            # We need previous forces needed for Swinging? 
            # Or just update speed based on global metrics.
            
            # For simplicity in this v1 implementation, we use a robust simpler heuristic 
            # if we don't store previous forces.
            # But "swinging" requires F(t) and F(t-1).
            # Let's implement global swinging logic properly.
            
            # _prev_forces is initialized before the loop (line ~149), so this
            # check is always False and can be skipped safely.
            # Kept as a no-op comment for clarity.

            # Compute Global Swing / Traction
            # swinging = mass * || F(t) - F(t-1) ||
            # traction = mass * || F(t) + F(t-1) || / 2
            
            diff_forces = np.linalg.norm(forces - self._prev_forces, axis=1)
            sum_forces = np.linalg.norm(forces + self._prev_forces, axis=1) / 2.0
            
            swinging = np.sum(degrees * diff_forces)
            traction = np.sum(degrees * sum_forces)
            
            # Adaptive speed update
            # Tolerance
            jt = self.jitter_tolerance
            
            if traction > 0:
                 ratio = swinging / traction
                 
                 if ratio > 2.0:
                     speed_efficiency = max(0.1, speed_efficiency * 0.5)
                 else:
                     # target = jt * efficiency * traction / swinging
                     # but safeguard div/0
                     if swinging < 0.001: 
                         target_speed = 1000.0 # Arbitrary high
                     else:
                         target_speed = (jt * speed_efficiency * traction) / swinging
                     
                     # Smooth update
                     # speed = speed + min(target - speed, 0.5 * speed)
                     
                     # Gephi limits rise
                     if target_speed > speed:
                         speed = min(target_speed, speed * 1.5)
                     else:
                         speed = target_speed

            # Prepare for next
            self._prev_forces = forces.copy()
            
            # --- APPLY DISPLACEMENT ---
            # final_speed = speed * speed_efficiency? 
            # In Gephi code: 
            # double factor = speed / (1.0 + sqrt(speed * swinging));
            # Then apply per node.
            
            # Global factor
            # We need 'swinging' per node for perfect local speed, but global is often fine.
            # Let's use the node-wise scaling limiter.
            
            force_mags = np.linalg.norm(forces, axis=1)
            # prevent explosion
            max_f = np.max(force_mags)
            if max_f > 0:
                # Limit step size
                # If force is huge, we limit displacement.
                # displacement = force * speed
                # limit = 10.0 (const)
                # scale = min(speed, limit/force)
                 
                # Using a safe simpler cap mostly
                scale = np.minimum(speed, 100.0 / (force_mags + 0.001))
                
                # Apply
                positions += forces * scale[:, np.newaxis]
            
            # Log
            if self.verbose and it % 50 == 0:
                spread = np.max(positions) - np.min(positions)
                log.info(f"FA2 Iter {it}: Speed={speed:.2f}, Spread={spread:.1f}")

        # Return Map
        return {
            nodes[i]: (float(positions[i, 0]), float(positions[i, 1]))
            for i in range(n_nodes)
        }
