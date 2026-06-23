"""
Entity-index self-check (TZ-CA-INDEX-INTEGRITY-001 C-1 acceptance).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.integrity_analysis.entity_index_check import check_entity_index


class FakeDB:
    def __init__(self, files, functions, classes, methods):
        self._counts = {
            "functions": functions,
            "classes": classes,
            "methods": methods,
            "files": files,
        }

    def execute(self, sql, params=None):
        if "FROM functions" in sql:
            key = "functions"
        elif "FROM methods" in sql:
            key = "methods"
        elif "FROM classes" in sql:
            key = "classes"
        else:
            key = "files"
        return {"data": [{"cnt": self._counts[key]}]}


def test_ok_when_entities_present():
    r = check_entity_index(FakeDB(600, 2837, 372, 1053), "p")
    assert r["ok"] is True
    assert r["entities"] == 2837 + 372 + 1053


def test_not_ok_when_files_present_but_entities_empty():
    # the desync signature: files indexed, all entity tables empty
    r = check_entity_index(FakeDB(600, 0, 0, 0), "p")
    assert r["ok"] is False
    assert r["files"] == 600 and r["entities"] == 0


def test_ok_when_project_truly_empty():
    # no files at all -> not the desync condition (nothing to index)
    r = check_entity_index(FakeDB(0, 0, 0, 0), "p")
    assert r["ok"] is True
