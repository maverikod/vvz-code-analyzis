#!/usr/bin/env python3
"""
Get OpenAPI schema from server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import json
import ssl
from pathlib import Path

import httpx

SERVER_URL = "https://127.0.0.1:15000"
CERT_DIR = Path(__file__).parent.parent / "mtls_certificates" / "mtls_certificates"
CLIENT_CERT = CERT_DIR / "client" / "code-analysis.crt"
CLIENT_KEY = CERT_DIR / "client" / "code-analysis.key"
CA_CERT = CERT_DIR / "ca" / "ca.crt"


def create_ssl_context() -> ssl.SSLContext:
    """Create SSL context for mTLS client connections."""
    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    if CA_CERT.exists():
        ssl_context.load_verify_locations(str(CA_CERT))
    else:
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    if CLIENT_CERT.exists() and CLIENT_KEY.exists():
        ssl_context.load_cert_chain(str(CLIENT_CERT), str(CLIENT_KEY))

    return ssl_context


async def get_openapi_schema():
    """Get OpenAPI schema from server."""
    ssl_context = create_ssl_context()

    async with httpx.AsyncClient(verify=ssl_context, timeout=30.0) as client:
        try:
            response = await client.get(f"{SERVER_URL}/openapi.json")
            if response.status_code == 200:
                schema = response.json()
                print(json.dumps(schema, indent=2))
                return schema
            else:
                print(f"Error: {response.status_code}")
                print(response.text)
                return None
        except Exception as e:
            print(f"Error: {e}")
            import traceback

            traceback.print_exc()
            return None


if __name__ == "__main__":
    asyncio.run(get_openapi_schema())
