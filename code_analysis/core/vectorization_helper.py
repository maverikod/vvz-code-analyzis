"""
Helper functions for immediate vectorization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Optional, Any, Dict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def get_svo_client_manager(
    config: Optional[Dict[str, Any]] = None,
    root_dir: Optional[Path] = None,
) -> Optional[Any]:
    """
    Get SVO client manager from config.

    Args:
        config: Configuration dictionary (full config or code_analysis section)
        root_dir: Optional root directory path for resolving relative certificate paths

    Returns:
        SVOClientManager instance or None if not available

    Note:
        This function creates a new SVOClientManager instance. The caller is responsible
        for initializing and closing it properly.
    """
    if not config:
        logger.debug("No config provided for SVO client manager")
        return None

    try:
        from .svo_client_manager import SVOClientManager

        manager = SVOClientManager(config, root_dir=root_dir)
        return manager
    except (ImportError, AttributeError, Exception) as e:
        logger.debug(f"SVO client manager not available: {e}")
        return None


def get_faiss_manager(
    index_path: Optional[Path] = None,
    vector_dim: Optional[int] = None,
) -> Optional[Any]:
    """
    Get FAISS manager from index path and vector dimension.

    Args:
        index_path: Path to FAISS index file
        vector_dim: Vector dimension (default: 384)

    Returns:
        FaissIndexManager instance or None if not available

    Note:
        This function creates a new FaissIndexManager instance. The caller is responsible
        for loading the index if needed.
    """
    if not index_path:
        logger.debug("No index path provided for FAISS manager")
        return None

    try:
        from .faiss_manager import FaissIndexManager

        if vector_dim is None:
            vector_dim = 384  # Default vector dimension

        manager = FaissIndexManager(
            index_path=str(index_path),
            vector_dim=vector_dim,
        )
        return manager
    except (ImportError, AttributeError, Exception) as e:
        logger.debug(f"FAISS manager not available: {e}")
        return None


def get_managers_from_config(
    config: Dict[str, Any],
    root_dir: Path,
    project_id: str,
) -> Dict[str, Optional[Any]]:
    """
    Get both SVO and FAISS managers from config.

    One FAISS index per project: {faiss_dir}/{project_id}.bin.

    Args:
        config: Full configuration dictionary
        root_dir: Root directory path
        project_id: Project ID

    Returns:
        Dictionary with keys:
            - svo_client_manager: SVOClientManager instance or None
            - faiss_manager: FaissIndexManager instance or None
            - vector_dim: Vector dimension from config
    """
    from .storage_paths import resolve_storage_paths, get_faiss_index_path

    result = {
        "svo_client_manager": None,
        "faiss_manager": None,
        "vector_dim": 384,
    }

    # Get vector dimension
    code_analysis_config = config.get("code_analysis", config)
    vector_dim = int(code_analysis_config.get("vector_dim", 384))
    result["vector_dim"] = vector_dim

    # Get SVO client manager
    try:
        result["svo_client_manager"] = get_svo_client_manager(config, root_dir)
    except Exception as e:
        logger.warning(f"Failed to create SVO client manager: {e}")

    # Get FAISS manager
    try:
        config_path = root_dir / "config.json"
        storage_paths = resolve_storage_paths(
            config_data=config, config_path=config_path
        )
        index_path = get_faiss_index_path(storage_paths.faiss_dir, project_id)
        if index_path.exists():
            result["faiss_manager"] = get_faiss_manager(
                index_path=index_path, vector_dim=vector_dim
            )
    except Exception as e:
        logger.warning(f"Failed to create FAISS manager: {e}")

    return result
