"""
MCP command for rebuilding FAISS index.

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


class RebuildFaissCommand(BaseMCPCommand):
    """
    Rebuild FAISS index from database.

    Implements dataset-scoped FAISS (Step 2 of refactor plan).
    Rebuilds FAISS index for a specific dataset or all datasets in a project.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Human readable description.
        category: Command category.
        author: Author name.
        email: Author email.
        use_queue: Whether command runs via queue.
    """

    name = "rebuild_faiss"
    version = "1.0.0"
    descr = "Rebuild FAISS index from database (dataset-scoped)"
    category = "vectorization"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["RebuildFaissCommand"]) -> Dict[str, Any]:
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
                    "description": "Optional dataset UUID; if omitted, rebuilds all datasets in project",
                },
            },
            "required": ["root_dir", "project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self: "RebuildFaissCommand",
        root_dir: str,
        project_id: str,
        dataset_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute FAISS index rebuild.

        Args:
            self: Command instance.
            root_dir: Root directory of the project.
            project_id: Project UUID (must match root_dir/projectid).
            dataset_id: Optional dataset UUID; if omitted, rebuilds all datasets.

        Returns:
            SuccessResult with rebuild statistics or ErrorResult on failure.
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
                        # Rebuild index for specific dataset
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

                        # Get dataset-scoped FAISS index path
                        index_path = get_faiss_index_path(
                            storage_paths.faiss_dir, actual_project_id, dataset_id
                        )

                        # Initialize FAISS manager
                        faiss_manager = FaissIndexManager(
                            index_path=str(index_path),
                            vector_dim=vector_dim,
                        )

                        # Rebuild index
                        vectors_count = await faiss_manager.rebuild_from_database(
                            database,
                            svo_client_manager,
                            project_id=actual_project_id,
                            dataset_id=dataset_id,
                        )

                        results.append(
                            {
                                "dataset_id": dataset_id,
                                "index_path": str(index_path),
                                "vectors_count": vectors_count,
                            }
                        )

                        faiss_manager.close()
                    else:
                        # Rebuild indexes for all datasets in project
                        datasets = database.get_project_datasets(actual_project_id)
                        if not datasets:
                            return ErrorResult(
                                message=f"No datasets found for project {actual_project_id}",
                                code="NO_DATASETS",
                            )

                        for dataset in datasets:
                            ds_id = dataset["id"]
                            ds_root = dataset["root_path"]

                            # Get dataset-scoped FAISS index path
                            index_path = get_faiss_index_path(
                                storage_paths.faiss_dir, actual_project_id, ds_id
                            )

                            # Initialize FAISS manager
                            faiss_manager = FaissIndexManager(
                                index_path=str(index_path),
                                vector_dim=vector_dim,
                            )

                            # Rebuild index
                            vectors_count = await faiss_manager.rebuild_from_database(
                                database,
                                svo_client_manager,
                                project_id=actual_project_id,
                                dataset_id=ds_id,
                            )

                            results.append(
                                {
                                    "dataset_id": ds_id,
                                    "root_path": ds_root,
                                    "index_path": str(index_path),
                                    "vectors_count": vectors_count,
                                }
                            )

                            faiss_manager.close()

                    total_vectors = sum(r["vectors_count"] for r in results)

                    return SuccessResult(
                        data={
                            "project_id": actual_project_id,
                            "datasets_rebuilt": len(results),
                            "total_vectors": total_vectors,
                            "results": results,
                        }
                    )
                finally:
                    await svo_client_manager.close()
            finally:
                database.close()

        except Exception as e:
            logger.error(f"Failed to rebuild FAISS index: {e}", exc_info=True)
            return self._handle_error(e, "REBUILD_FAISS_ERROR", "rebuild_faiss")

