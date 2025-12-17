"""
Test chunk_text on embedding service.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from svo_client import ChunkerClient


async def test():
    """Test chunk_text on embedding service."""
    print("=" * 80)
    print("TESTING CHUNK_TEXT ON EMBEDDING SERVICE")
    print("=" * 80)
    
    client = ChunkerClient(
        host="localhost",
        port=8001,
        cert="mtls_certificates/client/embedding-service.crt",
        key="mtls_certificates/client/embedding-service.key",
        ca="mtls_certificates/ca/ca.crt",
        check_hostname=False,
        timeout=300.0,
    )
    
    try:
        test_text = "This is a test document for getting embeddings. The embedding service should return chunks with vectors and bm25 scores."
        
        print(f"\nInput text: {test_text[:100]}...")
        print(f"Text length: {len(test_text)} characters")
        
        print("\nCalling chunk_text on embedding service...")
        chunks = await client.chunk_text(
            test_text,
            type="DocBlock",
            language="en",
        )
        
        print(f"\n✅ Success! Received {len(chunks)} chunks")
        
        for i, chunk in enumerate(chunks[:3], 1):
            chunk_text = getattr(chunk, "text", "") or getattr(chunk, "body", "")
            print(f"\nChunk {i}:")
            print(f"  Text: {chunk_text[:80]}...")
            
            # Check for embedding
            if hasattr(chunk, "embedding"):
                emb = getattr(chunk, "embedding", None)
                print(f"  Has embedding: {emb is not None}")
                if emb:
                    print(f"  Embedding length: {len(emb)}")
            
            # Check for bm25
            if hasattr(chunk, "bm25"):
                bm25 = getattr(chunk, "bm25", None)
                print(f"  Has bm25: {bm25 is not None}")
                if bm25:
                    print(f"  BM25: {bm25}")
        
        await client.close()
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.close()


if __name__ == "__main__":
    result = asyncio.run(test())
    sys.exit(0 if result else 1)


