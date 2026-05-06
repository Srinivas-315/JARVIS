"""
JARVIS — utils/safe_api.py
Safe API response handling — prevents crashes from malformed/incomplete responses.

Provides utilities to:
  - Safely extract nested values from JSON responses without KeyError/IndexError
  - Validate HTTP status codes before parsing JSON
  - Gracefully handle API failures
"""

from utils.logger import log
from typing import Any, Optional


def safe_json_extract(
    data: dict,
    *keys,
    default: Any = None
) -> Any:
    """
    Safely extract nested values from a dictionary.

    Navigates through multiple levels without raising KeyError/IndexError.
    Returns default value if any key doesn't exist or index is out of range.

    Args:
        data: Dictionary to extract from
        *keys: Sequence of keys/indices to navigate
        default: Value to return if extraction fails

    Returns:
        The nested value, or default if path doesn't exist

    Example:
        >>> response = {"candidates": [{"content": {"parts": ["answer"]}}]}
        >>> safe_json_extract(response, "candidates", 0, "content", "parts", 0)
        "answer"
        >>> safe_json_extract(response, "candidates", 1, "content")  # Out of range
        None
    """
    current = data

    try:
        for key in keys:
            if isinstance(current, dict):
                current = current[key]  # KeyError if key missing
            elif isinstance(current, (list, tuple)):
                current = current[int(key)]  # IndexError if out of range
            else:
                return default  # Can't navigate further
        return current
    except (KeyError, IndexError, TypeError, ValueError):
        return default


def validate_status(
    response,
    expected: int = 200
) -> bool:
    """
    Check if HTTP response status code matches expected value.

    Logs the status code and response reason if it doesn't match.

    Args:
        response: requests.Response object
        expected: Expected status code (default 200)

    Returns:
        True if status matches, False otherwise
    """
    if response.status_code != expected:
        log.error(
            f"API error: Status {response.status_code} {response.reason} "
            f"(expected {expected})"
        )
        return False
    return True


def safe_json_response(
    response,
    *keys,
    expected_status: int = 200,
    default: Any = None
) -> Any:
    """
    Safely extract data from an API response in one call.

    Validates status code, parses JSON, and extracts nested value.
    Returns default if any step fails.

    Args:
        response: requests.Response object
        *keys: Keys to navigate in the JSON response
        expected_status: Expected HTTP status code
        default: Value to return if anything fails

    Returns:
        The extracted value, or default on failure

    Example:
        >>> response = requests.get("https://api.example.com/data")
        >>> weather = safe_json_response(response, "data", "temperature", default={})
    """
    if not validate_status(response, expected_status):
        return default

    try:
        json_data = response.json()
        return safe_json_extract(json_data, *keys, default=default)
    except Exception as e:
        log.error(f"Failed to parse JSON response: {e}")
        return default


def get_first_match(
    data: list,
    condition=None,
    default: Any = None
) -> Any:
    """
    Find first item in list matching condition.

    Safely gets first matching item without IndexError.

    Args:
        data: List to search
        condition: Function that returns True for matching items
        default: Value if no match found

    Returns:
        First matching item or default

    Example:
        >>> items = [{"name": "Chrome"}, {"name": "Firefox"}]
        >>> get_first_match(items, lambda x: x["name"] == "Chrome")
        {"name": "Chrome"}
    """
    if not isinstance(data, list):
        return default

    try:
        if condition is None:
            return data[0] if data else default

        for item in data:
            if condition(item):
                return item
        return default
    except Exception:
        return default
