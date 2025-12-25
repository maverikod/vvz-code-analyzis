#!/usr/bin/env python3
"""
Test analyze_project command via OpenAPI with mTLS.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import json
import logging
import ssl
import sys
from pathlib import Path

import httpx

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
# Reduce noise from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

TEST_PROJECT_ROOT = str(Path(__file__).parent.parent.resolve())

# Server OpenAPI endpoint
SERVER_URL = "https://127.0.0.1:15000"
JSONRPC_ENDPOINT = f"{SERVER_URL}/api/jsonrpc"

# mTLS certificates
CERT_DIR = Path(__file__).parent.parent / "mtls_certificates" / "mtls_certificates"
CLIENT_CERT = CERT_DIR / "client" / "code-analysis.crt"
CLIENT_KEY = CERT_DIR / "client" / "code-analysis.key"
CA_CERT = CERT_DIR / "ca" / "ca.crt"


def create_ssl_context() -> ssl.SSLContext:
    """Create SSL context for mTLS client connections."""
    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    # Load CA certificate
    if CA_CERT.exists():
        ssl_context.load_verify_locations(str(CA_CERT))
        logger.debug(f"Loaded CA certificate from {CA_CERT}")
    else:
        logger.warning(f"CA certificate not found: {CA_CERT}")
        # For testing, disable verification
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    # Load client certificate
    if CLIENT_CERT.exists() and CLIENT_KEY.exists():
        ssl_context.load_cert_chain(str(CLIENT_CERT), str(CLIENT_KEY))
        logger.debug(f"Loaded client certificate from {CLIENT_CERT}")
    else:
        logger.warning(f"Client certificate not found: {CLIENT_CERT} or {CLIENT_KEY}")

    return ssl_context


async def test_analyze_project_openapi() -> bool:
    """Test analyze_project command via OpenAPI with mTLS."""
    logger.info("=" * 60)
    logger.info("TEST: analyze_project command via OpenAPI (mTLS)")
    logger.info("=" * 60)
    logger.info(f"Server URL: {SERVER_URL}")
    logger.info(f"JSON-RPC endpoint: {JSONRPC_ENDPOINT}")
    logger.info(f"Test project: {TEST_PROJECT_ROOT}")

    ssl_context = create_ssl_context()

    async with httpx.AsyncClient(verify=ssl_context, timeout=30.0) as client:
        try:
            # Test 1: Health check
            logger.info("\n📋 Test 1: Health check...")
            health_response = await client.get(f"{SERVER_URL}/health")
            if health_response.status_code == 200:
                health_data = health_response.json()
                logger.info("✅ Server is healthy")
                logger.info(
                    f"   Commands registered: {health_data.get('components', {}).get('commands', {}).get('registered_count', 'N/A')}"
                )
            else:
                logger.error(f"❌ Health check failed: {health_response.status_code}")
                return False

            # Test 2: List commands (optional, skip if fails)
            logger.info("\n📋 Test 2: List commands...")
            try:
                commands_response = await client.get(f"{SERVER_URL}/commands")
                if commands_response.status_code == 200:
                    commands_data = commands_response.json()
                    commands = commands_data.get("commands", [])
                    logger.info(f"✅ Found {len(commands)} commands")

                    # Check if analyze_project is available
                    analyze_cmd = next(
                        (
                            cmd
                            for cmd in commands
                            if cmd.get("name") == "analyze_project"
                        ),
                        None,
                    )
                    if analyze_cmd:
                        logger.info("✅ Found analyze_project command")
                        logger.info(
                            f"   Description: {analyze_cmd.get('description', 'N/A')[:100]}..."
                        )
                        logger.info(
                            f"   Use queue: {analyze_cmd.get('use_queue', False)}"
                        )
                    else:
                        logger.warning(
                            "⚠️  analyze_project not found in commands list, but will try to call it"
                        )
                else:
                    logger.warning(
                        f"⚠️  Failed to list commands: {commands_response.status_code}, but will try to call analyze_project"
                    )
            except Exception as e:
                logger.warning(
                    f"⚠️  Error listing commands: {e}, but will try to call analyze_project"
                )

            # Test 3: Call analyze_project (should return job_id)
            logger.info("\n📋 Test 3: Calling analyze_project...")
            logger.info(f"   Root dir: {TEST_PROJECT_ROOT}")
            logger.info("   Max lines: 400")

            jsonrpc_request = {
                "jsonrpc": "2.0",
                "method": "analyze_project",
                "params": {
                    "root_dir": TEST_PROJECT_ROOT,
                    "max_lines": 400,
                    "force": False,
                    "timeout": 300,
                },
                "id": 1,
            }

            call_response = await client.post(
                JSONRPC_ENDPOINT,
                json=jsonrpc_request,
                headers={"Content-Type": "application/json"},
            )

            if call_response.status_code != 200:
                logger.error(
                    f"❌ analyze_project call failed: {call_response.status_code}"
                )
                logger.error(f"   Response: {call_response.text}")
                return False

            call_result = call_response.json()
            logger.info(f"   Response: {json.dumps(call_result, indent=2)}")

            # Check for errors
            if "error" in call_result:
                logger.error(f"❌ JSON-RPC error: {call_result['error']}")
                return False

            result_data = call_result.get("result", {})

            # Check if we got job_id (queue response)
            if "job_id" in result_data:
                job_id = result_data["job_id"]
                logger.info(f"✅ Command queued, job_id: {job_id}")
                logger.info(f"   Status: {result_data.get('status', 'N/A')}")
                logger.info(f"   Message: {result_data.get('message', 'N/A')}")

                # Test 4: Get job status
                logger.info("\n📋 Test 4: Getting job status...")
                max_wait = 300  # 5 minutes max
                wait_interval = 2  # Check every 2 seconds
                waited = 0

                while waited < max_wait:
                    status_request = {
                        "jsonrpc": "2.0",
                        "method": "queue_get_job_status",
                        "params": {
                            "job_id": job_id,
                        },
                        "id": 2,
                    }

                    status_response = await client.post(
                        JSONRPC_ENDPOINT,
                        json=status_request,
                        headers={"Content-Type": "application/json"},
                    )

                    if status_response.status_code != 200:
                        logger.error(
                            f"❌ Failed to get job status: {status_response.status_code}"
                        )
                        break

                    status_result = status_response.json()

                    if "error" in status_result:
                        logger.error(f"❌ JSON-RPC error: {status_result['error']}")
                        break

                    # Structure: result.data contains job status info
                    # result.data.result contains the command execution result
                    # result.data.result.data contains the actual command data
                    status_data = status_result.get("result", {}).get("data", {})
                    job_status = status_data.get("status", "unknown")
                    logger.info(f"   Job status: {job_status} (waited {waited}s)")

                    if job_status == "completed":
                        logger.info("✅ Job completed!")

                        # Extract command result
                        # Structure: status_data.result.result.data contains the actual command result
                        job_result = status_data.get("result", {})

                        if isinstance(job_result, dict):
                            # The command execution result is in job_result.result
                            command_result = job_result.get("result", {})

                            # Check if command succeeded
                            if command_result.get("success") is False:
                                error_info = command_result.get("error", {})
                                error_msg = error_info.get("message", "Unknown error")
                                logger.error(f"❌ Command failed: {error_msg}")
                                logger.debug(
                                    f"   Full error: {json.dumps(error_info, indent=2)}"
                                )
                                return False

                            # Extract data from SuccessResult
                            result_data = command_result.get("data", {})

                            if result_data and isinstance(result_data, dict):
                                logger.info(
                                    f"   Files analyzed: {result_data.get('files_analyzed', 'N/A')}"
                                )
                                logger.info(
                                    f"   Classes: {result_data.get('classes', 'N/A')}"
                                )
                                logger.info(
                                    f"   Functions: {result_data.get('functions', 'N/A')}"
                                )
                                logger.info(
                                    f"   Issues: {result_data.get('issues', 'N/A')}"
                                )
                                logger.info(
                                    f"   Project ID: {result_data.get('project_id', 'N/A')}"
                                )
                            else:
                                logger.warning("⚠️  Result data is empty or not a dict")
                                logger.debug(
                                    f"   command_result: {json.dumps(command_result, indent=2)}"
                                )
                        else:
                            logger.warning(
                                f"⚠️  Unexpected result format: {type(job_result)}"
                            )
                            logger.debug(
                                f"   status_data: {json.dumps(status_data, indent=2)}"
                            )

                        logger.info("\n" + "=" * 60)
                        logger.info("✅ TEST PASSED")
                        logger.info("=" * 60)
                        return True
                    elif job_status == "failed":
                        error_info = status_data.get("error", "Unknown error")
                        logger.error(f"❌ Job failed: {error_info}")
                        return False
                    elif job_status in ("queued", "running"):
                        await asyncio.sleep(wait_interval)
                        waited += wait_interval
                    else:
                        logger.warning(f"⚠️  Unknown status: {job_status}")
                        await asyncio.sleep(wait_interval)
                        waited += wait_interval

                if waited >= max_wait:
                    logger.error(f"❌ Job did not complete within {max_wait} seconds")
                    return False
            else:
                # Direct result (shouldn't happen with use_queue=True, but handle it)
                logger.info("✅ analyze_project completed (direct result)")
                logger.info(f"   Files: {result_data.get('files_analyzed', 'N/A')}")
                logger.info(f"   Classes: {result_data.get('classes', 'N/A')}")
                logger.info(f"   Functions: {result_data.get('functions', 'N/A')}")
                logger.info(f"   Issues: {result_data.get('issues', 'N/A')}")
                logger.info("\n" + "=" * 60)
                logger.info("✅ TEST PASSED")
                logger.info("=" * 60)
                return True

        except Exception as e:
            logger.error(f"\n❌ TEST FAILED: {e}")
            import traceback

            traceback.print_exc()
            return False


def main() -> None:
    """Main entry point."""
    try:
        result = asyncio.run(test_analyze_project_openapi())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted")
        sys.exit(1)


if __name__ == "__main__":
    main()
