"""
Tests for XPathFilter object.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from code_analysis.core.database_client.objects.xpath_filter import XPathFilter


class TestXPathFilterCreation:
    """Test XPathFilter object creation."""

    def test_create_simple_filter(self):
        """Test creating simple filter."""
        filter_obj = XPathFilter(selector="function[name='test']")
        assert filter_obj.selector == "function[name='test']"
        assert filter_obj.node_type is None
        assert filter_obj.name is None

    def test_create_filter_with_all_fields(self):
        """Test creating filter with all fields."""
        filter_obj = XPathFilter(
            selector="function[name='test']",
            node_type="function",
            name="test",
            qualname="test.test",
            start_line=10,
            end_line=20,
        )
        assert filter_obj.selector == "function[name='test']"
        assert filter_obj.node_type == "function"
        assert filter_obj.name == "test"
        assert filter_obj.qualname == "test.test"
        assert filter_obj.start_line == 10
        assert filter_obj.end_line == 20

    def test_create_filter_empty_selector(self):
        """Test creating filter with empty selector raises error."""
        with pytest.raises(ValueError, match="selector cannot be empty"):
            XPathFilter(selector="")

    def test_create_filter_invalid_selector(self):
        """Test creating filter with invalid selector raises error."""
        with pytest.raises(ValueError, match="Invalid selector syntax"):
            XPathFilter(selector="function[")


class TestXPathFilterSerialization:
    """Test XPathFilter serialization."""

    def test_to_dict_simple(self):
        """Test converting simple filter to dict."""
        filter_obj = XPathFilter(selector="function[name='test']")
        data = filter_obj.to_dict()
        assert data == {"selector": "function[name='test']"}

    def test_to_dict_with_all_fields(self):
        """Test converting filter with all fields to dict."""
        filter_obj = XPathFilter(
            selector="function[name='test']",
            node_type="function",
            name="test",
            qualname="test.test",
            start_line=10,
            end_line=20,
        )
        data = filter_obj.to_dict()
        assert data == {
            "selector": "function[name='test']",
            "node_type": "function",
            "name": "test",
            "qualname": "test.test",
            "start_line": 10,
            "end_line": 20,
        }

    def test_from_dict_simple(self):
        """Test creating filter from simple dict."""
        data = {"selector": "function[name='test']"}
        filter_obj = XPathFilter.from_dict(data)
        assert filter_obj.selector == "function[name='test']"
        assert filter_obj.node_type is None

    def test_from_dict_with_all_fields(self):
        """Test creating filter from dict with all fields."""
        data = {
            "selector": "function[name='test']",
            "node_type": "function",
            "name": "test",
            "qualname": "test.test",
            "start_line": 10,
            "end_line": 20,
        }
        filter_obj = XPathFilter.from_dict(data)
        assert filter_obj.selector == "function[name='test']"
        assert filter_obj.node_type == "function"
        assert filter_obj.name == "test"
        assert filter_obj.qualname == "test.test"
        assert filter_obj.start_line == 10
        assert filter_obj.end_line == 20

    def test_round_trip_serialization(self):
        """Test round-trip serialization."""
        original = XPathFilter(
            selector="class[name='Test']",
            node_type="class",
            name="Test",
            qualname="test.Test",
            start_line=5,
            end_line=15,
        )
        data = original.to_dict()
        restored = XPathFilter.from_dict(data)
        assert restored.selector == original.selector
        assert restored.node_type == original.node_type
        assert restored.name == original.name
        assert restored.qualname == original.qualname
        assert restored.start_line == original.start_line
        assert restored.end_line == original.end_line


class TestXPathFilterStringRepresentation:
    """Test XPathFilter string representation."""

    def test_str_simple(self):
        """Test string representation of simple filter."""
        filter_obj = XPathFilter(selector="function[name='test']")
        str_repr = str(filter_obj)
        assert "selector='function[name='test']'" in str_repr

    def test_str_with_all_fields(self):
        """Test string representation with all fields."""
        filter_obj = XPathFilter(
            selector="function[name='test']",
            node_type="function",
            name="test",
            qualname="test.test",
            start_line=10,
            end_line=20,
        )
        str_repr = str(filter_obj)
        assert "selector='function[name='test']'" in str_repr
        assert "node_type='function'" in str_repr
        assert "name='test'" in str_repr
        assert "qualname='test.test'" in str_repr
        assert "start_line=10" in str_repr
        assert "end_line=20" in str_repr
