"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Substrate generation methods for BVP source generators.

This module provides substrate generation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except Exception:
    CUDA_AVAILABLE = False
    cp = None

from ..block_7d_expansion import (
    expand_spatial_to_7d,
    generate_7d_block_on_device,
)


class BVPSourceGeneratorsSubstrateMixin:
    """Mixin providing substrate generation methods."""
    
    def generate_topological_substrate(
        self, defect_config: Dict[str, Any]
    ) -> np.ndarray:
        """
        Generate topological substrate with defects and resonator walls.
        
        Physical Meaning:
            Creates the fundamental 7D BVP substrate based on topological defects
            that form semi-transparent resonator walls.
        """
        # Get defect parameters
        defect_type = defect_config.get("defect_type", "line")
        defect_density = defect_config.get("defect_density", 0.1)
        core_radius = defect_config.get("core_radius", 0.05)
        wall_thickness = defect_config.get("wall_thickness", 0.02)
        transparency = defect_config.get("transparency", 0.3)
        regularization = defect_config.get("regularization", 0.01)

        # Create 7D coordinate arrays
        shape = (
            self.domain.N,
            self.domain.N,
            self.domain.N,
            self.domain.N_phi,
            self.domain.N_phi,
            self.domain.N_phi,
            self.domain.N_t,
        )

        xp = cp if self.use_cuda else np
        # Initialize substrate with base transparency
        substrate = xp.full(shape, transparency, dtype=xp.float64)

        # Generate defects based on type
        if defect_type == "line":
            substrate = self._add_line_defects(
                substrate, defect_density, core_radius, wall_thickness
            )
        elif defect_type == "surface":
            substrate = self._add_surface_defects(
                substrate, defect_density, core_radius, wall_thickness
            )
        elif defect_type == "junction":
            substrate = self._add_junction_defects(
                substrate, defect_density, core_radius, wall_thickness
            )
        elif defect_type == "dislocation":
            substrate = self._add_dislocation_defects(
                substrate, defect_density, core_radius, wall_thickness
            )

        # Apply regularization to smooth walls
        if regularization > 0:
            # Regularize on CPU for now to avoid complex GPU pipeline
            substrate_np = cp.asnumpy(substrate) if self.use_cuda else substrate
            substrate_np = self._regularize_walls(substrate_np, regularization)
            substrate = cp.asarray(substrate_np) if self.use_cuda else substrate_np

        if self.use_cuda:
            return cp.asnumpy(substrate)
        return substrate
    
    def compose_multiscale_substrate(
        self, base_substrate: np.ndarray, layer_config: Dict[str, Any]
    ) -> np.ndarray:
        """
        Compose multiscale substrate with discrete layers and geometric decay.
        
        Physical Meaning:
            Creates discrete layers with quantized radii R_n and geometric decay
            of transparency q between layers.
        """
        num_layers = layer_config.get("num_layers", 4)
        base_radius = layer_config.get("base_radius", 0.1)
        wave_number = layer_config.get("wave_number", 2.0)
        decay_factor = layer_config.get("decay_factor", 0.7)
        center = layer_config.get("center", [0.5, 0.5, 0.5])

        xp = cp if self.use_cuda else np
        # Create coordinate arrays
        x = xp.linspace(0, 1, self.domain.N)
        y = xp.linspace(0, 1, self.domain.N)
        z = xp.linspace(0, 1, self.domain.N)

        X, Y, Z = xp.meshgrid(x, y, z, indexing="ij")

        # Compute distances from center
        dx = X - center[0]
        dy = Y - center[1]
        dz = Z - center[2]
        r = np.sqrt(dx**2 + dy**2 + dz**2)

        # Create discrete layers with geometric decay
        multiscale_substrate = (
            cp.asarray(base_substrate)
            if (self.use_cuda and not isinstance(base_substrate, cp.ndarray))
            else base_substrate
        ).copy()

        for n in range(1, num_layers + 1):
            # Quantized radius
            R_n = base_radius + (np.pi * n) / wave_number

            # Geometric decay of transparency
            T_n = decay_factor**n

            # Create layer wall (semi-transparent barrier)
            wall_mask = self._create_layer_wall(
                r, R_n, 0.02, xp=xp
            )  # 0.02 wall thickness
            
            # Explicit 7D expansion: expand 3D wall_mask to 7D with concrete phase/time extents
            # Uses block processing and CUDA if available (80% GPU memory limit)
            if self.use_cuda and CUDA_AVAILABLE:
                # Move to GPU if needed
                if isinstance(wall_mask, np.ndarray):
                    wall_mask_gpu = cp.asarray(wall_mask)
                else:
                    wall_mask_gpu = wall_mask
                
                # Generate 7D block directly on GPU with explicit construction
                wall_mask_7d = generate_7d_block_on_device(
                    cp.asnumpy(wall_mask_gpu) if isinstance(wall_mask_gpu, cp.ndarray) else wall_mask,
                    N_phi=self.domain.N_phi,
                    N_t=self.domain.N_t,
                    domain=self.domain,
                    use_cuda=True,
                )
            else:
                # CPU: explicit 7D expansion with block processing support
                wall_mask_7d = expand_spatial_to_7d(
                    wall_mask if isinstance(wall_mask, np.ndarray) else cp.asnumpy(wall_mask),
                    N_phi=self.domain.N_phi,
                    N_t=self.domain.N_t,
                    use_cuda=False,
                    optimize_block_size=True,
                )
            
            # Apply wall mask with explicit 7D structure (vectorized operation)
            if self.use_cuda and CUDA_AVAILABLE:
                if isinstance(wall_mask_7d, np.ndarray):
                    wall_mask_7d = cp.asarray(wall_mask_7d)
                if isinstance(multiscale_substrate, np.ndarray):
                    multiscale_substrate = cp.asarray(multiscale_substrate)
                multiscale_substrate = cp.where(wall_mask_7d, T_n, multiscale_substrate)
            else:
                multiscale_substrate = np.where(wall_mask_7d, T_n, multiscale_substrate)

        if self.use_cuda:
            return cp.asnumpy(multiscale_substrate)
        return multiscale_substrate

