"""
Regression tests for compose_cst_module node_id support on methods.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from code_analysis.core.cst_module.patcher import apply_replace_ops
from code_analysis.core.cst_module.models import ReplaceOp, Selector
from code_analysis.cst_query import query_source


class TestCSTComposeNodeIdMethod:
    """Ensure node_id replacements work for method/function/class nodes (not only stmt)."""

    @pytest.mark.parametrize(
        "selector, expected_substring",
        [
            ('class[name="A"] method[name="m"]', "return 2"),
            ('function[name="f"]', "return 3"),
        ],
    )
    def test_node_id_replacement_for_method_and_function(
        self, selector: str, expected_substring: str
    ) -> None:
        source = (
            "class A:\n"
            "    def m(self) -> int:\n"
            "        return 1\n"
            "\n"
            "def f() -> int:\n"
            "    return 1\n"
        )

        matches = query_source(source, selector, include_code=False)
        assert len(matches) == 1
        node_id = matches[0].node_id
        assert node_id

        if "method" in matches[0].kind:
            new_code = "def m(self) -> int:\n" "    return 2\n"
        else:
            new_code = "def f() -> int:\n" "    return 3\n"

        op = ReplaceOp(
            selector=Selector(kind="node_id", node_id=node_id), new_code=new_code
        )
        new_source, stats = apply_replace_ops(source, [op])

        assert expected_substring in new_source
        assert stats["replaced"] == 1
