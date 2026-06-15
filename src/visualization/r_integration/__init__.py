#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
R Integration Module for TextAnalyzer Pro

This module provides integration with R to generate visualizations
identical to IRaMuTeQ's original output.

Components:
- RBridge: Manages R executable detection and script execution
- DataExchange: Handles data serialization between Python and R
- RVisualizer: High-level API for generating visualizations
"""

from .r_bridge import RBridge
from .data_exchange import DataExchange
from .r_visualizer import RVisualizer

__all__ = ['RBridge', 'DataExchange', 'RVisualizer']
