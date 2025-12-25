"""
Detailed mTLS connection test with verbose logging.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import json
import logging
from pathlib import Path
from svo_client import ChunkerClient

# Enable verbose logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def main():
    """Test mTLS connection with detailed logging."""
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    ca = cfg["code_analysis"]["chunker"]

    # Resolve paths
    cert = Path(ca["cert_file"])
    if not cert.is_absolute():
        cert = Path(".") / cert
    cert = str(cert.resolve()) if cert.exists() else ca["cert_file"]

    key = Path(ca["key_file"])
    if not key.is_absolute():
        key = Path(".") / key
    key = str(key.resolve()) if key.exists() else ca["key_file"]

    ca_cert = Path(ca["ca_cert_file"])
    if not ca_cert.is_absolute():
        ca_cert = Path(".") / ca_cert
    ca_cert = str(ca_cert.resolve()) if ca_cert.exists() else ca["ca_cert_file"]

    print("=" * 60)
    print("mTLS Connection Test (Detailed)")
    print("=" * 60)
    print(f"Server: {ca['url']}:{ca['port']}")
    print(f"Protocol: {ca.get('protocol')}")
    print(f"Cert: {cert} (exists: {Path(cert).exists()})")
    print(f"Key: {key} (exists: {Path(key).exists()})")
    print(f"CA: {ca_cert} (exists: {Path(ca_cert).exists()})")
    print()

    # Create client
    client_kwargs = {
        "host": ca["url"],
        "port": ca["port"],
        "cert": cert,
        "key": key,
        "ca": ca_cert,
        "check_hostname": False,
    }

    if ca.get("timeout"):
        client_kwargs["timeout"] = float(ca["timeout"])

    print("Creating ChunkerClient with kwargs:")
    for k, v in client_kwargs.items():
        if k in ("cert", "key", "ca"):
            print(
                f"  {k}: {v} (exists: {Path(v).exists() if isinstance(v, str) else False})"
            )
        else:
            print(f"  {k}: {v}")
    print()

    try:
        client = ChunkerClient(**client_kwargs)
        print("✅ Client created")
        print(f"   Protocol: {client.protocol}")
        print(f"   Host: {client.host}")
        print(f"   Port: {client.port}")
        print(f"   Timeout: {client.timeout}")
        print()

        print("Testing health check...")
        async with client:
            try:
                result = await client.health()
                print("✅ Health check passed!")
                print(f"   Result: {json.dumps(result, indent=2)}")
            except Exception as e:
                print(f"❌ Health check failed: {type(e).__name__}: {e}")
                import traceback

                traceback.print_exc()
                return

        print()
        print("Testing chunking...")
        try:
            text = "Test docstring for chunking with mTLS connection."
            chunks = await client.chunk_text(text, type="DocBlock")
            print("✅ Chunking test passed!")
            print(f"   Chunks: {len(chunks)}")
            if chunks:
                chunk = chunks[0]
                has_emb = (
                    hasattr(chunk, "embedding")
                    and getattr(chunk, "embedding", None) is not None
                )
                has_bm25 = (
                    hasattr(chunk, "bm25") and getattr(chunk, "bm25", None) is not None
                )
                print(f"   - has_embedding: {has_emb}")
                print(f"   - has_bm25: {has_bm25}")
        except Exception as e:
            print(f"❌ Chunking test failed: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()

    except Exception as e:
        print(f"❌ Failed to create client: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
