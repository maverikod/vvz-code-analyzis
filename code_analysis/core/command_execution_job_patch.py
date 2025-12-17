"""
Patch for CommandExecutionJob to support progress tracking.

This module patches CommandExecutionJob to create and pass ProgressTracker
through context, allowing commands to update progress and logs.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import asyncio

logger = logging.getLogger(__name__)


# Flag to track if patch has been applied
_patch_applied = False


def patch_command_execution_job():
    """
    Patch CommandExecutionJob to support progress tracking.
    
    This function modifies CommandExecutionJob.run() to create a ProgressTracker
    and pass it through context before executing the command.
    """
    global _patch_applied

    # Only apply patch once
    if _patch_applied:
        return

    try:
        from mcp_proxy_adapter.commands.queue.jobs import CommandExecutionJob
        from ..core.progress_tracker import ProgressTracker

        # Check if already patched (has our attribute)
        if hasattr(CommandExecutionJob.run, "_progress_tracker_patched"):
            _patch_applied = True
            return

        # Store original run method
        original_run = CommandExecutionJob.run

        def patched_run(self):
            """Patched run method that creates and passes ProgressTracker."""
            # Get context from mcp_params
            context = self.mcp_params.get("context", {}) or {}
            if not isinstance(context, dict):
                context = {}

            # Create ProgressTracker with methods from job
            progress_tracker = ProgressTracker(
                set_progress_fn=self.set_progress,
                set_description_fn=self.set_description,
                set_status_fn=self.set_status,
                log_fn=lambda msg: self.logger.info(msg),
            )

            # Add ProgressTracker to context
            context["progress_tracker"] = progress_tracker

            # Update mcp_params with modified context
            self.mcp_params["context"] = context

            # Call original run method (it will use the updated context)
            original_run(self)

        # Mark as patched
        patched_run._progress_tracker_patched = True

        # Apply patch
        CommandExecutionJob.run = patched_run
        _patch_applied = True
        logger.debug("Successfully patched CommandExecutionJob for progress tracking")

    except ImportError as e:
        logger.warning(f"Failed to patch CommandExecutionJob: {e}")
    except Exception as e:
        logger.error(f"Error patching CommandExecutionJob: {e}", exc_info=True)


# Auto-patch on import
patch_command_execution_job()

