"""
Simple test script for SVO clients (chunker and embedding).

Tests basic functionality of ChunkerClient with mTLS.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from svo_client import ChunkerClient


async def test_chunker_client():
    """Test chunker client."""
    print("=" * 80)
    print("TESTING CHUNKER CLIENT")
    print("=" * 80)

    client = ChunkerClient(
        host="localhost",
        port=8009,
        cert="mtls_certificates/client/svo-chunker.crt",
        key="mtls_certificates/client/svo-chunker.key",
        ca="mtls_certificates/ca/ca.crt",
        check_hostname=False,
        timeout=300.0,  # 5 minutes timeout for chunking
    )

    try:
        # Test text for chunking
        test_text = """
        This is a test document for chunking.
        It contains multiple sentences and paragraphs.
        We want to see how the chunker service processes this text.
        The chunker should split it into semantic chunks.
        """

        print(f"\nInput text length: {len(test_text)} characters")
        print(f"Text preview: {test_text[:100]}...")

        print("\nCalling chunk_text...")
        chunks = await client.chunk_text(test_text)

        print(f"\n✅ Success! Received {len(chunks)} chunks")

        for i, chunk in enumerate(chunks[:3], 1):  # Show first 3 chunks
            chunk_text = getattr(chunk, "text", "") or getattr(chunk, "body", "")
            print(f"\nChunk {i}:")
            print(f"  Type: {type(chunk)}")
            print(f"  Text length: {len(chunk_text)}")
            print(f"  Preview: {chunk_text[:80]}...")
            if hasattr(chunk, "embedding"):
                emb = getattr(chunk, "embedding", None)
                print(f"  Has embedding: {emb is not None}")
                if emb:
                    print(f"  Embedding length: {len(emb)}")

        await client.close()
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_embedding_client():
    """Test embedding client."""
    print("\n" + "=" * 80)
    print("TESTING EMBEDDING CLIENT")
    print("=" * 80)

    client = ChunkerClient(
        host="localhost",
        port=8001,
        cert="mtls_certificates/client/embedding-service.crt",
        key="mtls_certificates/client/embedding-service.key",
        ca="mtls_certificates/ca/ca.crt",
        check_hostname=False,
        timeout=300.0,  # 5 minutes timeout
    )

    try:
        # Test text for embedding
        test_text = """
        This is a test document for getting embeddings.
        The embedding service should return chunks with vectors.
        It may also include bm25 scores and other metadata.
        """

        print(f"\nInput text length: {len(test_text)} characters")
        print(f"Text preview: {test_text[:100]}...")

        print("\nCalling chunk_text (should return chunks with embeddings, bm25)...")
        chunks = await client.chunk_text(test_text, type="DocBlock", language="en")

        print(f"\n✅ Success! Received {len(chunks)} chunks")

        for i, chunk in enumerate(chunks[:3], 1):  # Show first 3 chunks
            chunk_text = getattr(chunk, "text", "") or getattr(chunk, "body", "")
            print(f"\nChunk {i}:")
            print(f"  Type: {type(chunk)}")
            print(f"  Text length: {len(chunk_text)}")
            print(f"  Preview: {chunk_text[:80]}...")

            # Check for embedding
            if hasattr(chunk, "embedding"):
                emb = getattr(chunk, "embedding", None)
                print(f"  Has embedding: {emb is not None}")
                if emb:
                    print(f"  Embedding length: {len(emb)}")
                    print(f"  Embedding preview: {emb[:5] if len(emb) > 5 else emb}...")

            # Check for bm25
            if hasattr(chunk, "bm25"):
                bm25 = getattr(chunk, "bm25", None)
                print(f"  Has bm25: {bm25 is not None}")
                if bm25:
                    print(f"  BM25 value: {bm25}")

        await client.close()
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Main test function."""
    print("\n" + "=" * 80)
    print("SIMPLE SVO CLIENTS TEST")
    print("=" * 80)

    # Test chunker
    chunker_ok = await test_chunker_client()

    # Test embedding
    embedding_ok = await test_embedding_client()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Chunker client: {'✅ OK' if chunker_ok else '❌ FAILED'}")
    print(f"Embedding client: {'✅ OK' if embedding_ok else '❌ FAILED'}")

    if chunker_ok and embedding_ok:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
