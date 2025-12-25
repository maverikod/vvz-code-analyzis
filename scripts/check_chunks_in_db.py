"""
Check chunks and vectors in database.

This script checks if chunks with embeddings exist in the database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from code_analysis.core.database import CodeDatabase

# Database path
DB_PATH = project_root / "data" / "code_analysis.db"


def main():
    """Check chunks in database."""
    print("=" * 80)
    print("CHECKING CHUNKS IN DATABASE")
    print("=" * 80)
    print()

    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        sys.exit(1)

    print(f"Database: {DB_PATH}")
    print()

    database = CodeDatabase(DB_PATH)

    try:
        # Check total chunks
        assert database.conn is not None
        cursor = database.conn.cursor()

        # Total chunks
        cursor.execute("SELECT COUNT(*) FROM code_chunks")
        total_chunks = cursor.fetchone()[0]
        print(f"Total chunks: {total_chunks}")

        # Chunks with vector_id
        cursor.execute("SELECT COUNT(*) FROM code_chunks WHERE vector_id IS NOT NULL")
        chunks_with_vector = cursor.fetchone()[0]
        print(f"Chunks with vector_id: {chunks_with_vector}")

        # Chunks with embedding_model
        cursor.execute(
            "SELECT COUNT(*) FROM code_chunks WHERE embedding_model IS NOT NULL"
        )
        chunks_with_model = cursor.fetchone()[0]
        print(f"Chunks with embedding_model: {chunks_with_model}")

        # Sample chunks
        cursor.execute(
            """
            SELECT id, chunk_type, chunk_text, vector_id, embedding_model
            FROM code_chunks
            LIMIT 5
            """
        )
        samples = cursor.fetchall()
        print()
        print("Sample chunks (first 5):")
        for i, (
            chunk_id,
            chunk_type,
            chunk_text,
            vector_id,
            embedding_model,
        ) in enumerate(samples, 1):
            print(f"  {i}. ID={chunk_id}, Type={chunk_type}")
            print(f"     Vector ID: {vector_id}, Model: {embedding_model}")
            if chunk_text:
                preview = (
                    chunk_text[:100] + "..." if len(chunk_text) > 100 else chunk_text
                )
                print(f"     Text: {preview}")
            print()

        # Check FAISS index stats if available
        try:
            from code_analysis.core.faiss_manager import FaissIndexManager
            from code_analysis.core.config_manager import ConfigManager

            config_manager = ConfigManager(project_root / "config.json")
            config = config_manager.read()

            if config.faiss_index_path and config.vector_dim:
                faiss_path = Path(config.faiss_index_path)
                if faiss_path.is_absolute():
                    index_path = faiss_path
                else:
                    index_path = project_root / faiss_path

                if index_path.exists():
                    print(f"FAISS index: {index_path}")
                    manager = FaissIndexManager(
                        index_path=index_path, vector_dim=config.vector_dim
                    )
                    stats = manager.get_stats()
                    print(f"  Vectors in index: {stats.get('vector_count', 0)}")
                    print(f"  Vector dimension: {stats.get('vector_dim', 0)}")
                    manager.close()
                else:
                    print(f"FAISS index not found: {index_path}")
            else:
                print("FAISS not configured in config.json")
        except Exception as e:
            print(f"Could not check FAISS index: {e}")
    finally:
        database.close()

    print("=" * 80)


if __name__ == "__main__":
    main()
