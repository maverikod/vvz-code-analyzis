"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for streamline analyzer.

This module provides the base StreamlineAnalyzerBase class with common
initialization and setup methods.
"""

import logging
from typing import Any, Dict

from .streamlines_gradient import GradientComputer
from .streamlines_tracer import StreamlineTracer
from .streamlines_topology import TopologyAnalyzer


class StreamlineAnalyzerBase:
    """
    Base class for streamline analyzer.
    
    Physical Meaning:
        Provides base functionality for analyzing phase streamline
        patterns in the 7D phase field theory.
    """
    
    def __init__(self, domain: "Domain", parameters: Dict[str, Any]):
        """
        Initialize streamline analyzer.
        
        Physical Meaning:
            Sets up the streamline analysis system for
            tracing phase gradient flow patterns.
        
        Args:
            domain (Domain): Computational domain
            parameters (Dict): Analysis parameters
        """
        self.domain = domain
        self.parameters = parameters
        self.logger = logging.getLogger(__name__)
        
        # Initialize analysis tools
        self._gradient_computer = GradientComputer(domain)
        self._streamline_tracer = StreamlineTracer(domain, parameters)
        self._topology_analyzer = TopologyAnalyzer(domain)
        
        self.logger.info("Streamline analyzer initialized")

