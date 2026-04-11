"""
Regression: fulltext_search must not fail on plain text with FTS5 syntax characters (e.g. "/").

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.database_client.client_api_search import (
    plain_query_to_fts5_match,
)


def test_plain_query_slash_splits_into_tokens_for_match():
    """Real query shape that used to raise fts5: syntax error near "/"."""
    assert (
        plain_query_to_fts5_match("SSL/mTLS tests package") == "SSL mTLS tests package"
    )


def test_plain_query_no_tokens_returns_none():
    assert plain_query_to_fts5_match("///") is None
    assert plain_query_to_fts5_match("   ") is None
    assert plain_query_to_fts5_match("") is None


def test_plain_query_preserves_word_tokens():
    assert plain_query_to_fts5_match("foo bar") == "foo bar"
    assert plain_query_to_fts5_match("MyClass") == "MyClass"


def test_plain_query_unicode_word_tokens():
    assert plain_query_to_fts5_match("тест код") == "тест код"
