"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power Balance Postulate implementation for BVP framework.

This module provides backward compatibility for the Power Balance Postulate,
redirecting to the new modular power balance package.

Theoretical Background:
    Power balance is maintained at the external boundary through proper
    accounting of energy flows. This module provides backward compatibility
    while the new modular power balance package is used internally.

Example:
    >>> postulate = PowerBalancePostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

from .postulates.power_balance import (
    PowerBalancePostulate as ModularPowerBalancePostulate,
)

# Create backward compatibility alias
PowerBalancePostulate = ModularPowerBalancePostulate
