"""
Regression: list_code_entities must not filter entities by cst_node_id.

cst_node_id is NULL for every indexed entity across all projects (the indexer
does not populate it), so requiring it made list_code_entities return empty
everywhere. See TZ-CA-INDEX-INTEGRITY-001.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.commands.ast import list_entities_page as lep


class _RecordingDB:
    def __init__(self):
        self.sqls = []

    def execute(self, sql, params=()):
        self.sqls.append(sql)
        return {"data": [{"cnt": 7}]}


def test_cst_where_is_tautology():
    assert lep._CST_WHERE == "1=1"


def test_count_query_does_not_filter_on_cst_node_id():
    db = _RecordingDB()
    total = lep.count_code_entities(db, project_id="p1", entity_type="function", file_id=None)
    assert total == 7
    joined = "\n".join(db.sqls)
    assert "cst_node_id IS NOT NULL" not in joined
    assert "1=1" in joined


def test_combined_count_covers_all_kinds_without_cst_filter():
    db = _RecordingDB()
    lep.count_code_entities(db, project_id="p1", entity_type=None, file_id=None)
    joined = "\n".join(db.sqls)
    assert "cst_node_id IS NOT NULL" not in joined
    # still unions the three entity kinds
    assert "FROM classes" in joined and "FROM functions" in joined and "FROM methods" in joined
