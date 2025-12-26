"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main astrophysical object model for 7D phase field theory.

This module implements the main astrophysical object model that
coordinates different types of astrophysical objects (stars, galaxies,
black holes) and provides a unified interface.

Theoretical Background:
    Astrophysical objects are represented as phase field configurations
    with specific topological properties that give rise to their
    observable characteristics through phase coherence and defects.

Mathematical Foundation:
    Implements phase field profiles for different object types:
    - Stars: a(r) = A₀ T(r) cos(φ(r)) where T is transmission coefficient
    - Galaxies: a(r,θ) = A(r) exp(i(mθ + φ(r)))
    - Black holes: a(r) = A₀ (r/r_s)^(-α) exp(iφ(r))

Example:
    >>> model = AstrophysicalObjectModel('star', stellar_params)
    >>> properties = model.analyze_phase_properties()
"""

import numpy as np
from typing import Dict, Any, Optional
from ...base.model_base import ModelBase
from .stellar_models import StellarModel
from .galactic_models import GalacticModel
from .black_hole_models import BlackHoleModel
from .phase_analysis import PhaseAnalyzer
from .observable_properties import ObservablePropertiesCalculator


class AstrophysicalObjectModel(ModelBase):
    """
    Main model for astrophysical objects in 7D phase field theory.

    Physical Meaning:
        Represents stars, galaxies, and black holes as phase field
        configurations with specific topological properties.

    Mathematical Foundation:
        Implements phase field profiles for different object types:
        - Stars: a(r) = A₀ T(r) cos(φ(r)) where T is transmission coefficient
        - Galaxies: a(r,θ) = A(r) exp(i(mθ + φ(r)))
        - Black holes: a(r) = A₀ (r/r_s)^(-α) exp(iφ(r))

    Attributes:
        object_type (str): Type of astrophysical object
        phase_profile (np.ndarray): Phase field profile
        topological_charge (int): Topological charge
        physical_params (dict): Physical parameters
        specialized_model: Specialized model for the object type
        phase_analyzer: Phase analyzer for the object
        properties_calculator: Observable properties calculator
    """

    def __init__(self, object_type: str, object_params: Dict[str, Any]):
        """
        Initialize astrophysical object model.

        Physical Meaning:
            Creates a model for a specific type of astrophysical object
            with given physical parameters.

        Args:
            object_type: Type of object ('star', 'galaxy', 'black_hole')
            object_params: Physical parameters for the object
        """
        super().__init__()
        self.object_type = object_type
        self.object_params = object_params
        self.phase_profile = None
        self.topological_charge = 0
        self.physical_params = {}

        # Initialize specialized components
        self.phase_analyzer = PhaseAnalyzer()
        self.properties_calculator = ObservablePropertiesCalculator()

        # Setup specialized model
        self._setup_specialized_model()

    def _setup_specialized_model(self) -> None:
        """
        Setup specialized model based on object type.

        Physical Meaning:
            Initializes the specialized model for the specific
            astrophysical object type.

        Raises:
            ValueError: If object type is not supported
        """
        if self.object_type == "star":
            self.specialized_model = StellarModel(self.object_params)
        elif self.object_type == "galaxy":
            self.specialized_model = GalacticModel(self.object_params)
        elif self.object_type == "black_hole":
            self.specialized_model = BlackHoleModel(self.object_params)
        else:
            raise ValueError(f"Unknown object type: {self.object_type}")

        # Copy properties from specialized model
        self.phase_profile = self.specialized_model.phase_profile
        self.topological_charge = self.specialized_model.topological_charge
        self.physical_params = self.specialized_model.physical_params

    def create_star_model(
        self, stellar_params: Dict[str, Any]
    ) -> "AstrophysicalObjectModel":
        """
        Create star model with given parameters.

        Physical Meaning:
            Creates a star model with specified stellar parameters
            and phase field configuration.

        Args:
            stellar_params: Stellar parameters

        Returns:
            Star model instance
        """
        self.object_type = "star"
        self.object_params = stellar_params
        self._setup_specialized_model()
        return self

    def create_galaxy_model(
        self, galactic_params: Dict[str, Any]
    ) -> "AstrophysicalObjectModel":
        """
        Create galaxy model with given parameters.

        Physical Meaning:
            Creates a galaxy model with specified galactic parameters
            and spiral structure.

        Args:
            galactic_params: Galactic parameters

        Returns:
            Galaxy model instance
        """
        self.object_type = "galaxy"
        self.object_params = galactic_params
        self._setup_specialized_model()
        return self

    def create_black_hole_model(
        self, bh_params: Dict[str, Any]
    ) -> "AstrophysicalObjectModel":
        """
        Create black hole model with given parameters.

        Physical Meaning:
            Creates a black hole model with specified parameters
            and extreme phase defect.

        Args:
            bh_params: Black hole parameters

        Returns:
            Black hole model instance
        """
        self.object_type = "black_hole"
        self.object_params = bh_params
        self._setup_specialized_model()
        return self

    def analyze_phase_properties(self) -> Dict[str, Any]:
        """
        Analyze phase properties of the object.

        Physical Meaning:
            Analyzes the phase field properties of the astrophysical
            object, including topological characteristics.

        Returns:
            Phase properties analysis
        """
        if self.phase_profile is None:
            return {}

        # Use phase analyzer to compute properties
        properties = self.phase_analyzer.analyze_phase_properties(self.phase_profile)

        # Add object-specific properties
        properties.update(
            {
                "object_type": self.object_type,
                "topological_charge": self.topological_charge,
            }
        )

        return properties

    def compute_observable_properties(self) -> Dict[str, float]:
        """
        Compute observable properties of the object.

        Physical Meaning:
            Computes observable properties that can be compared
            with astronomical observations.

        Returns:
            Observable properties
        """
        if self.phase_profile is None:
            return {}

        # Use properties calculator to compute observable properties
        properties = self.properties_calculator.compute_observable_properties(
            self.phase_profile, self.physical_params
        )

        return properties

    def get_phase_profile(self) -> Optional[np.ndarray]:
        """
        Get the phase field profile.

        Physical Meaning:
            Returns the phase field profile of the astrophysical object.

        Returns:
            Phase field profile array
        """
        return self.phase_profile

    def get_topological_charge(self) -> int:
        """
        Get the topological charge.

        Physical Meaning:
            Returns the topological charge of the astrophysical object.

        Returns:
            Topological charge
        """
        return self.topological_charge

    def get_physical_params(self) -> Dict[str, Any]:
        """
        Get the physical parameters.

        Physical Meaning:
            Returns the physical parameters of the astrophysical object.

        Returns:
            Physical parameters dictionary
        """
        return self.physical_params

    def update_parameters(self, new_params: Dict[str, Any]) -> None:
        """
        Update object parameters.

        Physical Meaning:
            Updates the physical parameters of the astrophysical object
            and recomputes the phase field profile.

        Args:
            new_params: New parameters to update
        """
        self.object_params.update(new_params)
        self._setup_specialized_model()

    def get_specialized_model(self):
        """
        Get the specialized model.

        Physical Meaning:
            Returns the specialized model for the specific
            astrophysical object type.

        Returns:
            Specialized model instance
        """
        return self.specialized_model
