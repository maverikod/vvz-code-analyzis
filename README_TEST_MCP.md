# MCP Server Testing CLI

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Overview

CLI utility for testing MCP code analysis server using MCP client library.

## Installation

The CLI utility is installed automatically with the package:

```bash
pip install -e .
```

## Usage

### List Available Tools

```bash
python -m code_analysis.cli.test_mcp_cli --list
```

Or with custom URL:

```bash
python -m code_analysis.cli.test_mcp_cli --url http://127.0.0.1:15000/mcp --list
```

### Call a Tool

#### Using --arg (Key=Value pairs)

```bash
python -m code_analysis.cli.test_mcp_cli \
  --tool analyze_project \
  --arg root_dir=/path/to/project \
  --arg max_lines=400
```

#### Using --json

```bash
python -m code_analysis.cli.test_mcp_cli \
  --tool search_classes \
  --json '{"root_dir": "/path/to/project", "pattern": "Test"}'
```

### Examples

#### Analyze Project

```bash
python -m code_analysis.cli.test_mcp_cli \
  --tool analyze_project \
  --arg root_dir=/home/vasilyvz/projects/tools/code_analysis \
  --arg max_lines=100
```

#### Search Classes

```bash
python -m code_analysis.cli.test_mcp_cli \
  --tool search_classes \
  --arg root_dir=/home/vasilyvz/projects/tools/code_analysis \
  --arg pattern=FastMCP
```

#### Find Usages

```bash
python -m code_analysis.cli.test_mcp_cli \
  --tool find_usages \
  --arg root_dir=/home/vasilyvz/projects/tools/code_analysis \
  --arg name=analyze_project \
  --arg target_type=function
```

#### Full Text Search

```bash
python -m code_analysis.cli.test_mcp_cli \
  --tool full_text_search \
  --arg root_dir=/home/vasilyvz/projects/tools/code_analysis \
  --arg query=FastMCP \
  --arg limit=10
```

#### Get Issues

```bash
python -m code_analysis.cli.test_mcp_cli \
  --tool get_issues \
  --arg root_dir=/home/vasilyvz/projects/tools/code_analysis
```

### Verbose Mode

Enable verbose logging:

```bash
python -m code_analysis.cli.test_mcp_cli \
  --tool analyze_project \
  --arg root_dir=/path/to/project \
  --verbose
```

## Command Line Options

- `--url`: MCP server URL (default: http://127.0.0.1:15000/mcp)
- `--tool`: Tool name to call
- `--list`: List all available tools
- `--arg KEY=VALUE`: Tool arguments (can be used multiple times)
- `--json JSON`: Tool arguments as JSON string
- `--verbose, -v`: Enable verbose logging

## Requirements

- MCP server must be running
- Server URL must be accessible
- Python 3.8+

## Troubleshooting

### Connection Error

If you get connection errors, make sure:
1. MCP server is running
2. Server URL is correct
3. Server is accessible from your machine

### Tool Not Found

If a tool is not found:
1. Check tool name spelling
2. Use `--list` to see available tools
3. Make sure server has the tool registered

### Invalid Arguments

If you get argument errors:
1. Check required parameters for the tool
2. Use `--list` to see tool schema
3. Verify argument types (string, integer, etc.)

