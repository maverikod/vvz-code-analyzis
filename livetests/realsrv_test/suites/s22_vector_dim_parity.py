"""
Suite: vectorparity — embedding_vec dimension-parity tripwire (bug f4dd4039).

Exercises: check_vectors against a fixed, pre-existing, fully-vectorized
project, asserting it stays at 100% vectorized. Minimal, read-only guard
for a dimension-mismatch regression in the pgvector column-retype fix; see
``realsrv_test.core.lifecycle_vector_dim_parity`` module docstring for the
fallback design and its limitations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_vector_dim_parity import run_vector_dim_parity_check

SUITE_NAME = "vectorparity"
LIFECYCLE_RUNNERS = (run_vector_dim_parity_check,)
