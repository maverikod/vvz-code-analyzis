"""
Async façade over mcp-proxy-adapter JsonRpcClient for code-analysis-server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Dict, Literal, Mapping, Optional, Union, overload

try:
    from mcp_proxy_adapter.client.jsonrpc_client.client import JsonRpcClient
except Exception:  # pragma: no cover - compatibility with older layouts
    from mcp_proxy_adapter.client.jsonrpc_client import JsonRpcClient

from code_analysis_client.commands_proxy import ValidatedCommandsProxy
from code_analysis_client.config import (
    adapter_settings_from_server_config,
    adapter_settings_to_jsonrpc_kwargs,
    load_server_config,
)
from code_analysis_client.file_session import FileSessionClient
from code_analysis_client.queue_wait import (
    QueuedJob,
    StatusHook,
    extract_job_id,
    is_queued_envelope,
    unwrap_job_result,
    wait_for_job,
)
from code_analysis_client.universal_file import UniversalFileClient
from code_analysis_client.server_schema import fetch_command_schema_from_server
from code_analysis_client.validation import (
    prepare_params_for_schema,
    validate_params_against_schema,
)


class CodeAnalysisAsyncClient:
    """Async client: domain commands via :meth:`call` / :meth:`call_unified`; full adapter API on :attr:`rpc`."""

    __slots__ = ("_rpc", "_command_schema_cache", "_commands_proxy")

    def __init__(self, **jsonrpc_kwargs: Any) -> None:
        """Same keyword arguments as ``JsonRpcClient`` (``protocol``, ``host``, ``port``, ``cert``, …)."""
        self._rpc = JsonRpcClient(**jsonrpc_kwargs)
        self._command_schema_cache: Dict[str, Dict[str, Any]] = {}
        self._commands_proxy: Optional[ValidatedCommandsProxy] = None

    @classmethod
    def from_jsonrpc_kwargs(cls, **kwargs: Any) -> CodeAnalysisAsyncClient:
        """Alias for ``CodeAnalysisAsyncClient(**kwargs)``."""
        return cls(**kwargs)

    @classmethod
    def from_adapter_settings(
        cls,
        settings: Mapping[str, Any],
        *,
        timeout: float | None = 60.0,
        check_hostname: bool = False,
        token_header: str | None = None,
        token: str | None = None,
    ) -> CodeAnalysisAsyncClient:
        """Build from a dict like ``PipelineConfig.generate_adapter_client_settings()``."""
        kwargs = adapter_settings_to_jsonrpc_kwargs(
            settings,
            timeout=timeout,
            check_hostname=check_hostname,
            token_header=token_header,
            token=token,
        )
        return cls(**kwargs)

    @classmethod
    def from_server_config(
        cls,
        config: Mapping[str, Any],
        *,
        timeout: float | None = 60.0,
        check_hostname: bool = False,
        token_header: str | None = None,
        token: str | None = None,
    ) -> CodeAnalysisAsyncClient:
        """Derive connection settings from a code-analysis server config object."""
        settings = adapter_settings_from_server_config(config)
        return cls.from_adapter_settings(
            settings,
            timeout=timeout,
            check_hostname=check_hostname,
            token_header=token_header,
            token=token,
        )

    @classmethod
    def from_server_config_path(
        cls,
        path: str | Path,
        *,
        timeout: float | None = 60.0,
        check_hostname: bool = False,
        token_header: str | None = None,
        token: str | None = None,
    ) -> CodeAnalysisAsyncClient:
        """Load ``config.json`` and connect."""
        return cls.from_server_config(
            load_server_config(path),
            timeout=timeout,
            check_hostname=check_hostname,
            token_header=token_header,
            token=token,
        )

    @property
    def rpc(self) -> JsonRpcClient:
        """Underlying mcp-proxy-adapter client (queue, transfer, ``help``, ``execute_command``, …)."""
        return self._rpc

    @property
    def commands(self) -> ValidatedCommandsProxy:
        """Dynamic validated wrappers: schema is loaded from the server via ``help`` (cached)."""
        if self._commands_proxy is None:
            self._commands_proxy = ValidatedCommandsProxy(self)
        return self._commands_proxy

    def clear_command_schema_cache(self) -> None:
        """Drop cached command schemas (after ``reload`` or when server definitions change)."""
        self._command_schema_cache.clear()

    @property
    def file_sessions(self) -> FileSessionClient:
        """Session workflow: ``session_*``, ``subordinate_session_*``, transfer, advisory locks."""
        return FileSessionClient(self)

    @property
    def universal_files(self) -> UniversalFileClient:
        """Read-only structured preview (``universal_file_preview`` command)."""
        return UniversalFileClient(self)

    async def get_command_schema(
        self, command: str, *, refresh: bool = False
    ) -> Dict[str, Any]:
        """Fetch input JSON schema for ``command`` using server ``help`` (with in-memory cache)."""
        if not refresh and command in self._command_schema_cache:
            return self._command_schema_cache[command]
        schema = await fetch_command_schema_from_server(self._rpc, command)
        self._command_schema_cache[command] = schema
        return schema

    async def _execute(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        auto_poll: bool = True,
        timeout: Optional[float] = None,
        poll_interval: float = 1.0,
        status_hook: Optional[StatusHook] = None,
    ) -> Union[Dict[str, Any], QueuedJob]:
        """Single queue-aware core every public entry point routes through.

        Runs ``command`` via the raw adapter ``execute_command``. If the
        immediate response is a queue-service envelope
        (:func:`code_analysis_client.queue_wait.is_queued_envelope`):

        * ``auto_poll=True`` (default, unchanged behavior) — polls the job to
          completion (:func:`~code_analysis_client.queue_wait.wait_for_job`)
          and returns the unwrapped inner result
          (:func:`~code_analysis_client.queue_wait.unwrap_job_result`), raising
          on failure.
        * ``auto_poll=False`` — returns a
          :class:`~code_analysis_client.queue_wait.QueuedJob` handle
          immediately instead of polling; call ``await handle.wait(...)`` to
          get the same result the default path would have returned.

        A non-queued response is returned unchanged regardless of ``auto_poll``.
        """
        resp = await self._rpc.execute_command(
            command,
            params or {},
            use_cmd_endpoint=use_cmd_endpoint,
        )
        if not is_queued_envelope(resp):
            return resp

        job_id = extract_job_id(resp)
        if not auto_poll:
            return QueuedJob(job_id=job_id, envelope=resp, rpc=self._rpc)

        status = await wait_for_job(
            self._rpc,
            job_id,
            timeout=timeout,
            poll_interval=poll_interval,
            status_hook=status_hook,
        )
        return await unwrap_job_result(status, rpc=self._rpc)

    @overload
    async def call_validated(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        refresh_schema: bool = False,
        auto_poll: Literal[True] = True,
        timeout: Optional[float] = None,
        poll_interval: float = 1.0,
        status_hook: Optional[StatusHook] = None,
    ) -> Dict[str, Any]: ...

    @overload
    async def call_validated(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        refresh_schema: bool = False,
        auto_poll: Literal[False],
        timeout: Optional[float] = None,
        poll_interval: float = 1.0,
        status_hook: Optional[StatusHook] = None,
    ) -> QueuedJob: ...

    @overload
    async def call_validated(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        refresh_schema: bool = False,
        auto_poll: bool,
        timeout: Optional[float] = None,
        poll_interval: float = 1.0,
        status_hook: Optional[StatusHook] = None,
    ) -> Union[Dict[str, Any], QueuedJob]: ...

    async def call_validated(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        refresh_schema: bool = False,
        auto_poll: bool = True,
        timeout: Optional[float] = None,
        poll_interval: float = 1.0,
        status_hook: Optional[StatusHook] = None,
    ) -> Union[Dict[str, Any], QueuedJob]:
        """``help`` → schema on server, shallow local validation, then the queue-aware core.

        ``auto_poll`` (default ``True``) forwards to :meth:`_execute`: set it
        to ``False`` to get a :class:`~code_analysis_client.queue_wait.QueuedJob`
        handle back instead of blocking until a queued job completes.
        """
        schema = await self.get_command_schema(command, refresh=refresh_schema)
        merged = dict(params or {})
        prepared = prepare_params_for_schema(merged, schema)
        validate_params_against_schema(prepared, schema, command_name=command)
        return await self._execute(
            command,
            prepared,
            use_cmd_endpoint=use_cmd_endpoint,
            auto_poll=auto_poll,
            timeout=timeout,
            poll_interval=poll_interval,
            status_hook=status_hook,
        )

    @overload
    async def call_unified_validated(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        refresh_schema: bool = False,
        use_cmd_endpoint: bool = False,
        expect_queue: Optional[bool] = None,
        auto_poll: Literal[True] = True,
        poll_interval: float = 1.0,
        timeout: Optional[float] = None,
        status_hook: Optional[StatusHook] = None,
    ) -> Dict[str, Any]: ...

    @overload
    async def call_unified_validated(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        refresh_schema: bool = False,
        use_cmd_endpoint: bool = False,
        expect_queue: Optional[bool] = None,
        auto_poll: Literal[False],
        poll_interval: float = 1.0,
        timeout: Optional[float] = None,
        status_hook: Optional[StatusHook] = None,
    ) -> QueuedJob: ...

    @overload
    async def call_unified_validated(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        refresh_schema: bool = False,
        use_cmd_endpoint: bool = False,
        expect_queue: Optional[bool] = None,
        auto_poll: bool,
        poll_interval: float = 1.0,
        timeout: Optional[float] = None,
        status_hook: Optional[StatusHook] = None,
    ) -> Union[Dict[str, Any], QueuedJob]: ...

    async def call_unified_validated(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        refresh_schema: bool = False,
        use_cmd_endpoint: bool = False,
        expect_queue: Optional[bool] = None,
        auto_poll: bool = True,
        poll_interval: float = 1.0,
        timeout: Optional[float] = None,
        status_hook: Optional[StatusHook] = None,
    ) -> Union[Dict[str, Any], QueuedJob]:
        """Deprecated alias for :meth:`call_validated`.

        ``expect_queue`` remains accepted-and-ignored (documented no-op, kept
        only for signature compatibility). ``auto_poll`` is now LIVE again and
        forwards straight to the shared :meth:`_execute` core: ``auto_poll=False``
        returns a :class:`~code_analysis_client.queue_wait.QueuedJob` handle
        instead of a plain dict when the response is a queued envelope — a
        return-type change versus the previous era where this parameter was
        silently ignored and every path always blocked until completion.
        Prefer :meth:`call_validated` directly; this alias emits
        ``DeprecationWarning`` on every call.
        """
        warnings.warn(
            "call_unified_validated is deprecated; use call_validated() "
            "directly (its 'auto_poll' keyword works the same way).",
            DeprecationWarning,
            stacklevel=2,
        )
        schema = await self.get_command_schema(command, refresh=refresh_schema)
        merged = dict(params or {})
        prepared = prepare_params_for_schema(merged, schema)
        validate_params_against_schema(prepared, schema, command_name=command)
        return await self._execute(
            command,
            prepared,
            use_cmd_endpoint=use_cmd_endpoint,
            auto_poll=auto_poll,
            timeout=timeout,
            poll_interval=poll_interval,
            status_hook=status_hook,
        )

    @overload
    async def call(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        auto_poll: Literal[True] = True,
        timeout: Optional[float] = None,
        poll_interval: float = 1.0,
        status_hook: Optional[StatusHook] = None,
    ) -> Dict[str, Any]: ...

    @overload
    async def call(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        auto_poll: Literal[False],
        timeout: Optional[float] = None,
        poll_interval: float = 1.0,
        status_hook: Optional[StatusHook] = None,
    ) -> QueuedJob: ...

    @overload
    async def call(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        auto_poll: bool,
        timeout: Optional[float] = None,
        poll_interval: float = 1.0,
        status_hook: Optional[StatusHook] = None,
    ) -> Union[Dict[str, Any], QueuedJob]: ...

    async def call(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        auto_poll: bool = True,
        timeout: Optional[float] = None,
        poll_interval: float = 1.0,
        status_hook: Optional[StatusHook] = None,
    ) -> Union[Dict[str, Any], QueuedJob]:
        """Run any registered server command; queued jobs are polled to completion by default.

        Pass ``auto_poll=False`` to get a
        :class:`~code_analysis_client.queue_wait.QueuedJob` handle back
        immediately instead (call ``await handle.wait(...)`` when you're
        ready to block on it).
        """
        return await self._execute(
            command,
            params,
            use_cmd_endpoint=use_cmd_endpoint,
            auto_poll=auto_poll,
            timeout=timeout,
            poll_interval=poll_interval,
            status_hook=status_hook,
        )

    @overload
    async def call_unified(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        expect_queue: Optional[bool] = None,
        auto_poll: Literal[True] = True,
        poll_interval: float = 1.0,
        timeout: Optional[float] = None,
        status_hook: Optional[StatusHook] = None,
    ) -> Dict[str, Any]: ...

    @overload
    async def call_unified(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        expect_queue: Optional[bool] = None,
        auto_poll: Literal[False],
        poll_interval: float = 1.0,
        timeout: Optional[float] = None,
        status_hook: Optional[StatusHook] = None,
    ) -> QueuedJob: ...

    @overload
    async def call_unified(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        expect_queue: Optional[bool] = None,
        auto_poll: bool,
        poll_interval: float = 1.0,
        timeout: Optional[float] = None,
        status_hook: Optional[StatusHook] = None,
    ) -> Union[Dict[str, Any], QueuedJob]: ...

    async def call_unified(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        expect_queue: Optional[bool] = None,
        auto_poll: bool = True,
        poll_interval: float = 1.0,
        timeout: Optional[float] = None,
        status_hook: Optional[StatusHook] = None,
    ) -> Union[Dict[str, Any], QueuedJob]:
        """Deprecated alias for :meth:`call`.

        ``expect_queue`` remains accepted-and-ignored (documented no-op).
        ``auto_poll`` is now LIVE again and forwards straight to the shared
        :meth:`_execute` core: ``auto_poll=False`` returns a
        :class:`~code_analysis_client.queue_wait.QueuedJob` handle instead of
        a plain dict when the response is a queued envelope — a return-type
        change versus the previous era where this parameter was silently
        ignored. Prefer :meth:`call` directly; this alias emits
        ``DeprecationWarning`` on every call.
        """
        warnings.warn(
            "call_unified is deprecated; use call() directly (its "
            "'auto_poll' keyword works the same way).",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self._execute(
            command,
            params,
            use_cmd_endpoint=use_cmd_endpoint,
            auto_poll=auto_poll,
            timeout=timeout,
            poll_interval=poll_interval,
            status_hook=status_hook,
        )

    async def close(self) -> None:
        """Close the underlying JSON-RPC transport."""
        await self._rpc.close()

    async def __aenter__(self) -> CodeAnalysisAsyncClient:
        """Enter async context manager and return this client."""
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Close the client when leaving an async context manager block."""
        await self.close()
