"""
Driver-direct domain modules (stage 2 layer collapse).

Free functions taking a driver-shaped object (``driver.execute``/``select``/
``insert``/``update``/``delete``/``execute_batch``/``begin_transaction``/
``commit_transaction``/``rollback_transaction``) as their first argument,
duck-typed against both ``PostgreSQLDriver`` and the legacy ``DatabaseClient``
(both expose the same 13-primitive surface with matching shapes - see
scratchpad/stage2-parity-spike.md). These modules are the target home for the
domain methods currently implemented as ``client_api_*.py`` mixins on
``DatabaseClient``; they coexist additively with those mixins until Block C
deletes the client stack.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

__all__: list[str] = []
