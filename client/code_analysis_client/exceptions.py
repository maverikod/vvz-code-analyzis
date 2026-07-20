"""Client-side errors (no dependency on code_analysis server package)."""

from __future__ import annotations

from typing import Any, Dict, Optional


class ClientValidationError(ValueError):
    """Parameters do not match the command JSON schema (from server ``help``)."""

    def __init__(
        self,
        message: str,
        *,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize validation error with optional field and details payload."""
        super().__init__(message)
        self.field = field
        self.details = details or {}


class JobFailedError(ClientValidationError):
    """A queued job failed/stopped/cancelled, or reported an ``error`` status."""

    def __init__(
        self,
        job_id: Optional[str],
        error: Any = None,
        *,
        status: Optional[str] = None,
    ) -> None:
        """Store job id, verbatim error payload, and terminal status."""
        message = f"Job {job_id!r} failed (status={status!r}): {error!r}"
        super().__init__(
            message,
            field="job_id",
            details={"job_id": job_id, "status": status, "error": error},
        )
        self.job_id = job_id
        self.error = error
        self.status = status


class JobTimeoutError(ClientValidationError):
    """Polling exceeded ``timeout``; the job keeps running server-side."""

    def __init__(self, job_id: Optional[str], timeout: Optional[float]) -> None:
        """Store job id and the timeout that was exceeded."""
        message = (
            f"Timed out after {timeout}s waiting for job {job_id!r}; "
            "the job keeps running server-side - poll queue_get_job_status "
            "manually or retry with a longer timeout."
        )
        super().__init__(
            message,
            field="job_id",
            details={"job_id": job_id, "timeout": timeout},
        )
        self.job_id = job_id
        self.timeout = timeout


class CommandFailedError(ClientValidationError):
    """A queued command completed but its inner result is an error envelope."""

    def __init__(
        self, command: Optional[str], job_id: Optional[str], error: Any
    ) -> None:
        """Store command name, job id, and the verbatim inner error object."""
        message = f"Command {command!r} failed (job_id={job_id!r}): {error!r}"
        super().__init__(
            message,
            field="command",
            details={"command": command, "job_id": job_id, "error": error},
        )
        self.command = command
        self.job_id = job_id
        self.error = error
