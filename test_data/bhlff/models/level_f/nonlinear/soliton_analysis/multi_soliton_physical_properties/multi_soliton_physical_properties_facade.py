"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for multi-soliton physical properties.

This module provides the main MultiSolitonPhysicalProperties facade class that
coordinates all multi-soliton physical properties computation components.
"""

from .multi_soliton_physical_properties_base import MultiSolitonPhysicalPropertiesBase
from .multi_soliton_physical_properties_two import MultiSolitonPhysicalPropertiesTwoMixin
from .multi_soliton_physical_properties_three import MultiSolitonPhysicalPropertiesThreeMixin
from .multi_soliton_physical_properties_energy import MultiSolitonPhysicalPropertiesEnergyMixin
from .multi_soliton_physical_properties_7d import MultiSolitonPhysicalProperties7DMixin


class MultiSolitonPhysicalProperties(
    MultiSolitonPhysicalPropertiesBase,
    MultiSolitonPhysicalPropertiesTwoMixin,
    MultiSolitonPhysicalPropertiesThreeMixin,
    MultiSolitonPhysicalPropertiesEnergyMixin,
    MultiSolitonPhysicalProperties7DMixin
):
    """
    Facade class for multi-soliton physical properties with all mixins.
    
    Physical Meaning:
        Implements physical properties computation including energy calculations,
        stability metrics, phase coherence, and 7D BVP specific properties
        for multi-soliton systems.
    """
    pass

