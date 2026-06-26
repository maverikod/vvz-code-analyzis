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
    """Verify test plain query no tokens returns none."""
    assert plain_query_to_fts5_match("///") is None
    assert plain_query_to_fts5_match("   ") is None
    assert plain_query_to_fts5_match("") is None


def test_plain_query_preserves_word_tokens():
    """Verify test plain query preserves word tokens."""
    assert plain_query_to_fts5_match("foo bar") == "foo bar"
    assert plain_query_to_fts5_match("MyClass") == "MyClass"


def test_plain_query_unicode_word_tokens():
    """Verify test plain query unicode word tokens."""
    assert plain_query_to_fts5_match("тест код") == "тест код"


def test_plain_query_bogus_fts_column_colon_becomes_tokens():
    """FTS5 treats 'name:term' as column filter; unknown columns raise 'no such column'."""
    assert plain_query_to_fts5_match("proxy:adapter") == "proxy adapter"
    assert plain_query_to_fts5_match("mcp:proxy") == "mcp proxy"


def test_plain_query_allowed_fts_columns_preserved():
    """Verify test plain query allowed fts columns preserved."""
    assert plain_query_to_fts5_match("content:foo") == "content:foo"
    assert plain_query_to_fts5_match("entity_name:bar") == "entity_name:bar"


def test_plain_query_hyphenated_package_name_splits_tokens():
    """Regression: mcp-proxy-adapter must not hit FTS5 bogus column errors."""
    assert plain_query_to_fts5_match("mcp-proxy-adapter") == "mcp proxy adapter"
