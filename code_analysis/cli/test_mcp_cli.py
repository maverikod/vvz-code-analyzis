"""
CLI utility for testing MCP server.

Provides command-line interface for testing code analysis MCP server
using MCP client library.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import json
import logging
import sys
from typing import Any, Dict, Optional

import anyio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


async def test_tool(
    session: ClientSession,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Call a tool on the MCP server.

    Args:
        session: MCP client session
        tool_name: Name of the tool to call
        arguments: Tool arguments

    Returns:
        Tool execution result
    """
    try:
        result = await session.call_tool(tool_name, arguments)
        return result
    except Exception as e:
        logger.error(f"Error calling tool {tool_name}: {e}")
        raise


async def list_tools(session: ClientSession) -> list[Dict[str, Any]]:
    """
    List all available tools.

    Args:
        session: MCP client session

    Returns:
        List of available tools
    """
    try:
        result = await session.list_tools()
        return result.tools
    except Exception as e:
        logger.error(f"Error listing tools: {e}")
        raise


async def run_test(
    url: str,
    tool_name: Optional[str] = None,
    arguments: Optional[Dict[str, Any]] = None,
    list_tools_flag: bool = False,
) -> None:
    """
    Run MCP client test.

    Args:
        url: Server URL
        tool_name: Tool name to call (optional)
        arguments: Tool arguments (optional)
        list_tools_flag: If True, list all tools
    """
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize session
            logger.info("Initializing MCP session...")
            await session.initialize()
            logger.info("Session initialized")

            if list_tools_flag:
                # List all tools
                logger.info("Listing available tools...")
                tools = await list_tools(session)
                print("\n" + "=" * 80)
                print(f"Available tools ({len(tools)}):")
                print("=" * 80)
                for tool in tools:
                    print(f"\n📌 {tool.name}")
                    if tool.description:
                        print(f"   {tool.description}")
                    if tool.inputSchema:
                        print(
                            f"   Parameters: {json.dumps(tool.inputSchema, indent=6)}"
                        )
                print("\n" + "=" * 80)
                return

            if tool_name:
                # Call specific tool
                logger.info(f"Calling tool: {tool_name}")
                if arguments is None:
                    arguments = {}

                result = await test_tool(session, tool_name, arguments)
                print("\n" + "=" * 80)
                print(f"Tool: {tool_name}")
                print("=" * 80)
                print(json.dumps(result, indent=2, default=str))
                print("=" * 80)
            else:
                # Interactive mode
                tools = await list_tools(session)
                print(f"\nAvailable tools: {len(tools)}")
                for tool in tools:
                    print(f"  - {tool.name}")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Test MCP code analysis server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all tools
  %(prog)s --url http://127.0.0.1:15000/mcp --list

  # Call analyze_project
  %(prog)s --url http://127.0.0.1:15000/mcp --tool analyze_project \
      --arg root_dir=/path/to/project

  # Call with JSON arguments
  %(prog)s --url http://127.0.0.1:15000/mcp --tool search_classes \
      --json '{"root_dir": "/path", "pattern": "Test"}'
        """,
    )

    parser.add_argument(
        "--url",
        default="http://127.0.0.1:15000/mcp",
        help="MCP server URL (default: http://127.0.0.1:15000/mcp)",
    )

    parser.add_argument(
        "--tool",
        help="Tool name to call",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available tools",
    )

    parser.add_argument(
        "--arg",
        action="append",
        dest="args",
        metavar="KEY=VALUE",
        help=(
            "Tool arguments (can be used multiple times). "
            "Example: --arg root_dir=/path --arg max_lines=400"
        ),
    )

    parser.add_argument(
        "--json",
        help=(
            'Tool arguments as JSON string. '
            'Example: --json \'{"root_dir": "/path", "max_lines": 400}\''
        ),
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def parse_arguments_dict(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Parse arguments into dictionary.

    Args:
        args: Parsed arguments

    Returns:
        Dictionary of tool arguments
    """
    result: Dict[str, Any] = {}

    # Parse --arg KEY=VALUE pairs
    if args.args:
        for arg in args.args:
            if "=" not in arg:
                logger.warning(f"Invalid argument format: {arg}. Expected KEY=VALUE")
                continue
            key, value = arg.split("=", 1)
            # Try to convert to appropriate type
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            elif value.isdigit():
                value = int(value)
            elif value.replace(".", "", 1).isdigit():
                value = float(value)
            result[key] = value

    # Parse --json
    if args.json:
        try:
            json_args = json.loads(args.json)
            result.update(json_args)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            sys.exit(1)

    return result


def main() -> None:
    """Main entry point."""
    args = parse_arguments()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Validate arguments
    if not args.list and not args.tool:
        logger.error("Either --list or --tool must be specified")
        sys.exit(1)

    if args.list and args.tool:
        logger.error("Cannot use --list and --tool together")
        sys.exit(1)

    # Parse tool arguments
    tool_arguments = parse_arguments_dict(args) if args.tool else None

    # Run async test
    try:
        anyio.run(
            lambda: run_test(
                args.url,
                tool_name=args.tool,
                arguments=tool_arguments,
                list_tools_flag=args.list,
            ),
            backend="asyncio",
        )
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
