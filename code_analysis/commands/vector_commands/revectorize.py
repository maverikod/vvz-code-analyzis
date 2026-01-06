"""
MCP command for revectorizing chunks.

Implements dataset-scoped FAISS (Step 2 of refactor plan).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand
from ...core.faiss_manager import FaissIndexManager
from ...core.storage_paths import resolve_storage_paths, get_faiss_index_path
from ...core.project_resolution import normalize_root_dir

logger = logging.getLogger(__name__)


class RevectorizeCommand(BaseMCPCommand):
    """
    Revectorize chunks (regenerate embeddings and update FAISS index).

    Implements dataset-scoped FAISS (Step 2 of refactor plan).
    Revectorizes chunks for a specific dataset or all datasets in a project.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Human readable description.
        category: Command category.
        author: Author name.
        email: Author email.
        use_queue: Whether command runs via queue.
    """

    name = "revectorize"
    version = "1.0.0"
    descr = "Revectorize chunks (regenerate embeddings and update FAISS index)"
    category = "vectorization"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["RevectorizeCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema describing command parameters.
        """
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains projectid file)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (must match root_dir/projectid)",
                },
                "dataset_id": {
                    "type": "string",
                    "description": "Optional dataset UUID; if omitted, revectorizes all datasets in project",
                },
                "force": {
                    "type": "boolean",
                    "description": "Force revectorization even if embeddings exist (default: false)",
                    "default": False,
                },
            },
            "required": ["root_dir", "project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self: "RevectorizeCommand",
        root_dir: str,
        project_id: str,
        dataset_id: Optional[str] = None,
        force: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute chunk revectorization.

        Args:
            self: Command instance.
            root_dir: Root directory of the project.
            project_id: Project UUID (must match root_dir/projectid).
            dataset_id: Optional dataset UUID; if omitted, revectorizes all datasets.
            force: Force revectorization even if embeddings exist.

        Returns:
            SuccessResult with revectorization statistics or ErrorResult on failure.
        """
        try:
            root_path = normalize_root_dir(root_dir)

            # Validate project_id matches root_dir/projectid
            self._require_project_id_gate(root_dir, project_id)

            database = self._open_database(root_dir)
            try:
                actual_project_id = self._get_project_id(database, root_path, project_id)
                if not actual_project_id:
                    return ErrorResult(
                        message=f"Project not found: {project_id}",
                        code="PROJECT_NOT_FOUND",
                    )

                # Resolve storage paths
                config_path = root_path / "config.json"
                if not config_path.exists():
                    return ErrorResult(
                        message=f"Configuration file not found: {config_path}",
                        code="CONFIG_NOT_FOUND",
                    )

                import json

                with open(config_path, "r", encoding="utf-8") as f:
                    config_dict = json.load(f)

                storage_paths = resolve_storage_paths(
                    config_data=config_dict, config_path=config_path
                )

                # Get vector dimension
                code_analysis_config = config_dict.get("code_analysis", config_dict)
                vector_dim = int(code_analysis_config.get("vector_dim", 384))

                # Initialize SVO client manager
                from ...core.svo_client_manager import SVOClientManager

                svo_client_manager = SVOClientManager(config_dict, root_dir=root_path)
                await svo_client_manager.initialize()

                try:
                    results = []

                    if dataset_id:
                        # Revectorize chunks for specific dataset
                        normalized_root = str(normalize_root_dir(root_dir))
                        db_dataset_id = database.get_dataset_id(actual_project_id, normalized_root)
                        if not db_dataset_id:
                            # Create dataset if it doesn't exist
                            db_dataset_id = database.get_or_create_dataset(
                                actual_project_id, normalized_root
                            )

                        if db_dataset_id != dataset_id:
                            return ErrorResult(
                                message=f"Dataset ID mismatch: provided {dataset_id}, found {db_dataset_id}",
                                code="DATASET_ID_MISMATCH",
                            )

                        result = await self._revectorize_dataset(
                            database,
                            svo_client_manager,
                            storage_paths,
                            actual_project_id,
                            dataset_id,
                            vector_dim,
                            force,
                        )
                        results.append(result)
                    else:
                        # Revectorize chunks for all datasets in project
                        datasets = database.get_project_datasets(actual_project_id)
                        if not datasets:
                            return ErrorResult(
                                message=f"No datasets found for project {actual_project_id}",
                                code="NO_DATASETS",
                            )

                        for dataset in datasets:
                            ds_id = dataset["id"]
                            result = await self._revectorize_dataset(
                                database,
                                svo_client_manager,
                                storage_paths,
                                actual_project_id,
                                ds_id,
                                vector_dim,
                                force,
                            )
                            results.append(result)

                    total_chunks = sum(r["chunks_revectorized"] for r in results)

                    return SuccessResult(
                        data={
                            "project_id": actual_project_id,
                            "datasets_processed": len(results),
                            "total_chunks_revectorized": total_chunks,
                            "results": results,
                        }
                    )
                finally:
                    await svo_client_manager.close()
            finally:
                database.close()

        except Exception as e:
            logger.error(f"Failed to revectorize chunks: {e}", exc_info=True)
            return self._handle_error(e, "REVECTORIZE_ERROR", "revectorize")

    async def _revectorize_dataset(
        self,
        database: Any,
        svo_client_manager: Any,
        storage_paths: Any,
        project_id: str,
        dataset_id: str,
        vector_dim: int,
        force: bool,
    ) -> Dict[str, Any]:
        """Revectorize chunks for a specific dataset.

        Args:
            database: CodeDatabase instance.
            svo_client_manager: SVOClientManager instance.
            storage_paths: StoragePaths instance.
            project_id: Project UUID.
            dataset_id: Dataset UUID.
            vector_dim: Vector dimension.
            force: Force revectorization even if embeddings exist.

        Returns:
            Dictionary with revectorization statistics.
        """
        # Get dataset-scoped FAISS index path
        index_path = get_faiss_index_path(
            storage_paths.faiss_dir, project_id, dataset_id
        )

        # Initialize FAISS manager
        faiss_manager = FaissIndexManager(
            index_path=str(index_path),
            vector_dim=vector_dim,
        )

        try:
            # Get chunks for this dataset that need revectorization
            # If force=True, get all chunks; otherwise get only chunks without embeddings
            if force:
                # Get all chunks for this dataset
                chunks = database.get_all_chunks_for_faiss_rebuild(
                    project_id=project_id, dataset_id=dataset_id
                )
            else:
                # Get only chunks without embeddings
                # This is a simplified version - in production, you might want a more sophisticated query
                chunks = database.get_all_chunks_for_faiss_rebuild(
                    project_id=project_id, dataset_id=dataset_id
                )
                # Filter chunks without embeddings
                chunks = [
                    c
                    for c in chunks
                    if not c.get("embedding_vector") or not c.get("embedding_model")
                ]

            if not chunks:
                return {
                    "dataset_id": dataset_id,
                    "chunks_revectorized": 0,
                    "index_path": str(index_path),
                }

            # Revectorize chunks and update FAISS index
            revectorized_count = 0
            for chunk in chunks:
                chunk_id = chunk.get("id")
                chunk_text = chunk.get("chunk_text", "")

                if not chunk_text:
                    continue

                try:
                    # Get new embedding from SVO service
                    class _TmpChunk:
                        def __init__(self, text: str):
                            self.body = text
                            self.text = text

                    tmp = _TmpChunk(chunk_text)
                    chunks_with_emb = await svo_client_manager.get_embeddings([tmp])
                    if chunks_with_emb and hasattr(chunks_with_emb[0], "embedding"):
                        embedding = getattr(chunks_with_emb[0], "embedding")
                        embedding_model = getattr(
                            chunks_with_emb[0], "embedding_model", None
                        )

                        if embedding is not None:
                            import json
                            import numpy as np

                            embedding_array = np.array(embedding, dtype="float32")
                            embedding_json = json.dumps(embedding_array.tolist())

                            # Update database with new embedding
                            database._execute(
                                """
                                UPDATE code_chunks
                                SET embedding_vector = ?, embedding_model = ?, vector_id = NULL
                                WHERE id = ?
                                """,
                                (embedding_json, embedding_model, chunk_id),
                            )
                            database._commit()

                            revectorized_count += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to revectorize chunk {chunk_id}: {e}", exc_info=True
                    )

            # Rebuild FAISS index for this dataset
            vectors_count = await faiss_manager.rebuild_from_database(
                database,
                svo_client_manager,
                project_id=project_id,
                dataset_id=dataset_id,
            )

            return {
                "dataset_id": dataset_id,
                "chunks_revectorized": revectorized_count,
                "vectors_in_index": vectors_count,
                "index_path": str(index_path),
            }
        finally:
            faiss_manager.close()

