"""
Resolver-based circular-import detection (TZ-CA-INDEX-INTEGRITY-001 C-3).

Proves the resolver detector finds a cycle expressed with BARE/relative import
module strings — exactly the shape the old exact-dotted-path SQL matcher missed
(returned 0 cycles where analyze_tree found them).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

from code_analysis.core.integrity_analysis.import_cycles_resolver import (
    fetch_import_cycles_resolver,
)


class FakeDB:
    def __init__(self, tables):
        self._t = tables

    def execute(self, sql, params=None):
        key = "imports" if "FROM imports" in sql else "files"
        return {"data": list(self._t.get(key, []))}


def test_resolver_finds_cycle_from_bare_module_imports(tmp_path):
    files = [
        {"id": "fa", "path": "/r/pkg/a.py", "relative_path": "pkg/a.py"},
        {"id": "fb", "path": "/r/pkg/b.py", "relative_path": "pkg/b.py"},
        {"id": "fc", "path": "/r/pkg/c.py", "relative_path": "pkg/c.py"},
    ]
    # a -> b and b -> a, written as bare `from b import foo` / `from a import bar`
    # (module has no package prefix) — the exact-dotted-path SQL could not match
    # these against 'pkg.a' / 'pkg.b'. c imports nothing cyclic.
    imports = [
        {"file_id": "fa", "module": "b", "name": "foo", "import_type": "from"},
        {"file_id": "fb", "module": "a", "name": "bar", "import_type": "from"},
        {"file_id": "fc", "module": "os", "name": None, "import_type": "import"},
    ]
    db = FakeDB({"files": files, "imports": imports})

    cycles = fetch_import_cycles_resolver(db, "proj", tmp_path)
    assert len(cycles) == 1
    assert set(cycles[0]) == {"fa", "fb"}


def test_resolver_no_false_cycle(tmp_path):
    files = [
        {"id": "fa", "path": "/r/pkg/a.py", "relative_path": "pkg/a.py"},
        {"id": "fb", "path": "/r/pkg/b.py", "relative_path": "pkg/b.py"},
    ]
    imports = [  # a -> b only; no back-edge
        {"file_id": "fa", "module": "b", "name": "foo", "import_type": "from"},
    ]
    db = FakeDB({"files": files, "imports": imports})
    assert fetch_import_cycles_resolver(db, "proj", tmp_path) == []
