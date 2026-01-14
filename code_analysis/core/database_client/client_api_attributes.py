"""
Attribute operations API methods for database client.

Provides object-oriented API methods for AST, CST, and vector operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from .objects.base import BaseObject
from .objects.file import File


class _ClientAPIAttributesMixin:
    """Mixin class with attribute operation methods."""

    def save_ast(self, file_id: int, ast_data: Dict[str, Any]) -> bool:
        """Save AST tree for file.

        Args:
            file_id: File identifier
            ast_data: AST tree data as dictionary

        Returns:
            True if AST was saved successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If file not found
        """
        # Get file to get project_id
        file = self.get_file(file_id)
        if file is None:
            raise ValueError(f"File {file_id} not found")

        # Convert AST data to JSON string
        ast_json = json.dumps(ast_data)

        # Calculate hash
        ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()

        # Check if AST already exists
        existing = self.select(
            "ast_trees",
            where={"file_id": file_id, "ast_hash": ast_hash},
        )

        # Convert file_mtime to Julian day format
        file_mtime = (
            BaseObject._to_timestamp(file.last_modified) if file.last_modified else 0
        )

        if existing:
            # Update existing AST
            self.update(
                "ast_trees",
                where={"id": existing[0]["id"]},
                data={
                    "ast_json": ast_json,
                    "file_mtime": file_mtime,
                },
            )
        else:
            # Insert new AST
            self.insert(
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

    def get_ast(self, file_id: int) -> Optional[Dict[str, Any]]:
        """Get AST tree for file.

        Args:
            file_id: File identifier

        Returns:
            AST tree data as dictionary or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select(
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
            return json.loads(ast_json)
        except (json.JSONDecodeError, TypeError):
            return None

    def save_cst(self, file_id: int, cst_code: str) -> bool:
        """Save CST tree (source code) for file.

        Args:
            file_id: File identifier
            cst_code: CST tree as source code string

        Returns:
            True if CST was saved successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If file not found
        """
        # Get file to get project_id
        file = self.get_file(file_id)
        if file is None:
            raise ValueError(f"File {file_id} not found")

        # Calculate hash
        cst_hash = hashlib.sha256(cst_code.encode()).hexdigest()

        # Check if CST already exists
        existing = self.select(
            "cst_trees",
            where={"file_id": file_id, "cst_hash": cst_hash},
        )

        # Convert file_mtime to Julian day format
        file_mtime = (
            BaseObject._to_timestamp(file.last_modified) if file.last_modified else 0
        )

        if existing:
            # Update existing CST
            self.update(
                "cst_trees",
                where={"id": existing[0]["id"]},
                data={
                    "cst_code": cst_code,
                    "file_mtime": file_mtime,
                },
            )
        else:
            # Insert new CST
            self.insert(
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

    def get_cst(self, file_id: int) -> Optional[str]:
        """Get CST tree (source code) for file.

        Args:
            file_id: File identifier

        Returns:
            CST tree as source code string or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select(
            "cst_trees",
            where={"file_id": file_id},
            order_by=["updated_at"],
            limit=1,
        )
        if not rows:
            return None

        return rows[0].get("cst_code")

    def save_vectors(
        self, file_id: int, vectors: List[Dict[str, Any]]
    ) -> bool:
        """Save vector indices for file.

        Args:
            file_id: File identifier
            vectors: List of vector index dictionaries with keys:
                - entity_type: Entity type (file, chunk, class, function, method)
                - entity_id: Entity identifier
                - vector_id: Vector identifier in FAISS index
                - vector_dim: Vector dimension
                - embedding_model: Embedding model used (optional)

        Returns:
            True if vectors were saved successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If file not found
        """
        # Get file to get project_id
        file = self.get_file(file_id)
        if file is None:
            raise ValueError(f"File {file_id} not found")

        # Save each vector
        for vector_data in vectors:
            # Check if vector already exists
            existing = self.select(
                "vector_index",
                where={
                    "project_id": file.project_id,
                    "entity_type": vector_data["entity_type"],
                    "entity_id": vector_data["entity_id"],
                },
            )

            vector_row = {
                "project_id": file.project_id,
                "entity_type": vector_data["entity_type"],
                "entity_id": vector_data["entity_id"],
                "vector_id": vector_data["vector_id"],
                "vector_dim": vector_data["vector_dim"],
            }
            if "embedding_model" in vector_data:
                vector_row["embedding_model"] = vector_data["embedding_model"]

            if existing:
                # Update existing vector
                self.update(
                    "vector_index",
                    where={
                        "project_id": file.project_id,
                        "entity_type": vector_data["entity_type"],
                        "entity_id": vector_data["entity_id"],
                    },
                    data=vector_row,
                )
            else:
                # Insert new vector
                self.insert("vector_index", data=vector_row)

        return True

    def get_vectors(self, file_id: int) -> List[Dict[str, Any]]:
        """Get vector indices for file.

        Args:
            file_id: File identifier

        Returns:
            List of vector index dictionaries

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If file not found
        """
        # Get file to get project_id
        file = self.get_file(file_id)
        if file is None:
            raise ValueError(f"File {file_id} not found")

        # Get vectors for file entity
        rows = self.select(
            "vector_index",
            where={
                "project_id": file.project_id,
                "entity_type": "file",
                "entity_id": file_id,
            },
        )

        return rows
