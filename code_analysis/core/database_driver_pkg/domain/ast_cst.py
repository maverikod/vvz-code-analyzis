"""
AST/CST tree storage, ported driver-direct (stage 2 layer collapse, Part 1).

Free-function port of the live subset of
``code_analysis.core.database_client.client_api_attributes``'s
``_ClientAPIAttributesMixin`` methods (``save_ast``, ``get_ast``, ``save_cst``).
Each function takes ``driver: Any`` (duck-typed against ``execute``/``select``/
``insert``/``update`` - see scratchpad/stage2-parity-spike.md) instead of ``self``.

NOT ported: ``get_cst``, ``get_vectors``, ``save_vectors`` - confirmed zero
production callers (stage 2 call map §1.2's 44 zero-caller list, re-verified with a
fresh grep during this port), and the dead ``query_ast``/``query_cst``/
``modify_ast``/``modify_cst`` methods, already deleted in Block A.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from code_analysis.core.database_client.objects.base import BaseObject
from code_analysis.core.database_driver_pkg.domain.files import get_file


def save_ast(driver: Any, file_id: int, ast_data: Dict[str, Any]) -> bool:
    """Save AST tree for file.

    Exact port of ``_ClientAPIAttributesMixin.save_ast``.
    """
    file = get_file(driver, file_id)
    if file is None:
        raise ValueError(f"File {file_id} not found")

    ast_json = json.dumps(ast_data)
    ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()

    existing = driver.select(
        "ast_trees",
        where={"file_id": file_id, "ast_hash": ast_hash},
    )

    file_mtime = (
        BaseObject._to_timestamp(file.last_modified)  # type: ignore[arg-type]
        if file.last_modified
        else 0
    )

    if existing:
        driver.update(
            "ast_trees",
            where={"id": existing[0]["id"]},
            data={
                "ast_json": ast_json,
                "file_mtime": file_mtime,
            },
        )
    else:
        driver.insert(
            "ast_trees",
            data={
                "file_id": file_id,
                "project_id": file.project_id,
                "ast_json": ast_json,
                "ast_hash": ast_hash,
                "file_mtime": file_mtime,
            },
        )

    return True


def get_ast(driver: Any, file_id: int) -> Optional[Dict[str, Any]]:
    """Get AST tree for file.

    Exact port of ``_ClientAPIAttributesMixin.get_ast``.
    """
    rows = driver.select(
        "ast_trees",
        where={"file_id": file_id},
        order_by=["updated_at"],
        limit=1,
    )
    if not rows:
        return None

    ast_json = rows[0].get("ast_json")
    if ast_json is None:
        return None

    try:
        parsed: Dict[str, Any] = json.loads(ast_json)
        return parsed
    except (json.JSONDecodeError, TypeError):
        return None


def save_cst(driver: Any, file_id: int, cst_code: str) -> bool:
    """Save CST tree (source code) for file.

    Exact port of ``_ClientAPIAttributesMixin.save_cst``.
    """
    file = get_file(driver, file_id)
    if file is None:
        raise ValueError(f"File {file_id} not found")

    cst_hash = hashlib.sha256(cst_code.encode()).hexdigest()

    existing = driver.select(
        "cst_trees",
        where={"file_id": file_id, "cst_hash": cst_hash},
    )

    file_mtime = (
        BaseObject._to_timestamp(file.last_modified)  # type: ignore[arg-type]
        if file.last_modified
        else 0
    )

    if existing:
        driver.update(
            "cst_trees",
            where={"id": existing[0]["id"]},
            data={
                "cst_code": cst_code,
                "file_mtime": file_mtime,
            },
        )
    else:
        driver.insert(
            "cst_trees",
            data={
                "file_id": file_id,
                "project_id": file.project_id,
                "cst_code": cst_code,
                "cst_hash": cst_hash,
                "file_mtime": file_mtime,
            },
        )

    return True
