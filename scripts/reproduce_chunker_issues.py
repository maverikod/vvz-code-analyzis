"""
Script to reproduce all chunker client issues.

Tests:
1. Chunker connection with mTLS
2. Chunking text with different lengths
3. Getting embeddings from chunks
4. Processing empty chunks (chunks without embeddings)

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

from svo_client import ChunkerClient
from svo_client.errors import (
    SVOServerError,
    SVOConnectionError,
    SVOTimeoutError,
    SVOChunkingIntegrityError,
)


class ChunkerTester:
    """Test chunker client functionality."""

    def __init__(self, config_path: str = "config.json"):
        """Initialize tester with config."""
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.client: Optional[ChunkerClient] = None
        self.results: Dict[str, Any] = {}

    def load_config(self) -> None:
        """Load configuration from config.json."""
        if not self.config_path.exists():
            print(f"❌ Config file not found: {self.config_path}")
            sys.exit(1)

        with open(self.config_path, "r", encoding="utf-8") as f:
            full_config = json.load(f)

        ca_cfg = full_config.get("code_analysis", {})
        chunker_cfg = ca_cfg.get("chunker", {})

        if not chunker_cfg.get("enabled"):
            print("❌ Chunker is not enabled in config")
            sys.exit(1)

        self.config = chunker_cfg
        print(f"✅ Loaded config: {chunker_cfg.get('url')}:{chunker_cfg.get('port')}")

    def create_client(self) -> None:
        """Create ChunkerClient with mTLS support."""
        try:
            # New ChunkerClient API: host, port, cert, key, ca
            client_kwargs = {
                "host": self.config.get("url", "localhost"),
                "port": self.config.get("port", 8009),
                "check_hostname": False,
            }

            # Add mTLS certificates only if protocol is explicitly mtls or https
            # IMPORTANT: Do NOT pass certificates for HTTP protocol
            protocol = self.config.get("protocol", "http")
            if protocol in ("https", "mtls"):
                cert_file = self.config.get("cert_file")
                key_file = self.config.get("key_file")
                ca_cert_file = self.config.get("ca_cert_file")

                if cert_file and key_file and ca_cert_file:
                    # Resolve paths
                    cert_path = Path(cert_file)
                    key_path = Path(key_file)
                    ca_path = Path(ca_cert_file)

                    if not cert_path.is_absolute():
                        cert_path = self.config_path.parent / cert_path
                    if not key_path.is_absolute():
                        key_path = self.config_path.parent / key_path
                    if not ca_path.is_absolute():
                        ca_path = self.config_path.parent / ca_path

                    client_kwargs["cert"] = str(cert_path.resolve())
                    client_kwargs["key"] = str(key_path.resolve())
                    client_kwargs["ca"] = str(ca_path.resolve())

                    print(f"✅ mTLS configured: cert={client_kwargs['cert']}")
                else:
                    print("⚠️  mTLS protocol but certificates not provided, falling back to HTTP")
            else:
                print("✅ Using HTTP protocol (no certificates)")

            # Add timeout if configured
            timeout = self.config.get("timeout")
            if timeout:
                client_kwargs["timeout"] = float(timeout)

            self.client = ChunkerClient(**client_kwargs)
            print(f"✅ ChunkerClient created: {client_kwargs['host']}:{client_kwargs['port']}")

        except Exception as e:
            print(f"❌ Failed to create client: {e}")
            raise

    async def test_health(self) -> bool:
        """Test health check."""
        print("\n🔍 Test 1: Health Check")
        try:
            result = await self.client.health()
            print(f"✅ Health check passed: {result}")
            self.results["health"] = {"status": "ok", "result": result}
            return True
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            self.results["health"] = {"status": "error", "error": str(e), "type": type(e).__name__}
            return False

    async def test_chunking_short(self) -> bool:
        """Test chunking short text (< 30 chars)."""
        print("\n🔍 Test 2: Chunking Short Text (< 30 chars)")
        text = "Short docstring."
        try:
            result = await self.client.chunk_text(text, type="DocBlock")
            if result and len(result) > 0:
                chunk = result[0]
                has_emb = hasattr(chunk, "embedding") and getattr(chunk, "embedding", None) is not None
                has_bm25 = hasattr(chunk, "bm25") and getattr(chunk, "bm25", None) is not None
                print(f"✅ Short text chunked: {len(result)} chunks, has_embedding={has_emb}, has_bm25={has_bm25}")
                self.results["chunking_short"] = {
                    "status": "ok",
                    "chunks": len(result),
                    "has_embedding": has_emb,
                    "has_bm25": has_bm25,
                }
                return True
            else:
                print(f"❌ Short text returned empty result")
                self.results["chunking_short"] = {"status": "error", "error": "empty_result"}
                return False
        except Exception as e:
            print(f"❌ Short text chunking failed: {e}")
            self.results["chunking_short"] = {"status": "error", "error": str(e), "type": type(e).__name__}
            return False

    async def test_chunking_medium(self) -> bool:
        """Test chunking medium text (30-200 chars)."""
        print("\n🔍 Test 3: Chunking Medium Text (30-200 chars)")
        text = "Manage FAISS index: add vectors, search, rebuild from DB. Provides efficient similarity search."
        try:
            result = await self.client.chunk_text(text, type="DocBlock")
            if result and len(result) > 0:
                chunk = result[0]
                has_emb = hasattr(chunk, "embedding") and getattr(chunk, "embedding", None) is not None
                has_bm25 = hasattr(chunk, "bm25") and getattr(chunk, "bm25", None) is not None
                print(f"✅ Medium text chunked: {len(result)} chunks, has_embedding={has_emb}, has_bm25={has_bm25}")
                self.results["chunking_medium"] = {
                    "status": "ok",
                    "chunks": len(result),
                    "has_embedding": has_emb,
                    "has_bm25": has_bm25,
                }
                return True
            else:
                print(f"❌ Medium text returned empty result")
                self.results["chunking_medium"] = {"status": "error", "error": "empty_result"}
                return False
        except Exception as e:
            print(f"❌ Medium text chunking failed: {e}")
            self.results["chunking_medium"] = {"status": "error", "error": str(e), "type": type(e).__name__}
            return False

    async def test_chunking_long(self) -> bool:
        """Test chunking long text (> 200 chars)."""
        print("\n🔍 Test 4: Chunking Long Text (> 200 chars)")
        text = """Analyze Python codebase and generate comprehensive reports.

