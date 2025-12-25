"""
Simple test to verify chunker client works correctly.

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


async def test_simple():
    """Test chunker with simple text."""
    print("=" * 80)
    print("SIMPLE CHUNKER TEST")
    print("=" * 80)

    # Use same certificates as in diagnose script
    cert_file = "mtls_certificates/mtls_certificates/client/code-analysis.crt"
    key_file = "mtls_certificates/mtls_certificates/client/code-analysis.key"
    ca_file = "mtls_certificates/mtls_certificates/ca/ca.crt"

    # Resolve to absolute paths
    cert_path = Path(cert_file).resolve()
    key_path = Path(key_file).resolve()
    ca_path = Path(ca_file).resolve()

    print("\nCertificates:")
    print(f"  Cert: {cert_path} (exists: {cert_path.exists()})")
    print(f"  Key: {key_path} (exists: {key_path.exists()})")
    print(f"  CA: {ca_path} (exists: {ca_path.exists()})")

    client = ChunkerClient(
        host="localhost",
        port=8009,
        cert=str(cert_path) if cert_path.exists() else cert_file,
        key=str(key_path) if key_path.exists() else key_file,
        ca=str(ca_path) if ca_path.exists() else ca_file,
        check_hostname=False,
        timeout=60.0,
    )

    try:
        # Test health first
        print("\n1. Testing health check...")
        health = await client.health()
        print(f"✅ Health check: {health.get('success', False)}")

        # Test with simple text
        print("\n2. Testing chunk_text with simple text...")
        test_text = "Register server with MCP Proxy."
        print(f"   Text: {test_text}")
        print(f"   Length: {len(test_text)}")

        result = await client.chunk_text(test_text, type="DocBlock")

        if result:
            print(f"✅ Success! Received {len(result)} chunks")
            if len(result) > 0:
                first = result[0]
                print(f"   First chunk type: {type(first)}")
                if hasattr(first, "body"):
                    print(f"   First chunk body: {first.body[:100]}")
                elif hasattr(first, "text"):
                    print(f"   First chunk text: {first.text[:100]}")
        else:
            print("❌ Result is None")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_simple())
