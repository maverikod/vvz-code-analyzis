"""
Smoke test for semantic search functionality.

Quick test to verify basic functionality works.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from code_analysis.commands.semantic_search import SemanticSearchCommand
from code_analysis.core.database import CodeDatabase


async def smoke_test():
    """Quick smoke test for semantic search."""
    print("=" * 60)
    print("SMOKE TEST: Semantic Search")
    print("=" * 60)
    
    # Test 1: Import and initialization
    print("\n[1] Testing import and initialization...")
    try:
        from code_analysis.commands.semantic_search import SemanticSearchCommand
        print("✓ Import successful")
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False
    
    # Test 2: Check if FAISS manager is required
    print("\n[2] Testing error handling (no FAISS manager)...")
    try:
        db_path = project_root / "data" / "code_analysis.db"
        if not db_path.exists():
            print("⚠ Database not found, skipping database tests")
            return True
        
        database = CodeDatabase(db_path)
        project_id = database.get_or_create_project(str(project_root), name="test")
        
        cmd = SemanticSearchCommand(
            database=database,
            project_id=project_id,
            faiss_manager=None,
            svo_client_manager=None,
        )
        
        try:
            await cmd.search("test query", k=5)
            print("✗ Should have raised RuntimeError")
            return False
        except RuntimeError as e:
            if "FAISS manager" in str(e):
                print("✓ Correctly raises RuntimeError when FAISS manager is missing")
            else:
                print(f"✗ Wrong error: {e}")
                return False
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            return False
        finally:
            database.close()
    except Exception as e:
        print(f"⚠ Error during test: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("SMOKE TEST: PASSED")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(smoke_test())
    sys.exit(0 if success else 1)

