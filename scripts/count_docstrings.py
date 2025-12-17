"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Count docstrings in a project and compare with database chunks.
"""

import argparse
import ast
import os
import sqlite3
from pathlib import Path
from typing import Tuple


def count_docstrings_in_file(path: Path) -> int:
    """Return number of docstrings in a Python file."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0

    count = 0

    # Module docstring
    if ast.get_docstring(tree):
        count += 1

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if ast.get_docstring(node):
                count += 1

    return count


def count_docstrings_in_project(root_dir: Path) -> int:
    """Count docstrings across all .py files under root_dir."""
    total = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(".")
            and d not in {"__pycache__", "node_modules", ".venv", "venv"}
        ]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            file_path = Path(dirpath) / filename
            total += count_docstrings_in_file(file_path)
    return total


def get_db_docstring_counts(db_path: Path) -> Tuple[int, int]:
    """
    Return (total_docstring_chunks, docstring_chunks_with_vector).

    Docstrings are identified by source_type containing 'docstring'.
    """
    if not db_path.exists():
        return 0, 0

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM code_chunks WHERE source_type LIKE '%docstring%'"
    )
    total = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM code_chunks WHERE source_type LIKE '%docstring%' AND vector_id IS NOT NULL"
    )
    with_vec = cur.fetchone()[0]

    conn.close()
    return total, with_vec


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count docstrings and compare with database chunks."
    )
    parser.add_argument(
        "--root-dir",
        default=".",
        help="Project root (default: current directory)",
    )
    parser.add_argument(
        "--db-path",
        default="data/code_analysis.db",
        help="Path to SQLite database (default: data/code_analysis.db)",
    )
    args = parser.parse_args()

    root_dir = Path(args.root_dir).resolve()
    db_path = Path(args.db_path).resolve()

    fs_count = count_docstrings_in_project(root_dir)
    db_total, db_with_vec = get_db_docstring_counts(db_path)

    print(f"Project root: {root_dir}")
    print(f"Database: {db_path} (exists: {db_path.exists()})")
    print(f"Docstrings in files: {fs_count}")
    print(f"Docstring chunks in DB: {db_total}")
    print(f"Docstring chunks with vector_id: {db_with_vec}")
    print(f"Delta (files - DB): {fs_count - db_total}")


if __name__ == "__main__":
    main()

