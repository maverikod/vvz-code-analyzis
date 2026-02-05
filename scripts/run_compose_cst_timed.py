#!/usr/bin/env python3
"""
Run compose_cst_module via CLI with elapsed time measurement.

Usage:
  python scripts/run_compose_cst_timed.py --config config.json --project-id UUID --file-path REL_PATH [--tree-id TREE_ID]
  If --tree-id is omitted, loads file with cst_load_file to get tree_id, then runs compose_cst_module.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run compose_cst_module with timing")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--project-id", default=None, help="Project UUID (required unless --list-projects)")
    parser.add_argument("--file-path", default=None, help="File path relative to project root")
    parser.add_argument("--tree-id", default=None, help="CST tree ID (if omitted, load file to get it)")
    parser.add_argument("--commit-message", default=None, help="Optional git commit message")
    parser.add_argument("--list-projects", action="store_true", help="List projects and exit")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (PROJECT_ROOT / args.config).resolve()
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    if args.list_projects:
        from code_analysis.commands.project_management_mcp_commands import ListProjectsMCPCommand

        list_cmd = ListProjectsMCPCommand()
        list_result = await list_cmd.execute()
        projects = (getattr(list_result, "data", None) or {}).get("projects", [])
        print(f"Projects: {len(projects)}")
        for p in projects[:10]:
            print(f"  {p.get('id')}  {p.get('name', '')}  {p.get('root_path', '')}")
        return 0

    project_id = args.project_id
    file_path = args.file_path
    if not project_id or not file_path:
        print("--project-id and --file-path are required (or use --list-projects)", file=sys.stderr)
        return 1

    tree_id = args.tree_id
    commit_message = args.commit_message

    if not tree_id:
        from code_analysis.commands.cst_load_file_command import CSTLoadFileCommand

        load_cmd = CSTLoadFileCommand()
        t0 = time.perf_counter()
        load_result = await load_cmd.execute(project_id=project_id, file_path=file_path)
        load_elapsed = time.perf_counter() - t0
        if not getattr(load_result, "data", None) or not load_result.data.get("tree_id"):
            print(f"cst_load_file failed: {getattr(load_result, 'message', load_result)}", file=sys.stderr)
            return 1
        tree_id = load_result.data["tree_id"]
        print(f"cst_load_file tree_id={tree_id} elapsed={load_elapsed:.3f}s")
    else:
        print(f"Using tree_id={tree_id}")

    from code_analysis.commands.cst_compose_module_command import ComposeCSTModuleCommand

    cmd = ComposeCSTModuleCommand()
    t0 = time.perf_counter()
    result = await cmd.execute(
        project_id=project_id,
        file_path=file_path,
        tree_id=tree_id,
        commit_message=commit_message,
    )
    elapsed = time.perf_counter() - t0

    success = getattr(result, "success", False) or (hasattr(result, "data") and result.data is not None)
    if hasattr(result, "message"):
        print(f"Result: {result.message}")
    if hasattr(result, "code") and result.code:
        print(f"Code: {result.code}")
    print(f"compose_cst_module elapsed={elapsed:.3f}s")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
