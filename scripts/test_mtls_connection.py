"""
Test mTLS connection to chunker server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import json
from pathlib import Path
from svo_client import ChunkerClient


async def main():
    """Test mTLS connection."""
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
    
    print(f"Testing mTLS connection to {ca['url']}:{ca['port']}")
    print(f"Protocol: {ca.get('protocol')}")
    print(f"Cert: {cert}")
    print(f"Key: {key}")
    print(f"CA: {ca_cert}")
    print(f"Cert exists: {Path(cert).exists()}")
    print(f"Key exists: {Path(key).exists()}")
    print(f"CA exists: {Path(ca_cert).exists()}")
    
    # Try with explicit protocol
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
    
    print("\nCreating client...")
    client = ChunkerClient(**client_kwargs)
    
    print(f"Client protocol: {client.protocol}")
    print(f"Client host: {client.host}")
    print(f"Client port: {client.port}")
    
    print("\nTesting health check...")
    try:
        async with client:
            result = await client.health()
            print(f"✅ Health check passed: {result}")
            
            # Test chunking
            text = "Test docstring for chunking with mTLS."
            print("\nTesting chunking...")
            chunks = await client.chunk_text(text, type="DocBlock")
            print(f"✅ Chunking test: {len(chunks)} chunks")
            if chunks:
                chunk = chunks[0]
                has_emb = hasattr(chunk, "embedding") and getattr(chunk, "embedding", None) is not None
                has_bm25 = hasattr(chunk, "bm25") and getattr(chunk, "bm25", None) is not None
                print(f"  - has_embedding: {has_emb}")
                print(f"  - has_bm25: {has_bm25}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

