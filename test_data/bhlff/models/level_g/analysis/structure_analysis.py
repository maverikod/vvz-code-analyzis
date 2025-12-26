"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Structure formation analysis for cosmological analysis in 7D phase field theory.

This module implements structure formation analysis methods for
cosmological evolution results, including structure evolution,
formation timescales, and growth rate analysis.

Theoretical Background:
    Structure formation analysis in cosmological evolution
    involves analyzing how structure evolves over cosmological time,
    including growth rates and characteristic scales.

Mathematical Foundation:
    Implements structure formation analysis methods:
    - Growth rate: based on RMS evolution
    - Characteristic timescale: based on structure evolution
    - Formation timescales: various timescales for structure formation

Example:
    >>> analysis = StructureAnalysis(evolution_results)
    >>> structure_evolution = analysis.analyze_structure_evolution()
"""

import numpy as np
from typing import Dict, Any, List, Optional


class StructureAnalysis:
    """
    Structure formation analysis for cosmological analysis.

    Physical Meaning:
        Implements structure formation analysis methods for
        cosmological evolution results, including structure
        evolution, formation timescales, and growth rate analysis.

    Mathematical Foundation:
        Implements structure formation analysis methods:
        - Growth rate: based on RMS evolution
        - Characteristic timescale: based on structure evolution
        - Formation timescales: various timescales for structure formation

    Attributes:
        evolution_results (dict): Cosmological evolution results
        analysis_parameters (dict): Analysis parameters
    """

    def __init__(
        self,
        evolution_results: Dict[str, Any],
        analysis_parameters: Dict[str, Any] = None,
    ):
        """
        Initialize structure analysis.

        Physical Meaning:
            Sets up the structure analysis with evolution results
            and analysis parameters.

        Args:
            evolution_results: Cosmological evolution results
            analysis_parameters: Analysis parameters
        """
        self.evolution_results = evolution_results
        self.analysis_parameters = analysis_parameters or {}

        # Analysis parameters
        self.correlation_threshold = self.analysis_parameters.get(
            "correlation_threshold", 0.1
        )
        self.significance_level = self.analysis_parameters.get(
            "significance_level", 0.05
        )
        self.structure_threshold = self.analysis_parameters.get(
            "structure_threshold", 0.5
        )

    def analyze_structure_formation(self) -> Dict[str, Any]:
        """
        Analyze structure formation process.

        Physical Meaning:
            Analyzes the process of structure formation from
            phase field evolution and gravitational effects.

        Returns:
            Structure formation analysis
        """
        if not self.evolution_results:
            return {}

        # Analyze structure formation
        analysis = {
            "structure_evolution": self._analyze_structure_evolution(),
            "formation_timescales": self._compute_formation_timescales(),
            "structure_statistics": self._compute_structure_statistics(),
            "correlation_analysis": self._analyze_correlations(),
        }

        return analysis

    def _analyze_structure_evolution(self) -> Dict[str, Any]:
        """
        Analyze structure evolution over time.

        Physical Meaning:
            Analyzes how structure evolves over cosmological time,
            including growth rates and characteristic scales.

        Returns:
            Structure evolution analysis
        """
        structure_formation = self.evolution_results.get("structure_formation", [])
        if len(structure_formation) == 0:
            return {}

        # Extract evolution metrics
        time_evolution = [structure["time"] for structure in structure_formation]
        rms_evolution = [
            structure.get("phase_field_rms", 0.0) for structure in structure_formation
        ]
        max_evolution = [
            structure.get("phase_field_max", 0.0) for structure in structure_formation
        ]
        correlation_evolution = [
            structure.get("correlation_length", 0.0)
            for structure in structure_formation
        ]

        # Compute evolution metrics
        evolution_analysis = {
            "time_evolution": time_evolution,
            "rms_evolution": rms_evolution,
            "max_evolution": max_evolution,
            "correlation_evolution": correlation_evolution,
            "growth_rate": self._compute_growth_rate(rms_evolution),
            "characteristic_timescale": self._compute_characteristic_timescale(
                rms_evolution
            ),
        }

        return evolution_analysis

    def _compute_growth_rate(self, rms_evolution: List[float]) -> float:
        """
        Compute structure growth rate.

        Physical Meaning:
            Computes the rate at which structure grows during
            cosmological evolution.

        Args:
            rms_evolution: RMS evolution over time

        Returns:
            Growth rate
        """
        if len(rms_evolution) < 2:
            return 0.0

        # Compute growth rate
        initial_rms = rms_evolution[0]
        final_rms = rms_evolution[-1]

        if initial_rms > 0:
            growth_rate = (final_rms - initial_rms) / len(rms_evolution)
        else:
            growth_rate = 0.0

        return float(growth_rate)

    def _compute_characteristic_timescale(self, rms_evolution: List[float]) -> float:
        """
        Compute characteristic timescale.

        Physical Meaning:
            Computes the characteristic timescale for structure
            formation from the evolution data.

        Args:
            rms_evolution: RMS evolution over time

        Returns:
            Characteristic timescale
        """
        if len(rms_evolution) < 2:
            return 0.0

        # Find timescale where structure reaches half of final value
        final_rms = rms_evolution[-1]
        half_rms = final_rms / 2.0

        # Find index where structure reaches half value
        for i, rms in enumerate(rms_evolution):
            if rms >= half_rms:
                return float(i)

        return float(len(rms_evolution))

    def _compute_formation_timescales(self) -> Dict[str, float]:
        """
        Compute formation timescales.

        Physical Meaning:
            Computes various timescales for structure formation,
            including characteristic formation times.

        Returns:
            Formation timescales
        """
        structure_formation = self.evolution_results.get("structure_formation", [])
        if len(structure_formation) == 0:
            return {}

        # Compute timescales
        timescales = {
            "total_formation_time": structure_formation[-1]["time"]
            - structure_formation[0]["time"],
            "initial_growth_time": self._compute_initial_growth_time(
                structure_formation
            ),
            "maturation_time": self._compute_maturation_time(structure_formation),
            "equilibrium_time": self._compute_equilibrium_time(structure_formation),
        }

        return timescales

    def _compute_initial_growth_time(
        self, structure_formation: List[Dict[str, Any]]
    ) -> float:
        """
        Compute initial growth time.

        Physical Meaning:
            Computes the time for initial structure growth
            from the formation data.

        Args:
            structure_formation: Structure formation data

        Returns:
            Initial growth time
        """
        if len(structure_formation) < 2:
            return 0.0

        # Find time when structure starts growing significantly
        initial_rms = structure_formation[0].get("phase_field_rms", 0.0)
        threshold = initial_rms * 1.1  # 10% growth threshold

        for structure in structure_formation:
            if structure.get("phase_field_rms", 0.0) > threshold:
                return float(structure["time"])

        return float(structure_formation[-1]["time"])

    def _compute_maturation_time(
        self, structure_formation: List[Dict[str, Any]]
    ) -> float:
        """
        Compute maturation time.

        Physical Meaning:
            Computes the time for structure maturation
            from the formation data.

        Args:
            structure_formation: Structure formation data

        Returns:
            Maturation time
        """
        if len(structure_formation) < 2:
            return 0.0

        # Find time when structure reaches 90% of final value
        final_rms = structure_formation[-1].get("phase_field_rms", 0.0)
        threshold = final_rms * 0.9

        for structure in structure_formation:
            if structure.get("phase_field_rms", 0.0) >= threshold:
                return float(structure["time"])

        return float(structure_formation[-1]["time"])

    def _compute_equilibrium_time(
        self, structure_formation: List[Dict[str, Any]]
    ) -> float:
        """
        Compute equilibrium time.

        Physical Meaning:
            Computes the time when structure reaches equilibrium
            from the formation data.

        Args:
            structure_formation: Structure formation data

        Returns:
            Equilibrium time
        """
        if len(structure_formation) < 3:
            return 0.0

        # Find time when structure growth rate becomes small
        rms_values = [
            structure.get("phase_field_rms", 0.0) for structure in structure_formation
        ]
        growth_rates = np.diff(rms_values)

        # Find when growth rate becomes small
        for i, rate in enumerate(growth_rates):
            if abs(rate) < 0.01:  # Small growth rate threshold
                return float(structure_formation[i]["time"])

        return float(structure_formation[-1]["time"])
