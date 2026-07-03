"""
GitHub HTTP API request helper.

Low-level HTTP transport for the GitHub command block (C-018 GithubBlock,
layer github_http_api). Executes one authenticated request against the
GitHub REST API and returns a uniform (data, status, error_code) result.
Every GitHub operation command imports github_api_request() from this
module instead of using urllib directly.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

GITHUB_API_BASE_URL = "https://api.github.com"


def github_api_request(
    method: str,
    path: str,
    headers: Dict[str, str],
    *,
    query: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 30,
) -> Tuple[Optional[Any], Optional[int], Optional[str]]:
    """
    Execute one HTTP request against the GitHub REST API.

    Builds the full URL from GITHUB_API_BASE_URL joined with path, optionally
    appends a URL-encoded query string, sends the request with the given
    method, headers, and an optional JSON-serialized body, and parses a JSON
    response body when the response is not empty.

    Args:
        method: HTTP method string, one of "GET", "POST", "PATCH", "PUT".
        path: Path appended to GITHUB_API_BASE_URL, starting with "/",
            e.g. "/repos/owner/name".
        headers: Request headers, the dict returned as the first element of
            resolve_github_auth() from code_analysis.core.github_auth.
        query: Optional mapping of query string parameter names to values.
        json_body: Optional JSON-serializable mapping sent as the request
            body for POST/PATCH/PUT; when provided, Content-Type
            application/json is added to the outgoing request headers.
        timeout_seconds: Socket timeout in seconds applied to the request.

    Returns:
        A 3-tuple (data, status, error_code):
        - On a 2xx response with a non-empty JSON body: (parsed_body,
          status_code, None).
        - On a 2xx response with an empty body: (None, status_code, None).
        - On a non-2xx HTTP response: (parsed_error_body_or_None,
          status_code, "GITHUB_API_ERROR").
        - On a network failure (connection error, timeout, DNS failure,
          or any other transport-level error): (None, None,
          "GITHUB_REQUEST_FAILED").
    """
    url = GITHUB_API_BASE_URL + path
    if query:
        url = url + "?" + urllib.parse.urlencode(query)
    request_headers: Dict[str, str] = dict(headers)
    data_bytes: Optional[bytes] = None
    if json_body is not None:
        data_bytes = json.dumps(json_body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=data_bytes,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = response.getcode()
            raw_body = response.read()
            if not raw_body:
                return (None, status_code, None)
            return (json.loads(raw_body.decode("utf-8")), status_code, None)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        raw_body = exc.read()
        parsed_body: Optional[Any] = None
        if raw_body:
            try:
                parsed_body = json.loads(raw_body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                parsed_body = None
        logger.warning(
            "GitHub API HTTP error %s for %s %s", status_code, method, path
        )
        return (parsed_body, status_code, "GITHUB_API_ERROR")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("GitHub API request failed for %s %s: %s", method, path, exc)
        return (None, None, "GITHUB_REQUEST_FAILED")


def github_timeout_seconds_from_config(config_data: Dict[str, Any]) -> int:
    """
    Read the configured GitHub API request timeout in seconds.

    Looks at code_analysis.github.timeout_seconds in config_data. Returns
    30 when config_data is not a dict, the code_analysis section is not a
    dict, the github section is not a dict, or the key is absent.

    Args:
        config_data: Full config dict (e.g. from BaseMCPCommand._get_raw_config()).

    Returns:
        The configured timeout in seconds, or 30 as the default.
    """
    if not isinstance(config_data, dict):
        return 30
    code_analysis_section = config_data.get("code_analysis")
    if not isinstance(code_analysis_section, dict):
        return 30
    github_section = code_analysis_section.get("github")
    if not isinstance(github_section, dict):
        return 30
    value = github_section.get("timeout_seconds", 30)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 30
