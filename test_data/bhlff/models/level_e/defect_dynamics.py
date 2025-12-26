"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Defect dynamics implementation for Level E experiments in 7D phase field theory.

This module implements the dynamics of topological defects including
motion, forces, and interactions between defects.

Theoretical Background:
    Defect dynamics follows the Thiele equation: ẋ = -∇U_eff + G × ẋ + D ẋ
    where U_eff is the effective potential, G is the gyroscopic tensor,
    and D is the dissipation tensor.

Mathematical Foundation:
    The Thiele equation describes the motion of topological defects
    under the influence of effective forces, gyroscopic effects,
    and dissipative processes.

Example:
    >>> defect = DefectModel(domain, physics_params)
    >>> trajectory = defect.simulate_defect_motion(initial_position, time_steps)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple


class DefectDynamics:
    """
    Defect dynamics calculator for topological defects.

    Physical Meaning:
        Implements the dynamics of topological defects following the
        Thiele equation, including effective forces, gyroscopic effects,
        and dissipative processes.

    Mathematical Foundation:
        Solves the Thiele equation: ẋ = -∇U_eff + G × ẋ + D ẋ
        where the motion is governed by effective potential gradients,
        gyroscopic forces, and dissipation.
    """

    def __init__(self, domain: "Domain", physics_params: Dict[str, Any]):
        """
        Initialize defect dynamics calculator.

        Physical Meaning:
            Sets up the computational framework for defect dynamics
            including force calculations, gyroscopic effects, and
            dissipative processes.

        Args:
            domain: Computational domain
            physics_params: Physical parameters
        """
        self.domain = domain
        self.params = physics_params
        self._setup_dynamics_parameters()

    def _setup_dynamics_parameters(self) -> None:
        """
        Setup parameters for defect dynamics.

        Physical Meaning:
            Initializes the physical parameters required for
            defect dynamics calculations using energy-based dynamics.
        """
        # NO MASS PARAMETERS - use energy-based dynamics
        self.gyroscopic_coefficient = self.params.get("gyroscopic_coefficient", 1.0)
        self.time_step = self.params.get("time_step", 0.01)
        self.max_velocity = self.params.get("max_velocity", 10.0)

        # Energy-based parameters
        self.energy_threshold = self.params.get("energy_threshold", 1.0)
        self.phase_coherence_length = self.params.get("phase_coherence_length", 1.0)

    def simulate_defect_motion(
        self, initial_position: np.ndarray, time_steps: int, field: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        Simulate defect motion using energy-based dynamics.

        Physical Meaning:
            Computes defect motion based on energy gradients
            rather than classical mass-based dynamics.
        """
        # Compute energy landscape
        energy_landscape = self._compute_energy_landscape(field)

        # Compute energy gradients (instead of forces)
        energy_gradients = self._compute_energy_gradients(energy_landscape)

        # Energy-based motion (no mass)
        positions = self._integrate_energy_dynamics(
            initial_position, energy_gradients, time_steps
        )

        return {
            "positions": positions,
            "energy_landscape": energy_landscape,
            "energy_gradients": energy_gradients,
        }

    def _find_defect_position(self, field: np.ndarray) -> np.ndarray:
        """
        Find current position of defect in field.

        Physical Meaning:
            Locates the defect center by finding the position
            of minimum amplitude in the field configuration.

        Args:
            field: Complex field configuration

        Returns:
            Position of defect center
        """
        # Compute field amplitude
        amplitude = np.abs(field)

        # Find minimum amplitude (defect core)
        min_indices = np.unravel_index(np.argmin(amplitude), amplitude.shape)

        # Convert to physical coordinates
        L = self.domain.L
        N = self.domain.N
        position = np.array(
            [min_indices[0] * L / N, min_indices[1] * L / N, min_indices[2] * L / N]
        )

        return position

    def _compute_defect_force(
        self, position: np.ndarray, field: np.ndarray
    ) -> np.ndarray:
        """
        Compute effective force on defect.

        Physical Meaning:
            Calculates the effective force acting on the defect
            due to the gradient of the effective potential.

        Mathematical Foundation:
            F = -∇U_eff where U_eff is the effective potential
            derived from the field configuration.

        Args:
            position: Current defect position
            field: Background field configuration

        Returns:
            Effective force vector
        """
        # Compute potential energy
        potential = self._compute_effective_potential(field)

        # Compute gradient using finite differences
        force = self._compute_potential_gradient(potential, position)

        return -force

    def _compute_effective_potential(self, field: np.ndarray) -> np.ndarray:
        """
        Compute effective potential from field configuration.

        Physical Meaning:
            Calculates the effective potential that governs
            defect motion based on the field configuration.
        """
        # Use field amplitude as potential
        potential = np.abs(field) ** 2

        # Add smoothing to avoid singularities
        potential = potential + 1e-6

        return potential

    def _compute_potential_gradient(
        self, potential: np.ndarray, position: np.ndarray
    ) -> np.ndarray:
        """
        Compute gradient of potential at defect position.

        Physical Meaning:
            Calculates the spatial gradient of the effective
            potential at the defect position.
        """
        N = self.domain.N
        L = self.domain.L

        # Convert position to grid indices
        i = int(position[0] * N / L) % N
        j = int(position[1] * N / L) % N
        k = int(position[2] * N / L) % N

        # Compute gradients using finite differences
        dx = L / N
        grad_x = (potential[(i + 1) % N, j, k] - potential[(i - 1) % N, j, k]) / (
            2 * dx
        )
        grad_y = (potential[i, (j + 1) % N, k] - potential[i, (j - 1) % N, k]) / (
            2 * dx
        )
        grad_z = (potential[i, j, (k + 1) % N] - potential[i, j, (k - 1) % N]) / (
            2 * dx
        )

        return np.array([grad_x, grad_y, grad_z])

    def _interpolate_potential(
        self, potential: np.ndarray, position: np.ndarray
    ) -> float:
        """
        Interpolate potential at arbitrary position.

        Physical Meaning:
            Computes the potential value at an arbitrary position
            using interpolation from the grid values.

        Args:
            potential: Potential field on grid
            position: Position for interpolation

        Returns:
            Interpolated potential value
        """
        N = self.domain.N
        L = self.domain.L

        # Convert to grid coordinates
        x = position[0] * N / L
        y = position[1] * N / L
        z = position[2] * N / L

        # Trilinear interpolation
        x0, y0, z0 = int(x), int(y), int(z)
        x1, y1, z1 = (x0 + 1) % N, (y0 + 1) % N, (z0 + 1) % N

        # Interpolation weights
        wx = x - x0
        wy = y - y0
        wz = z - z0

        # Interpolate
        c000 = potential[x0, y0, z0]
        c001 = potential[x0, y0, z1]
        c010 = potential[x0, y1, z0]
        c011 = potential[x0, y1, z1]
        c100 = potential[x1, y0, z0]
        c101 = potential[x1, y0, z1]
        c110 = potential[x1, y1, z0]
        c111 = potential[x1, y1, z1]

        # Trilinear interpolation formula
        result = (
            c000 * (1 - wx) * (1 - wy) * (1 - wz)
            + c001 * (1 - wx) * (1 - wy) * wz
            + c010 * (1 - wx) * wy * (1 - wz)
            + c011 * (1 - wx) * wy * wz
            + c100 * wx * (1 - wy) * (1 - wz)
            + c101 * wx * (1 - wy) * wz
            + c110 * wx * wy * (1 - wz)
            + c111 * wx * wy * wz
        )

        return result

    def _compute_gyroscopic_force(self, velocity: np.ndarray) -> np.ndarray:
        """
        Compute gyroscopic force.

        Physical Meaning:
            Calculates the gyroscopic force G × ẋ that arises
            from the topological structure of the defect.

        Mathematical Foundation:
            F_gyro = G × ẋ where G is the gyroscopic tensor.

        Args:
            velocity: Current velocity vector

        Returns:
            Gyroscopic force vector
        """
        # Gyroscopic tensor (simplified as scalar)
        G = self.gyroscopic_coefficient

        # Gyroscopic force (perpendicular to velocity)
        if np.linalg.norm(velocity) > 1e-10:
            # Create perpendicular direction
            perpendicular = np.array([-velocity[1], velocity[0], 0])
            if np.linalg.norm(perpendicular) < 1e-10:
                perpendicular = np.array([0, -velocity[2], velocity[1]])

            perpendicular = perpendicular / np.linalg.norm(perpendicular)
            gyroscopic_force = G * np.linalg.norm(velocity) * perpendicular
        else:
            gyroscopic_force = np.zeros(3)

        return gyroscopic_force

    def _compute_dissipative_force(self, velocity: np.ndarray) -> np.ndarray:
        """
        Compute dissipative force.

        Physical Meaning:
            Calculates the dissipative force D ẋ that represents
            energy loss due to friction and other dissipative processes.

        Mathematical Foundation:
            F_diss = -D ẋ where D is the dissipation tensor.

        Args:
            velocity: Current velocity vector

        Returns:
            Dissipative force vector
        """
        D = self.dissipation_coefficient
        return -D * velocity

    def _compute_energy_landscape(self, field: np.ndarray) -> np.ndarray:
        """
        Compute energy landscape from field configuration.

        Physical Meaning:
            Calculates the energy landscape that governs
            defect motion based on 7D phase field theory.
        """
        # Use 7D phase field energy
        from bhlff.core.operators.fractional_laplacian import FractionalLaplacian

        # Compute fractional Laplacian energy
        laplacian_energy = FractionalLaplacian.apply(field)
        energy_landscape = np.abs(laplacian_energy) ** 2

        return energy_landscape

    def _compute_energy_gradients(self, energy_landscape: np.ndarray) -> np.ndarray:
        """
        Compute energy gradients for defect motion.

        Physical Meaning:
            Calculates energy gradients that drive
            defect motion in 7D phase field theory.
        """
        # Compute spatial gradients of energy
        grad_x = np.gradient(energy_landscape, axis=0)
        grad_y = np.gradient(energy_landscape, axis=1)
        grad_z = np.gradient(energy_landscape, axis=2)

        # Stack gradients
        energy_gradients = np.stack([grad_x, grad_y, grad_z], axis=-1)

        return energy_gradients

    def _integrate_energy_dynamics(
        self,
        initial_position: np.ndarray,
        energy_gradients: np.ndarray,
        time_steps: int,
    ) -> np.ndarray:
        """
        Integrate energy-based dynamics for defect motion.

        Physical Meaning:
            Integrates the energy-based equations of motion
            to obtain defect trajectory.
        """
        # Initialize trajectory
        positions = np.zeros((time_steps, 3))
        positions[0] = initial_position

        # Energy-based integration
        for step in range(1, time_steps):
            # Get current position
            current_pos = positions[step - 1]

            # Interpolate energy gradient at current position
            gradient = self._interpolate_energy_gradient(energy_gradients, current_pos)

            # Energy-based velocity (no mass)
            velocity = -gradient * self.time_step

            # Limit velocity
            velocity_magnitude = np.linalg.norm(velocity)
            if velocity_magnitude > self.max_velocity:
                velocity *= self.max_velocity / velocity_magnitude

            # Update position
            positions[step] = current_pos + velocity

        return positions

    def _interpolate_energy_gradient(
        self, energy_gradients: np.ndarray, position: np.ndarray
    ) -> np.ndarray:
        """
        Interpolate energy gradient at arbitrary position.

        Physical Meaning:
            Computes the energy gradient at an arbitrary position
            using interpolation from the grid values.
        """
        N = self.domain.N
        L = self.domain.L

        # Convert to grid coordinates
        x = position[0] * N / L
        y = position[1] * N / L
        z = position[2] * N / L

        # Trilinear interpolation for each component
        gradient = np.zeros(3)
        for i in range(3):
            gradient[i] = self._interpolate_scalar_field(
                energy_gradients[:, :, :, i], x, y, z
            )

        return gradient

    def _interpolate_scalar_field(
        self, field: np.ndarray, x: float, y: float, z: float
    ) -> float:
        """
        Interpolate scalar field at arbitrary position.
        """
        N = field.shape[0]

        # Trilinear interpolation
        x0, y0, z0 = int(x) % N, int(y) % N, int(z) % N
        x1, y1, z1 = (x0 + 1) % N, (y0 + 1) % N, (z0 + 1) % N

        # Interpolation weights
        wx = x - int(x)
        wy = y - int(y)
        wz = z - int(z)

        # Interpolate
        c000 = field[x0, y0, z0]
        c001 = field[x0, y0, z1]
        c010 = field[x0, y1, z0]
        c011 = field[x0, y1, z1]
        c100 = field[x1, y0, z0]
        c101 = field[x1, y0, z1]
        c110 = field[x1, y1, z0]
        c111 = field[x1, y1, z1]

        # Trilinear interpolation formula
        result = (
            c000 * (1 - wx) * (1 - wy) * (1 - wz)
            + c001 * (1 - wx) * (1 - wy) * wz
            + c010 * (1 - wx) * wy * (1 - wz)
            + c011 * (1 - wx) * wy * wz
            + c100 * wx * (1 - wy) * (1 - wz)
            + c101 * wx * (1 - wy) * wz
            + c110 * wx * wy * (1 - wz)
            + c111 * wx * wy * wz
        )

        return result
