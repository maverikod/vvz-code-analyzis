#!/usr/bin/env python3
"""
Test analyze_project command via MCP Proxy with queue support.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

import anyio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

TEST_PROJECT_ROOT = str(Path(__file__).parent.parent.resolve())

# MCP Proxy endpoint (for Cursor AI)
PROXY_MCP_URL = "http://127.0.0.1:3002/mcp"


async def test_analyze_project() -> bool:
    """Test analyze_project command via MCP Proxy with queue."""
    logger.info("=" * 60)
    logger.info("TEST: analyze_project command via MCP Proxy (with queue)")
    logger.info("=" * 60)
    logger.info(f"Proxy MCP URL: {PROXY_MCP_URL}")
    logger.info(f"Test project: {TEST_PROJECT_ROOT}")
    
    
    try:
        async with streamablehttp_client(PROXY_MCP_URL) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                logger.info("✅ Connected to MCP Proxy")
                
                # Initialize
                await session.initialize()
                logger.info("✅ Session initialized")
                
                # Test 1: List tools to verify analyze_project is available
                logger.info("\n📋 Test 1: List tools...")
                tools = await session.list_tools()
                logger.info(f"✅ Found {len(tools.tools)} tools")
                
                # Find analyze_project tool
                analyze_tool = None
                for tool in tools.tools:
                    if tool.name == "analyze_project":
                        analyze_tool = tool
                        break
                
                if not analyze_tool:
                    logger.error("❌ analyze_project tool not found")
                    return False
                
                logger.info(f"✅ Found analyze_project tool")
                logger.info(f"   Description: {analyze_tool.description[:100]}...")
                
                # Test 2: Call analyze_project (should return job_id since use_queue=True)
                logger.info("\n📋 Test 2: Calling analyze_project...")
                logger.info(f"   Root dir: {TEST_PROJECT_ROOT}")
                logger.info(f"   Max lines: 400")
                
                try:
                    call_result = await asyncio.wait_for(
                        session.call_tool(
                            "analyze_project",
                            {
                                "root_dir": TEST_PROJECT_ROOT,
                                "max_lines": 400,
                                "force": False,
                                "timeout": 300,
                            },
                        ),
                        timeout=10.0,  # Should return quickly with job_id
                    )
                    
                    # Extract content from CallToolResult
                    if hasattr(call_result, 'content') and call_result.content:
                        content_text = call_result.content[0].text
                        result = json.loads(content_text) if content_text else {}
                    else:
                        result = call_result
                    
                except asyncio.TimeoutError:
                    logger.error("❌ analyze_project call timed out")
                    return False
                
                logger.info(f"   Response: {json.dumps(result, indent=2)}")
                
                # Check if we got job_id (queue response)
                if isinstance(result, dict):
                    if "job_id" in result:
                        job_id = result["job_id"]
                        logger.info(f"✅ Command queued, job_id: {job_id}")
                        logger.info(f"   Status: {result.get('status', 'N/A')}")
                        logger.info(f"   Message: {result.get('message', 'N/A')}")
                        
                        # Test 3: Get job status
                        logger.info("\n📋 Test 3: Getting job status...")
                        max_wait = 300  # 5 minutes max
                        wait_interval = 2  # Check every 2 seconds
                        waited = 0
                        
                        while waited < max_wait:
                            try:
                                status_result = await session.call_tool(
                                    "queue_get_job_status",
                                    {"job_id": job_id},
                                )
                                
                                # Extract content
                                if hasattr(status_result, 'content') and status_result.content:
                                    status_text = status_result.content[0].text
                                    status_data = json.loads(status_text) if status_text else {}
                                else:
                                    status_data = status_result
                                
                                if isinstance(status_data, dict):
                                    job_status = status_data.get("data", {}).get("status", "unknown")
                                    logger.info(f"   Job status: {job_status} (waited {waited}s)")
                                    
                                    if job_status == "completed":
                                        logger.info("✅ Job completed!")
                                        job_result = status_data.get("data", {}).get("result", {})
                                        if isinstance(job_result, dict):
                                            result_data = job_result.get("data", {})
                                            logger.info(f"   Files analyzed: {result_data.get('files_analyzed', 'N/A')}")
                                            logger.info(f"   Classes: {result_data.get('classes', 'N/A')}")
                                            logger.info(f"   Functions: {result_data.get('functions', 'N/A')}")
                                            logger.info(f"   Issues: {result_data.get('issues', 'N/A')}")
                                        break
                                    elif job_status == "failed":
                                        logger.error(f"❌ Job failed: {status_data.get('data', {}).get('error', 'Unknown error')}")
                                        return False
                                    elif job_status in ("queued", "running"):
                                        await asyncio.sleep(wait_interval)
                                        waited += wait_interval
                                    else:
                                        logger.warning(f"⚠️  Unknown status: {job_status}")
                                        await asyncio.sleep(wait_interval)
                                        waited += wait_interval
                                else:
                                    logger.warning(f"⚠️  Unexpected status format: {type(status_data)}")
                                    await asyncio.sleep(wait_interval)
                                    waited += wait_interval
                                    
                            except Exception as e:
                                logger.error(f"❌ Error getting job status: {e}")
                                return False
                        
                        if waited >= max_wait:
                            logger.error(f"❌ Job did not complete within {max_wait} seconds")
                            return False
                        
                        logger.info("\n" + "=" * 60)
                        logger.info("✅ TEST PASSED")
                        logger.info("=" * 60)
                        return True
                    else:
                        # Direct result (shouldn't happen with use_queue=True, but handle it)
                        logger.info("✅ analyze_project completed (direct result)")
                        logger.info(f"   Files: {result.get('files_analyzed', 'N/A')}")
                        logger.info(f"   Classes: {result.get('classes', 'N/A')}")
                        logger.info(f"   Functions: {result.get('functions', 'N/A')}")
                        logger.info(f"   Issues: {result.get('issues', 'N/A')}")
                        return True
                else:
                    logger.error(f"❌ Unexpected result type: {type(result)}")
                    logger.error(f"   Result: {result}")
                    return False
                
    except Exception as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main() -> None:
    """Main entry point."""
    try:
        result = anyio.run(test_analyze_project, backend="asyncio")
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted")
        sys.exit(1)


if __name__ == "__main__":
    main()
