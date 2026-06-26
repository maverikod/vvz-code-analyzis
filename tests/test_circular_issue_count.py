"""
register_circular_import_issues must count 2-node SCC cycles (a<->b).

find_cycles returns SCC node lists (no repeated closing node); the old len<3
threshold dropped genuine 2-file cycles. See TZ-CA-INDEX-INTEGRITY-001 C-3.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.integrity_analysis.issues_registry import (
    register_circular_import_issues,
)


class _DB:
    """Represent DB."""

    def __init__(self):
        """Initialize the instance."""
        self.issues = []

    def create_issue(self, issue):
        """Return create issue."""
        self.issues.append(issue)


def test_counts_two_node_cycle_and_drops_self_loop():
    """Verify test counts two node cycle and drops self loop."""
    db = _DB()
    cycles = [["fa", "fb"], ["fc"], ["fd", "fe", "ff"]]  # 2-node, self-loop, 3-node
    count = register_circular_import_issues(
        db, "proj", cycles, file_id_to_path={"fa": "a.py", "fb": "b.py"}
    )
    assert count == 2  # 2-node + 3-node counted; self-loop dropped
    assert len(db.issues) == 2
    # closure shown in description: a -> b -> a
    desc = db.issues[0].description
    assert desc.endswith("a.py -> b.py -> a.py")
