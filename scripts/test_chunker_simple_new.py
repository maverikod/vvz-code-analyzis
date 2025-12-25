"""
Simple test for new ChunkerClient.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import json
from pathlib import Path
from svo_client import ChunkerClient


async def main():
    """Test ChunkerClient."""
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

    print(f"Creating client: {ca['url']}:{ca['port']}")
    print(f"Protocol: {ca.get('protocol', 'http')}")

    # Build client kwargs based on protocol
    client_kwargs = {
        "host": ca["url"],
        "port": ca["port"],
        "check_hostname": False,
    }

    # Add timeout if configured
    if ca.get("timeout"):
        client_kwargs["timeout"] = float(ca["timeout"])

    # Add mTLS certificates only if protocol is explicitly mtls or https
    # IMPORTANT: Do NOT pass certificates for HTTP protocol, even if they are in config
    # This will cause the client to try to use SSL/TLS which the server doesn't support
    protocol = ca.get("protocol", "http")
    if protocol in ("https", "mtls"):
        if cert and key and ca_cert:
            print(f"Cert: {cert}")
            print(f"Key: {key}")
            print(f"CA: {ca_cert}")
            client_kwargs["cert"] = cert
            client_kwargs["key"] = key
            client_kwargs["ca"] = ca_cert
        else:
            print(
                "⚠️  mTLS protocol but certificates not provided, falling back to HTTP"
            )
            # Remove protocol from kwargs to force HTTP
            protocol = "http"
    else:
        print("Using HTTP (no certificates)")

    client = ChunkerClient(**client_kwargs)

    print("Client created, testing health...")

    try:
        async with client:
            result = await client.health()
            print(f"✅ Health check passed: {result}")

            # Test chunking
            text = "Test docstring for chunking."
            chunks = await client.chunk_text(text, type="DocBlock")
            print(f"✅ Chunking test: {len(chunks)} chunks")
            if chunks:
                chunk = chunks[0]
                has_emb = (
                    hasattr(chunk, "embedding")
                    and getattr(chunk, "embedding", None) is not None
                )
                has_bm25 = (
                    hasattr(chunk, "bm25") and getattr(chunk, "bm25", None) is not None
                )
                print(f"  - has_embedding: {has_emb}")
                print(f"  - has_bm25: {has_bm25}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
