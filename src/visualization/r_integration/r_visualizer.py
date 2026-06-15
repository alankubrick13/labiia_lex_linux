#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
R Visualizer - High-level API for R-based visualizations

This module provides a unified interface for generating IRaMuTeQ-style
visualizations using R scripts.
"""

import os
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path

from .r_bridge import RBridge, REQUIRED_PACKAGES, OPTIONAL_PACKAGES
from .data_exchange import DataExchange
from ...utils.logger import get_logger

logger = get_logger('r_visualizer')


class RVisualizer:
    """
    High-level API for generating IRaMuTeQ-style visualizations with R.

    Provides methods for:
    - AFC (Correspondence Analysis) plots
    - CHD (Hierarchical Classification) dendrograms
    - Similarity graphs

    Falls back to Python implementations if R is not available.
    """

    def __init__(self, temp_dir: Optional[str] = None):
        """
        Initialize RVisualizer.

        Args:
            temp_dir: Directory for temporary files
        """
        self.bridge = RBridge()
        self.exchange = DataExchange(temp_dir)
        self._packages_checked = False
        self._packages_ok = False

    @property
    def r_available(self) -> bool:
        """Check if R is available and packages are installed."""
        logger.debug(f">>> r_available property called <<<")
        logger.debug(f"  bridge.r_available: {self.bridge.r_available}")
        logger.debug(f"  _packages_checked: {self._packages_checked}")
        logger.debug(f"  _packages_ok: {self._packages_ok}")

        if not self.bridge.r_available:
            logger.warning(">>> bridge.r_available is False - R executable not found <<<")
            return False

        if not self._packages_checked:
            logger.info(">>> Checking R packages for first time <<<")
            self._check_packages()

        logger.debug(f">>> r_available returning: {self._packages_ok} <<<")
        return self._packages_ok

    def _check_packages(self):
        """Check if required R packages are installed."""
        logger.info(f"Checking packages: {REQUIRED_PACKAGES}")
        status = self.bridge.check_packages(REQUIRED_PACKAGES)
        optional_status = self.bridge.check_packages(OPTIONAL_PACKAGES)
        logger.info(f"Package check result: {status}")
        if optional_status:
            logger.info(f"Optional package status: {optional_status}")
        self._packages_checked = True
        self._packages_ok = all(status.values())
        logger.info(f"All packages OK: {self._packages_ok}")

        if not self._packages_ok:
            missing = [p for p, ok in status.items() if not ok]
            logger.warning(f">>> MISSING R PACKAGES: {missing} <<<")
        else:
            logger.info(">>> ALL R PACKAGES INSTALLED <<<")

    def install_packages(self) -> bool:
        """Install missing R packages."""
        success = self.bridge.install_packages()
        if success:
            self._packages_checked = False
            return self.r_available
        return False

    def get_status(self) -> Dict[str, Any]:
        """Get R integration status."""
        return {
            'r_available': self.bridge.r_available,
            'r_executable': self.bridge.r_executable,
            'r_version': self.bridge.get_r_version(),
            'packages_ok': self._packages_ok if self._packages_checked else None,
            'packages_status': self.bridge.check_packages() if self.bridge.r_available else {},
            'optional_packages_status': self.bridge.check_packages(OPTIONAL_PACKAGES) if self.bridge.r_available else {},
        }

    # =========================================================================
    # AFC Plot
    # =========================================================================

    def create_afc_plot(self, afc_result: Dict[str, Any], chd_result=None,
                        width: int = 900, height: int = 900,
                        axes: Tuple[int, int] = (1, 2),
                        max_words: int = 120,
                        nb_per_class: int = 80,
                        what: str = "coord",
                        col: bool = False,
                        debsup: Optional[int] = None,
                        gexf_output: Optional[str] = None,
                        show_class_labels: bool = False) -> bytes:
        """
        Create AFC (Correspondence Analysis) plot using R.

        Args:
            afc_result: AFC analysis result dictionary
            chd_result: Optional CHD result for class coloring
            width: Image width in pixels
            height: Image height in pixels
            axes: Which axes to plot (1-indexed)
            max_words: Maximum words to display
            nb_per_class: Words per class for chi-square selection (IRaMuTeQ default: 80)
            what: AFC coordinate mode ('coord' or 'crl')
            col: Plot column coordinates when True
            debsup: Index where supplementary forms begin
            gexf_output: Optional output path for GEXF export
            show_class_labels: Draw class labels in plot corners

        Returns:
            PNG image bytes, or empty bytes on error
        """
        logger.info(">>> RVisualizer.create_afc_plot() called <<<")
        logger.info(f"  r_available: {self.r_available}")

        if not self.r_available:
            logger.error(">>> R NOT AVAILABLE - returning empty bytes <<<")
            return b''

        try:
            # Export data for R
            logger.info("Exporting AFC data...")
            files = self.exchange.export_afc_data(afc_result, chd_result)
            logger.info(f"Exported files: {list(files.keys())}")

            if 'coords_file' not in files:
                logger.error("No coordinates data for AFC plot")
                return b''

            # Prepare output file
            output_file = self.exchange.get_temp_output_path('afc', 'png')

            # Get inertia values
            inertia = list(afc_result.get('explained_inertia', []))

            resolved_debsup = debsup
            if resolved_debsup in (None, "", 0):
                candidates: List[Any] = [
                    files.get('debsup'),
                    afc_result.get('debsup'),
                    afc_result.get('n_active_forms'),
                ]
                if chd_result is not None:
                    candidates.extend([
                        getattr(chd_result, 'debsup', None),
                        getattr(chd_result, 'n_active_forms', None),
                    ])
                for value in candidates:
                    try:
                        parsed = int(value)
                    except (TypeError, ValueError):
                        continue
                    if parsed > 1:
                        resolved_debsup = parsed
                        break

            # Prepare arguments for R script
            args = {
                'coords_file': files['coords_file'],
                'chi2_file': files.get('chi2_file'),
                'col_coords_file': files.get('col_coords_file'),
                'output_file': output_file,
                'width': width,
                'height': height,
                'axes': list(axes),
                'max_words': max_words,
                'nbbycl': nb_per_class,
                'inertia': inertia,
                'what': what,
                'col': bool(col),
                'debsup': resolved_debsup,
                'gexf_output': gexf_output,
                'show_class_labels': bool(show_class_labels),
            }

            # Execute R script
            success, stdout, output_bytes = self.bridge.execute_script(
                'afc_plot.R', args, timeout=120
            )

            if success and output_bytes:
                logger.info("AFC plot created successfully with R")
                return output_bytes
            elif success:
                # Try reading from output file
                output_bytes = self.exchange.read_output_image(output_file)
                if output_bytes:
                    return output_bytes

            logger.error(f"AFC plot failed: {stdout}")
            return b''

        except Exception as e:
            logger.error(f"Error creating AFC plot: {e}")
            return b''

    # =========================================================================
    # CHD Dendrogram
    # =========================================================================

    def create_dendrogram(self, chd_result, width: int = 1400,
                          height: int = 1200, max_words: int = 60,
                          type_dendro: str = 'phylogram',
                          dendro_type: str = "profile",
                          bw: bool = False,
                          lab: Optional[List[str]] = None,
                          direction: str = "downwards") -> bytes:
        """
        Create CHD dendrogram using R.

        Args:
            chd_result: CHD analysis result
            width: Image width in pixels
            height: Image height in pixels
            max_words: Maximum words per class
            type_dendro: Dendrogram type ('phylogram' or 'cladogram')
            dendro_type: Variant ('profile', 'cloud', 'pie', 'barplot')
            bw: Black and white mode
            lab: Optional labels for class tips
            direction: Tree direction ('downwards' or 'rightwards')

        Returns:
            PNG image bytes, or empty bytes on error
        """
        if not self.r_available:
            logger.error("R not available for dendrogram")
            return b''

        try:
            # Export data for R
            files = self.exchange.export_chd_data(chd_result)

            if 'tree_file' not in files:
                logger.error("No tree data for dendrogram")
                return b''

            # Prepare output file
            output_file = self.exchange.get_temp_output_path('dendro', 'png')

            # Prepare arguments for R script
            args = {
                'tree_file': files['tree_file'],
                'classes_file': files['classes_file'],
                'words_file': files.get('words_file'),
                'output_file': output_file,
                'width': width,
                'height': height,
                'nbbycl': max_words,
                'type_dendro': type_dendro,
                'dendro_type': dendro_type,
                'bw': bool(bw),
                'lab': lab,
                'direction': direction,
            }

            # Execute R script
            success, stdout, output_bytes = self.bridge.execute_script(
                'dendrogram.R', args, timeout=120
            )

            if success and output_bytes:
                logger.info("Dendrogram created successfully with R")
                return output_bytes
            elif success:
                output_bytes = self.exchange.read_output_image(output_file)
                if output_bytes:
                    return output_bytes

            logger.error(f"Dendrogram failed: {stdout}")
            return b''

        except Exception as e:
            logger.error(f"Error creating dendrogram: {e}")
            return b''

    # =========================================================================
    # Similarity Graph
    # =========================================================================

    def create_similarity_graph(self, sim_result: Dict[str, Any],
                                 width: int = 1000, height: int = 1000,
                                 method: str = 'cooc', max_tree: bool = True,
                                 layout: str = 'frutch',
                                 plot_type: str = 'text',
                                 show_halos: bool = False,
                                 grayscale: bool = False,
                                 min_edge: float = 0.0,
                                 vertex_size_range: Tuple[float, float] = (2.0, 20.0),
                                 show_edge_labels: bool = False,
                                 detect_communities: bool = False,
                                 community_method: Any = 4,
                                 cexalpha: bool = False,
                                 graph_word: Optional[str] = None,
                                 gexf_output: Optional[str] = None) -> bytes:
        """
        Create similarity graph using R.

        Args:
            sim_result: Similarity analysis result
            width: Image width in pixels
            height: Image height in pixels
            method: Similarity method ('cooc', 'jaccard')
            max_tree: Use maximum spanning tree
            layout: Layout algorithm ('frutch' or 'kawa')
            plot_type: Plot type ('graph' or 'text')
            show_halos: Whether to show colored community halos/backgrounds
            min_edge: Edge threshold (seuil)
            vertex_size_range: Min/max vertex size range
            show_edge_labels: Show edge weights as labels
            detect_communities: Enable community detection
            community_method: Method id/name
            cexalpha: Alpha scale labels by cex
            graph_word: Optional center word for one-word subgraph
            gexf_output: Optional GEXF export path

        Returns:
            PNG image bytes, or empty bytes on error
        """
        if not self.r_available:
            logger.error("R not available for similarity graph")
            return b''

        try:
            # Export data for R
            files = self.exchange.export_similarity_data(sim_result)

            if 'matrix_file' not in files:
                logger.error("No matrix data for similarity graph")
                return b''

            # Prepare output file
            output_file = self.exchange.get_temp_output_path('simi', 'png')

            # Prepare arguments for R script
            args = {
                'matrix_file': files['matrix_file'],
                'freq_file': files.get('freq_file'),
                'output_file': output_file,
                'width': width,
                'height': height,
                'method': method,
                'max_tree': max_tree,
                'layout': layout,
                'vcexmin': 1.0,
                'vcexmax': 2.5,
                'seuil': min_edge,
                'min_edge': min_edge,
                'minmaxeff': [float(vertex_size_range[0]), float(vertex_size_range[1])],
                'edge_label': bool(show_edge_labels),
                'show_edge_labels': bool(show_edge_labels),
                'detect_communities': bool(detect_communities),
                'community_method': community_method,
                'communities': community_method if detect_communities else None,
                'halos': show_halos,
                'show_halo': show_halos,
                'grayscale': grayscale,  # Pass grayscale to R
                'cexalpha': bool(cexalpha),
                'graph_word': graph_word,
                'communities_out': str(self.exchange.temp_dir / 'similarity_communities.csv'),
                'centrality_out': str(self.exchange.temp_dir / 'similarity_centrality.csv'),
                'gexf_output': gexf_output,
            }

            # Execute R script
            success, stdout, output_bytes = self.bridge.execute_script(
                'similarity.R', args, timeout=120
            )

            if success and output_bytes:
                logger.info("Similarity graph created successfully with R")
                return output_bytes
            elif success:
                output_bytes = self.exchange.read_output_image(output_file)
                if output_bytes:
                    return output_bytes

            logger.error(f"Similarity graph failed: {stdout}")
            return b''

        except Exception as e:
            logger.error(f"Error creating similarity graph: {e}")
            return b''

    # =========================================================================
    # Specificities Plot
    # =========================================================================

    def create_specificities_plot(self, spec_file: str, output_file: Optional[str] = None,
                                  width: int = 1200, height: int = 800,
                                  top_n: int = 30, bw: bool = False) -> bytes:
        """
        Create specificities plot (IRaMuTeQ-like plot.spec) using R.

        Args:
            spec_file: CSV file with class_id, word and score column
            output_file: Optional output path
            width: Image width
            height: Image height
            top_n: Top terms per class
            bw: Black/white mode
        """
        if not self.r_available:
            logger.error("R not available for specificities plot")
            return b''

        out_file = output_file or self.exchange.get_temp_output_path('specificities', 'png')
        args = {
            'spec_file': spec_file,
            'output_file': out_file,
            'width': width,
            'height': height,
            'top_n': top_n,
            'bw': bool(bw),
        }
        try:
            success, stdout, output_bytes = self.bridge.execute_script(
                'specificities.R', args, timeout=120
            )
            if success and output_bytes:
                return output_bytes
            if success:
                output_bytes = self.exchange.read_output_image(out_file)
                if output_bytes:
                    return output_bytes
            logger.error(f"Specificities plot failed: {stdout}")
            return b''
        except Exception as e:
            logger.error(f"Error creating specificities plot: {e}")
            return b''

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def cleanup(self):
        """Clean up temporary files."""
        self.exchange.cleanup()

    def __del__(self):
        """Destructor - cleanup on deletion."""
        try:
            self.cleanup()
        except:
            pass
