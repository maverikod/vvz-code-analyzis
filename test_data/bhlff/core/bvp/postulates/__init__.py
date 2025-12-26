"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP postulates package for 7D space-time theory.

This package contains all 9 BVP postulates as separate modules, implementing
the fundamental properties and behavior of the Base High-Frequency Field
in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Physical Meaning:
    Each postulate validates specific aspects of the BVP field behavior,
    ensuring physical consistency and theoretical correctness of the
    7D phase field theory implementation.

Mathematical Foundation:
    The postulates implement mathematical operations to verify:
    - Carrier primacy and frequency structure
    - Scale separation between carrier and envelope
    - BVP rigidity and stability
    - U(1) phase structure and coherence
    - Quench dynamics and memory effects
    - Tail resonatorness and resonance properties
    - Transition zone behavior
    - Core renormalization effects
    - Power balance and energy conservation

Example:
    >>> from bhlff.core.bvp.postulates import BVPPostulates7D
    >>> postulates = BVPPostulates7D(domain_7d, config)
    >>> results = postulates.validate_all_postulates(envelope_7d)
"""

from .carrier_primacy_postulate import BVPPostulate1_CarrierPrimacy
from .scale_separation_postulate import BVPPostulate2_ScaleSeparation
from .bvp_rigidity_postulate import BVPPostulate3_BVPRigidity
from .u1_phase_structure_postulate import BVPPostulate4_U1PhaseStructure
from .quenches_postulate import BVPPostulate5_Quenches
from .tail_resonatorness_postulate import BVPPostulate6_TailResonatorness
from .transition_zone_postulate import BVPPostulate7_TransitionZone
from .core_renormalization_postulate import BVPPostulate8_CoreRenormalization
from .power_balance.power_balance_postulate import (
    PowerBalancePostulate as BVPPostulate9_PowerBalance,
)
from .bvp_postulates_7d import BVPPostulates7D

__all__ = [
    "BVPPostulate1_CarrierPrimacy",
    "BVPPostulate2_ScaleSeparation",
    "BVPPostulate3_BVPRigidity",
    "BVPPostulate4_U1PhaseStructure",
    "BVPPostulate5_Quenches",
    "BVPPostulate6_TailResonatorness",
    "BVPPostulate7_TransitionZone",
    "BVPPostulate8_CoreRenormalization",
    "BVPPostulate9_PowerBalance",
    "BVPPostulates7D",
]
