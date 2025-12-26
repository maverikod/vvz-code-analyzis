"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper functions for multi-particle potential computations (CPU path).

This module provides small, testable functions used by
`MultiParticlePotentialAnalyzer` to keep the class concise
and under file size limits while preserving public API.
"""

from __future__ import annotations

from typing import List, Any
import numpy as np


def setup_interaction_matrix(particles: List[Any], interaction_range: float, params: dict) -> np.ndarray:
    n = len(particles)
    M = np.zeros((n, n))
    for i, pi in enumerate(particles):
        for j, pj in enumerate(particles):
            if i == j:
                continue
            d = float(np.linalg.norm(pi.position - pj.position))
            M[i, j] = calculate_interaction_strength(d, interaction_range, params)
    return M


def calculate_interaction_strength(distance: float, interaction_range: float, params: dict) -> float:
    return step_interaction_potential(distance, interaction_range, params.get("interaction_strength", 1.0))


def calculate_three_body_strength(d12: float, d13: float, d23: float, interaction_range: float, params: dict) -> float:
    if d12 < interaction_range and d13 < interaction_range and d23 < interaction_range:
        return step_three_body_potential(d12, d13, d23, interaction_range, params.get("interaction_strength", 1.0))
    return 0.0


def step_interaction_potential(distance: float, interaction_range: float, strength: float) -> float:
    return float(strength) if distance < interaction_range else 0.0


def step_three_body_potential(d12: float, d13: float, d23: float, interaction_range: float, strength: float) -> float:
    avg = (d12 + d13 + d23) / 3.0
    return float(strength) if avg < interaction_range else 0.0


def single_particle_field(domain: Any, particle: Any, interaction_range: float, params: dict) -> np.ndarray:
    N = int(domain.N)
    L = getattr(domain, "L", N)
    Lval = float(L[0] if hasattr(L, "__len__") else L)
    x = np.linspace(0.0, Lval, N)
    y = np.linspace(0.0, Lval, N)
    z = np.linspace(0.0, Lval, N)
    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
    r = np.sqrt((X - particle.position[0]) ** 2 + (Y - particle.position[1]) ** 2 + (Z - particle.position[2]) ** 2)
    mask = (r < interaction_range).astype(np.float64)
    return float(particle.charge) * params.get("interaction_strength", 1.0) * mask


def pair_interaction_field(domain: Any, p1: Any, p2: Any, interaction_range: float, params: dict) -> np.ndarray:
    d = float(np.linalg.norm(p1.position - p2.position))
    s = calculate_interaction_strength(d, interaction_range, params)
    return s * np.ones((int(domain.N), int(domain.N), int(domain.N)), dtype=np.float64) if s else np.zeros((int(domain.N), int(domain.N), int(domain.N)), dtype=np.float64)


def three_body_interaction_field(domain: Any, p1: Any, p2: Any, p3: Any, interaction_range: float, params: dict) -> np.ndarray:
    d12 = float(np.linalg.norm(p1.position - p2.position))
    d13 = float(np.linalg.norm(p1.position - p3.position))
    d23 = float(np.linalg.norm(p2.position - p3.position))
    s = calculate_three_body_strength(d12, d13, d23, interaction_range, params)
    return s * np.ones((int(domain.N), int(domain.N), int(domain.N)), dtype=np.float64) if s else np.zeros((int(domain.N), int(domain.N), int(domain.N)), dtype=np.float64)


def higher_order_interactions_field(domain: Any, particles: List[Any], interaction_range: float, params: dict) -> np.ndarray:
    N = int(domain.N)
    pot = np.zeros((N, N, N), dtype=np.float64)
    n = len(particles)
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                pot += three_body_interaction_field(domain, particles[i], particles[j], particles[k], interaction_range, params)
    return pot


