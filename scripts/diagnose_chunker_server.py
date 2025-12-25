"""
Diagnostic script for chunker server empty result issue.

This script performs detailed analysis of chunker server responses
to help diagnose why all chunking requests return empty results.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import sys
import json
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from svo_client import ChunkerClient
from svo_client.errors import SVOServerError


class ChunkerDiagnostics:
    """Diagnostic tool for chunker server issues."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8009,
        cert_file: Optional[str] = None,
        key_file: Optional[str] = None,
        ca_cert_file: Optional[str] = None,
    ):
        """
        Initialize diagnostics.

        Args:
            host: Chunker server host
            port: Chunker server port
            cert_file: Path to client certificate
            key_file: Path to client private key
            ca_cert_file: Path to CA certificate
        """
        self.host = host
        self.port = port
        self.cert_file = cert_file
        self.key_file = key_file
        self.ca_cert_file = ca_cert_file
        self.client: Optional[ChunkerClient] = None

    async def initialize(self) -> bool:
        """Initialize chunker client."""
        try:
            client_kwargs = {
                "host": self.host,
                "port": self.port,
                "check_hostname": False,
                "timeout": 60.0,
            }

            if self.cert_file and self.key_file and self.ca_cert_file:
                client_kwargs["cert"] = str(Path(self.cert_file).resolve())
                client_kwargs["key"] = str(Path(self.key_file).resolve())
                client_kwargs["ca"] = str(Path(self.ca_cert_file).resolve())
                print("✅ Using mTLS certificates:")
                print(f"   Cert: {client_kwargs['cert']}")
                print(f"   Key: {client_kwargs['key']}")
                print(f"   CA: {client_kwargs['ca']}")
            else:
                print("⚠️  No certificates provided, using plain HTTP")

            self.client = ChunkerClient(**client_kwargs)
            print(f"✅ ChunkerClient initialized: {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize client: {e}")
            traceback.print_exc()
            return False

    async def test_health(self) -> bool:
        """Test health check endpoint."""
        print("\n" + "=" * 80)
        print("TEST 1: Health Check")
        print("=" * 80)

        if not self.client:
            print("❌ Client not initialized")
            return False

        try:
            print(f"Calling health() on {self.host}:{self.port}...")
            result = await self.client.health()
            print("✅ Health check succeeded")
            print(f"Response type: {type(result)}")
            print(f"Response: {json.dumps(result, indent=2, default=str)}")
            return True
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            print(f"Error type: {type(e).__name__}")
            traceback.print_exc()
            return False

    async def test_chunk_text(
        self, text: str, test_name: str, **params
    ) -> Dict[str, Any]:
        """
        Test chunk_text with detailed diagnostics.

        Args:
            text: Text to chunk
            test_name: Name of the test case
            **params: Additional parameters for chunking

        Returns:
            Dictionary with test results
        """
        print("\n" + "=" * 80)
        print(f"TEST: {test_name}")
        print("=" * 80)
        print(f"Text length: {len(text)} characters")
        print(f"Text preview: {text[:100]}{'...' if len(text) > 100 else ''}")
        print(f"Parameters: {params}")

        if not self.client:
            return {
                "success": False,
                "error": "Client not initialized",
                "test_name": test_name,
            }

        result_info = {
            "test_name": test_name,
            "text_length": len(text),
            "text_preview": text[:100],
            "params": params,
            "success": False,
            "error": None,
            "error_type": None,
            "result_type": None,
            "result_length": None,
            "result_details": None,
        }

        try:
            print("\nCalling chunk_text()...")
            print(f"Client type: {type(self.client)}")
            print(
                f"Client attributes: {[attr for attr in dir(self.client) if not attr.startswith('_')]}"
            )

            # Try to get more info about the request
            if hasattr(self.client, "_client"):
                print(f"Internal client: {type(self.client._client)}")

            result = await self.client.chunk_text(text, **params)

            result_info["result_type"] = str(type(result))
            result_info["result_length"] = len(result) if result is not None else None

            if result is None:
                result_info["error"] = "Result is None"
                print("❌ Result is None")
            elif isinstance(result, list):
                if len(result) == 0:
                    result_info["error"] = "Result is empty list"
                    print("❌ Result is empty list")
                else:
                    result_info["success"] = True
                    print(f"✅ Received {len(result)} chunks")

                    # Analyze first chunk
                    first_chunk = result[0]
                    chunk_info = {
                        "type": str(type(first_chunk)),
                        "attributes": dir(first_chunk),
                    }

                    # Check for common attributes
                    for attr in ["text", "body", "embedding", "bm25", "type"]:
                        if hasattr(first_chunk, attr):
                            value = getattr(first_chunk, attr)
                            if value is not None:
                                if attr == "embedding" and isinstance(value, list):
                                    chunk_info[attr] = {
                                        "present": True,
                                        "length": len(value),
                                        "preview": (
                                            value[:5] if len(value) > 5 else value
                                        ),
                                    }
                                else:
                                    chunk_info[attr] = {
                                        "present": True,
                                        "value": str(value)[:100],
                                    }
                            else:
                                chunk_info[attr] = {"present": True, "value": None}
                        else:
                            chunk_info[attr] = {"present": False}

                    result_info["result_details"] = {
                        "chunk_count": len(result),
                        "first_chunk": chunk_info,
                    }

                    print("\nFirst chunk analysis:")
                    print(f"  Type: {chunk_info['type']}")
                    for attr, info in chunk_info.items():
                        if attr not in ["type", "attributes"]:
                            if isinstance(info, dict) and info.get("present"):
                                if info.get("value") is not None:
                                    print(f"  {attr}: {info.get('value', 'N/A')}")
                                elif "length" in info:
                                    print(
                                        f"  {attr}: length={info['length']}, preview={info.get('preview', 'N/A')}"
                                    )
                                else:
                                    print(f"  {attr}: None")
            else:
                result_info["error"] = f"Unexpected result type: {type(result)}"
                print(f"❌ Unexpected result type: {type(result)}")
                print(f"Result: {result}")

        except SVOServerError as e:
            result_info["error"] = str(e)
            result_info["error_type"] = "SVOServerError"
            print(f"❌ SVOServerError: {e}")
            print(f"Error details: {type(e).__name__}")
            traceback.print_exc()
        except Exception as e:
            result_info["error"] = str(e)
            result_info["error_type"] = type(e).__name__
            print(f"❌ Exception: {e}")
            print(f"Error type: {type(e).__name__}")
            traceback.print_exc()

        return result_info

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all diagnostic tests."""
        print("\n" + "=" * 80)
        print("CHUNKER SERVER DIAGNOSTICS")
        print("=" * 80)

        if not await self.initialize():
            return {"success": False, "error": "Failed to initialize client"}

        results = {
            "host": self.host,
            "port": self.port,
            "health_check": None,
            "chunking_tests": [],
        }

        # Test health check
        results["health_check"] = await self.test_health()

        # Test cases from bug report
        test_cases = [
            {
                "name": "Short text (30 chars)",
                "text": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                "params": {},
            },
            {
                "name": "Medium text (50-150 chars)",
                "text": "This is a longer test docstring that should definitely be chunked properly. It contains more than enough text.",
                "params": {},
            },
            {
                "name": "Long text (300+ chars)",
                "text": "This is a very long test docstring. " * 10,
                "params": {},
            },
            {
                "name": "Text with Python code",
                "text": "This is a docstring with Python code example.\n\ndef example():\n    return True",
                "params": {},
            },
            {
                "name": "Real docstring 1 (42 chars)",
                "text": "Simple HTTPS server with mTLS for testing.",
                "params": {"type": "DocBlock"},
            },
            {
                "name": "Real docstring 2 (47 chars)",
                "text": "Create SSL context for mTLS client connections.",
                "params": {"type": "DocBlock"},
            },
            {
                "name": "Real docstring 3 (31 chars)",
                "text": "Register server with MCP Proxy.",
                "params": {"type": "DocBlock"},
            },
        ]

        # Run chunking tests
        for test_case in test_cases:
            test_result = await self.test_chunk_text(
                test_case["text"], test_case["name"], **test_case["params"]
            )
            results["chunking_tests"].append(test_result)
            await asyncio.sleep(1)  # Small delay between tests

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(
            f"Health check: {'✅ PASSED' if results['health_check'] else '❌ FAILED'}"
        )
        successful = sum(1 for t in results["chunking_tests"] if t.get("success"))
        total = len(results["chunking_tests"])
        print(f"Chunking tests: {successful}/{total} successful")

        print("\nDetailed results:")
        for test in results["chunking_tests"]:
            status = "✅" if test.get("success") else "❌"
            print(f"  {status} {test['test_name']}: {test.get('error', 'OK')}")

        return results

    async def close(self):
        """Close client connection."""
        if self.client:
            await self.client.close()


async def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Diagnose chunker server empty result issue"
    )
    parser.add_argument("--host", default="localhost", help="Chunker server host")
    parser.add_argument("--port", type=int, default=8009, help="Chunker server port")
    parser.add_argument("--cert", help="Path to client certificate")
    parser.add_argument("--key", help="Path to client private key")
    parser.add_argument("--ca", help="Path to CA certificate")
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config.json (will read chunker config from it)",
    )

    args = parser.parse_args()

    # Load config if provided
    cert_file = args.cert
    key_file = args.key
    ca_cert_file = args.ca

    if args.config and args.config.exists():
        with open(args.config) as f:
            config = json.load(f)

        chunker_config = config.get("code_analysis", {}).get("chunker", {})
        if chunker_config:
            cert_file = cert_file or chunker_config.get("cert_file")
            key_file = key_file or chunker_config.get("key_file")
            ca_cert_file = ca_cert_file or chunker_config.get("ca_cert_file")
            if chunker_config.get("url"):
                args.host = chunker_config["url"]
            if chunker_config.get("port"):
                args.port = chunker_config["port"]

    # Resolve relative paths
    if cert_file:
        cert_file = str(Path(cert_file).resolve())
    if key_file:
        key_file = str(Path(key_file).resolve())
    if ca_cert_file:
        ca_cert_file = str(Path(ca_cert_file).resolve())

    diagnostics = ChunkerDiagnostics(
        host=args.host,
        port=args.port,
        cert_file=cert_file,
        key_file=key_file,
        ca_cert_file=ca_cert_file,
    )

    try:
        results = await diagnostics.run_all_tests()

        # Save results to file
        results_file = Path("logs/chunker_diagnostics_results.json")
        results_file.parent.mkdir(parents=True, exist_ok=True)
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n✅ Results saved to: {results_file}")

        if results.get("health_check") and any(
            t.get("success") for t in results.get("chunking_tests", [])
        ):
            sys.exit(0)
        else:
            sys.exit(1)
    finally:
        await diagnostics.close()


if __name__ == "__main__":
    asyncio.run(main())
