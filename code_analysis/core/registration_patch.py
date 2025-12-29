"""
Patch for RegistrationManager to handle "already registered" error.

When server is already registered, we unregister first, then register again.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


def patch_registration_manager() -> None:
    """
    Patch RegistrationManager to handle "already registered" error.
    
    When server is already registered:
    1. Unregister first
    2. Then register again
    """
    try:
        from mcp_proxy_adapter.api.core.registration_manager.manager import (
            RegistrationManager,
        )

        # Store original register_with_proxy method
        original_register = RegistrationManager.register_with_proxy

        async def patched_register_with_proxy(
            self: RegistrationManager, config: Dict[str, Any]
        ) -> bool:
            """
            Patched register_with_proxy that handles "already registered" by unregistering first.
            """
            import asyncio

            # Call original method and catch "already registered" error
            try:
                return await original_register(self, config)
            except Exception as exc:
                error_str = str(exc).lower()
                full_error = self._format_httpx_error(exc)
                
                # Check if error is "already registered"
                if "already registered" in error_str or "already registered" in full_error.lower():
                    self.logger.info(
                        "⚠️  Server already registered, unregistering and re-registering..."
                    )
                    
                    # Unregister first
                    try:
                        self.registered = True  # Set flag so unregister can work
                        await self.unregister()
                        self.logger.info("✅ Successfully unregistered from proxy")
                    except Exception as e:
                        self.logger.warning(f"Failed to unregister: {e}")
                    
                    # Wait a bit before re-registering
                    await asyncio.sleep(1)
                    
                    # Try to register again
                    try:
                        return await original_register(self, config)
                    except Exception as e:
                        self.logger.error(f"Failed to re-register: {e}")
                        raise
                else:
                    # Not "already registered" error - re-raise
                    raise

        # Apply patch
        RegistrationManager.register_with_proxy = patched_register_with_proxy
        logger.info("✅ Applied registration manager patch for 'already registered' handling")

    except ImportError as e:
        logger.warning(f"Failed to import RegistrationManager for patching: {e}")
    except Exception as e:
        logger.error(f"Failed to patch RegistrationManager: {e}", exc_info=True)