This tool analyzes Python code and generates:
- Code map with classes, functions, and dependencies
- Issue reports with code quality problems
- Method index for easy navigation
- AST-based code structure analysis
- Semantic search capabilities using FAISS

The analysis process includes:
1. Parsing Python files into AST
2. Extracting docstrings and comments
3. Chunking and vectorizing documentation
4. Building searchable indexes"""
        try:
            result = await self.client.chunk_text(text, type="DocBlock")
            if result and len(result) > 0:
                chunks_with_emb = sum(1 for c in result if hasattr(c, "embedding") and getattr(c, "embedding", None) is not None)
                chunks_with_bm25 = sum(1 for c in result if hasattr(c, "bm25") and getattr(c, "bm25", None) is not None)
                print(f"✅ Long text chunked: {len(result)} chunks, {chunks_with_emb} with embeddings, {chunks_with_bm25} with bm25")
                self.results["chunking_long"] = {
                    "status": "ok",
                    "chunks": len(result),
                    "chunks_with_embedding": chunks_with_emb,
                    "chunks_with_bm25": chunks_with_bm25,
                }
                return True
            else:
                print(f"❌ Long text returned empty result")
                self.results["chunking_long"] = {"status": "error", "error": "empty_result"}
                return False
        except Exception as e:
            print(f"❌ Long text chunking failed: {e}")
            self.results["chunking_long"] = {"status": "error", "error": str(e), "type": type(e).__name__}
            return False

    async def test_embeddings(self) -> bool:
        """Test getting embeddings from chunks."""
        print("\n🔍 Test 5: Getting Embeddings")
        text = "Vectorization worker for processing chunks in background. Processes chunks that don't have vector_id, gets embeddings, adds them to FAISS, updates DB."
        try:
            result = await self.client.chunk_text(text, type="DocBlock")
            if not result or len(result) == 0:
                print("❌ No chunks returned for embedding test")
                self.results["embeddings"] = {"status": "error", "error": "no_chunks"}
                return False

            chunks_with_emb = []
            chunks_without_emb = []
            for chunk in result:
                emb = getattr(chunk, "embedding", None)
                if emb is not None:
                    chunks_with_emb.append(chunk)
                else:
                    chunks_without_emb.append(chunk)

            print(f"✅ Embeddings test: {len(chunks_with_emb)}/{len(result)} chunks have embeddings")
            if chunks_without_emb:
                print(f"⚠️  {len(chunks_without_emb)} chunks without embeddings (empty chunks)")

            self.results["embeddings"] = {
                "status": "ok",
                "total_chunks": len(result),
                "chunks_with_embedding": len(chunks_with_emb),
                "chunks_without_embedding": len(chunks_without_emb),
            }
            return len(chunks_with_emb) > 0
        except Exception as e:
            print(f"❌ Embeddings test failed: {e}")
            self.results["embeddings"] = {"status": "error", "error": str(e), "type": type(e).__name__}
            return False

    async def test_empty_chunks(self) -> bool:
        """Test processing empty chunks (chunks without embeddings)."""
        print("\n🔍 Test 6: Processing Empty Chunks")
        # Try to get chunks that might not have embeddings
        samples = [
            "Short docstring.",
            "Very short.",
            "Tiny.",
        ]
        empty_count = 0
        total_count = 0

        for text in samples:
            try:
                result = await self.client.chunk_text(text, type="DocBlock")
                total_count += len(result) if result else 0
                if result:
                    for chunk in result:
                        emb = getattr(chunk, "embedding", None)
                        if emb is None:
                            empty_count += 1
            except Exception as e:
                print(f"⚠️  Error processing sample '{text}': {e}")

        print(f"✅ Empty chunks test: {empty_count}/{total_count} chunks without embeddings")
        self.results["empty_chunks"] = {
            "status": "ok",
            "total_chunks": total_count,
            "empty_chunks": empty_count,
        }
        return True

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests."""
        print("=" * 60)
        print("Chunker Client Test Suite")
        print("=" * 60)

        self.load_config()
        self.create_client()

        if not self.client:
            print("❌ Client not created, aborting tests")
            return self.results

        try:
            async with self.client:
                await self.test_health()
                await self.test_chunking_short()
                await self.test_chunking_medium()
                await self.test_chunking_long()
                await self.test_embeddings()
                await self.test_empty_chunks()
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            self.results["fatal_error"] = {"error": str(e), "type": type(e).__name__}
        finally:
            if self.client:
                await self.client.close()

        return self.results

    def print_summary(self) -> None:
        """Print test summary."""
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)

        passed = sum(1 for r in self.results.values() if isinstance(r, dict) and r.get("status") == "ok")
        failed = sum(1 for r in self.results.values() if isinstance(r, dict) and r.get("status") == "error")
        total = len([r for r in self.results.values() if isinstance(r, dict)])

        print(f"Total tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")

        if failed > 0:
            print("\nFailed tests:")
            for test_name, result in self.results.items():
                if isinstance(result, dict) and result.get("status") == "error":
                    error = result.get("error", "unknown")
                    error_type = result.get("type", "unknown")
                    print(f"  - {test_name}: {error_type}: {error}")

        print("\n" + "=" * 60)
        print("Full Results (JSON):")
        print(json.dumps(self.results, indent=2, default=str))


async def main():
    """Main entry point."""
    tester = ChunkerTester()
    await tester.run_all_tests()
    tester.print_summary()


if __name__ == "__main__":
    asyncio.run(main())

