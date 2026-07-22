"""
MCP command wrapper: get_comprehensive_analysis_results.

Reads saved comprehensive_analysis_results rows without running analysis.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ...core.database_driver_pkg.domain.comprehensive_analysis import (
    get_comprehensive_analysis_results,
)
from ...core.database_driver_pkg.domain.files import (
    get_file_by_id,
    get_project_file_rows,
)
from ...core.exceptions import ValidationError
from ..ast.file_resolution import resolve_project_file_record
from ..base_mcp_command import BaseMCPCommand
from . import schema
from .metadata import get_metadata


def _file_row_id(row: Dict[str, Any]) -> Optional[str]:
    """Return a normalized files.id value from a database row."""
    raw_id = row.get("id") or row.get("file_id")
    if raw_id is None:
        return None
    file_id = str(raw_id).strip()
    return file_id or None


def _relative_path(row: Dict[str, Any]) -> Optional[str]:
    """Return normalized relative path when present."""
    rel = row.get("relative_path")
    if rel:
        return str(rel).replace("\\", "/")
    return None


def _build_item(
    *,
    row: Dict[str, Any],
    saved: Dict[str, Any],
    result_key: Optional[str],
    include_summary: bool,
) -> Tuple[Dict[str, Any], int]:
    """Build one response item and return it with selected finding count."""
    results_obj = saved.get("results") or {}
    selected = results_obj.get(result_key, []) if result_key else results_obj
    finding_count = len(selected) if isinstance(selected, list) else 0
    item: Dict[str, Any] = {
        "file_id": _file_row_id(row),
        "path": row.get("path"),
        "relative_path": _relative_path(row),
        "file_mtime": saved.get("file_mtime"),
        "analysis_date": saved.get("analysis_date"),
        "results": selected,
    }
    if include_summary:
        item["summary"] = saved.get("summary") or {}
    return item, finding_count


class ComprehensiveAnalysisResultsMCPCommand(BaseMCPCommand):
    """Read saved comprehensive_analysis results from the database."""

    name = "get_comprehensive_analysis_results"
    version = "1.0.0"
    descr = "Read saved comprehensive_analysis results without running analysis"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return schema.get_schema(cls)

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate common parameters before reading saved results."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        if params.get("file_id") and params.get("file_path"):
            raise ValidationError(
                "Use either file_id or file_path, not both",
                field="file_id",
                details={"file_path": params.get("file_path")},
            )
        return params

    async def execute(
        self,
        project_id: str,
        file_id: Optional[str] = None,
        file_path: Optional[str] = None,
        result_key: Optional[str] = None,
        include_summary: bool = True,
        include_empty: bool = False,
        limit: int = 100,
        offset: int = 0,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute saved comprehensive analysis result lookup."""
        params: Dict[str, Any] = {
            "project_id": project_id,
            "file_id": file_id,
            "file_path": file_path,
            "result_key": result_key,
            "include_summary": include_summary,
            "include_empty": include_empty,
            "limit": limit,
            "offset": offset,
        }
        params.update(kwargs)
        try:
            params = self.validate_params(params)
        except ValidationError as exc:
            return self._handle_error(
                exc, "VALIDATION_ERROR", "get_comprehensive_analysis_results"
            )

        project_id = str(params["project_id"])
        file_id = params.get("file_id")
        file_path = params.get("file_path")
        result_key = params.get("result_key")
        include_summary = bool(params.get("include_summary", True))
        include_empty = bool(params.get("include_empty", False))
        raw_limit = params.get("limit", 100)
        raw_offset = params.get("offset", 0)
        limit = 100 if raw_limit is None else int(raw_limit)
        offset = 0 if raw_offset is None else int(raw_offset)
        if limit < 1 or limit > 1000:
            return ErrorResult(
                message="limit must be between 1 and 1000",
                code="VALIDATION_ERROR",
            )
        if offset < 0:
            return ErrorResult(
                message="offset must be greater than or equal to 0",
                code="VALIDATION_ERROR",
            )

        try:
            root_path = self._resolve_project_root(project_id)
            db = self._open_database()
            try:
                rows: List[Dict[str, Any]]
                if file_path:
                    resolved = resolve_project_file_record(
                        db=db,
                        project_id=project_id,
                        project_root=root_path,
                        file_path=str(file_path),
                    )
                    file_record = resolved.get("file_record")
                    if not file_record:
                        return ErrorResult(
                            message=f"File not found in project: {file_path}",
                            code="FILE_NOT_FOUND",
                        )
                    rows = [file_record]
                elif file_id:
                    file_record = get_file_by_id(db, str(file_id))
                    if not file_record or file_record.get("project_id") != project_id:
                        return ErrorResult(
                            message=f"File not found in project: {file_id}",
                            code="FILE_NOT_FOUND",
                        )
                    rows = [file_record]
                else:
                    rows = get_project_file_rows(db, project_id, include_deleted=False)

                items_all: List[Dict[str, Any]] = []
                files_with_saved_results = 0
                total_findings = 0
                for row in rows:
                    row_file_id = _file_row_id(row)
                    if not row_file_id:
                        continue
                    saved = get_comprehensive_analysis_results(db, row_file_id)
                    if not saved:
                        continue
                    files_with_saved_results += 1
                    item, finding_count = _build_item(
                        row=row,
                        saved=saved,
                        result_key=result_key,
                        include_summary=include_summary,
                    )
                    total_findings += finding_count
                    if result_key and not include_empty and finding_count == 0:
                        continue
                    items_all.append(item)

                total_matches = len(items_all)
                page = items_all[offset : offset + limit]
                return SuccessResult(
                    data={
                        "project_id": project_id,
                        "result_key": result_key,
                        "items": page,
                        "pagination": {
                            "limit": limit,
                            "offset": offset,
                            "total_matches": total_matches,
                            "has_more": offset + limit < total_matches,
                        },
                        "summary": {
                            "files_scanned": len(rows),
                            "files_with_saved_results": files_with_saved_results,
                            "files_returned": len(page),
                            "total_matches": total_matches,
                            "total_findings": total_findings,
                        },
                    }
                )
            finally:
                db.disconnect()
        except Exception as exc:
            return self._handle_error(
                exc,
                "COMPREHENSIVE_ANALYSIS_RESULTS_ERROR",
                "get_comprehensive_analysis_results",
            )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_metadata(cls)
