"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Find docstrings present in the filesystem but missing in the database chunks.
"""

import argparse
import ast
import os
import sqlite3
from pathlib import Path
from typing import List, Set, Tuple


def collect_fs_docstrings(root_dir: Path) -> List[Tuple[str, str]]:
    """Collect (path, docstring) from all .py files."""
    results: List[Tuple[str, str]] = []

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
            try:
                source = file_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except Exception:
                continue

            # module docstring
            mod_ds = ast.get_docstring(tree)
            if mod_ds:
                results.append((str(file_path.resolve()), mod_ds.strip()))

            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    ds = ast.get_docstring(node)
                    if ds:
                        results.append((str(file_path.resolve()), ds.strip()))

    return results


def collect_db_docstrings(db_path: Path) -> List[Tuple[str, str]]:
    """Collect (path, chunk_text) for docstring chunks from DB."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT f.path AS path, c.chunk_text AS text
        FROM code_chunks c
        JOIN files f ON c.file_id = f.id
        WHERE c.source_type LIKE '%docstring%'
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [(str(Path(r["path"]).resolve()), (r["text"] or "").strip()) for r in rows]


def normalize_entries(entries: List[Tuple[str, str]]) -> Set[Tuple[str, str]]:
    """Normalize entries by stripping text; path as resolved string."""
    norm: Set[Tuple[str, str]] = set()
    for path, text in entries:
        norm.add((path, text.strip()))
    return norm


def main() -> None:
    parser = argparse.ArgumentParser(description="Find docstrings missing in DB.")
    parser.add_argument(
        "--root-dir",
        default=".",
        help="Project root (default: .)",
    )
    parser.add_argument(
        "--db-path",
        default="data/code_analysis.db",
        help="Path to SQLite database (default: data/code_analysis.db)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Limit for sample output (default: 20)",
    )
    args = parser.parse_args()

    root_dir = Path(args.root_dir).resolve()
    db_path = Path(args.db_path).resolve()

    fs_entries = collect_fs_docstrings(root_dir)
    db_entries = collect_db_docstrings(db_path)

    fs_set = normalize_entries(fs_entries)
    db_set = normalize_entries(db_entries)

    missing = fs_set - db_set

    print(f"Project root: {root_dir}")
    print(f"Database: {db_path} (exists: {db_path.exists()})")
    print(f"Docstrings in files: {len(fs_set)}")
    print(f"Docstrings in DB: {len(db_set)}")
    print(f"Missing (in files, not in DB): {len(missing)}")

    for i, (path, text) in enumerate(list(missing)[: args.limit]):
        preview = text[:120].replace("\n", " ")
        print(f"[{i+1}] {path} :: {preview}")


if __name__ == "__main__":
    main()
