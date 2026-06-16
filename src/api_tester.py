"""API testing module using Python stdlib urllib.request.

Executes HTTP requests against endpoints and captures results.
"""

import json
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Callable, Optional


def run_api_tests(
    endpoints: list[dict[str, Any]],
    base_url: str,
    session_log_fn: Optional[Callable[[str], None]] = None,
) -> list[dict[str, Any]]:
    """Run API tests against the given endpoints.

    Args:
        endpoints: List of endpoint dicts with keys: method, url, headers, body, expected_status
        base_url: Base URL to prepend to relative URLs
        session_log_fn: Optional callback for logging progress

    Returns:
        List of result dicts with keys: endpoint, method, url, status, expected_status,
        passed, response_excerpt, duration_ms, error
    """
    results: list[dict[str, Any]] = []

    def log(msg: str) -> None:
        if session_log_fn:
            session_log_fn(msg)

    for i, ep in enumerate(endpoints):
        method = ep.get("method", "GET").upper()
        url = ep.get("url", "")
        headers = ep.get("headers", {}) or {}
        body = ep.get("body")
        expected_status = ep.get("expected_status", 200)

        # Resolve relative URLs
        if url and not url.startswith("http"):
            # Strip leading slash for join
            base = base_url.rstrip("/")
            path = url if url.startswith("/") else "/" + url
            url = base + path

        log(f"[API Test {i+1}/{len(endpoints)}] {method} {url}")

        result: dict[str, Any] = {
            "endpoint": ep.get("url", ""),
            "method": method,
            "url": url,
            "status": None,
            "expected_status": expected_status,
            "passed": False,
            "response_excerpt": "",
            "duration_ms": 0,
            "error": None,
        }

        try:
            # Prepare request body
            data: Optional[bytes] = None
            if body is not None:
                if isinstance(body, (dict, list)):
                    data = json.dumps(body).encode("utf-8")
                    if "Content-Type" not in headers:
                        headers["Content-Type"] = "application/json"
                elif isinstance(body, str):
                    data = body.encode("utf-8")

            req = urllib.request.Request(url, data=data, method=method)
            for key, value in headers.items():
                req.add_header(key, value)

            start_time = time.time()
            with urllib.request.urlopen(req, timeout=30) as response:
                elapsed = (time.time() - start_time) * 1000
                status_code = response.status
                body_bytes = response.read(4096)
                response_text = body_bytes.decode("utf-8", errors="replace")

            result["status"] = status_code
            result["duration_ms"] = round(elapsed, 2)
            result["response_excerpt"] = response_text[:500]
            result["passed"] = status_code == expected_status

        except urllib.error.HTTPError as e:
            elapsed = 0
            result["status"] = e.code
            result["duration_ms"] = round(elapsed, 2)
            try:
                error_body = e.read(2048).decode("utf-8", errors="replace")
                result["response_excerpt"] = error_body[:500]
            except Exception:
                result["response_excerpt"] = ""
            result["passed"] = e.code == expected_status
            if not result["passed"]:
                result["error"] = f"HTTP {e.code}: {e.reason}"

        except urllib.error.URLError as e:
            result["error"] = f"Connection error: {e.reason}"
            result["duration_ms"] = 0

        except Exception as e:
            result["error"] = f"Error: {str(e)}"
            result["duration_ms"] = 0

        status_str = "PASS" if result["passed"] else "FAIL"
        log(f"  -> {status_str} (status={result['status']}, {result['duration_ms']}ms)")
        results.append(result)

    return results


def deep_crawler(
    base_url: str,
    session_log_fn: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """Crawl the base URL and discover all linked URLs from responses.

    Makes GET requests and extracts URLs from JSON responses or HTML-like content.

    Args:
        base_url: The starting URL to crawl
        session_log_fn: Optional callback for logging progress

    Returns:
        List of discovered URLs
    """
    discovered_urls: list[str] = []
    visited: set[str] = set()
    to_visit: list[str] = [base_url.rstrip("/")]

    def log(msg: str) -> None:
        if session_log_fn:
            session_log_fn(msg)

    max_pages = 20  # Safety limit

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        log(f"[Deep Crawler] Visiting: {url}")

        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as response:
                body = response.read(65536).decode("utf-8", errors="replace")

            # Extract URLs from response
            urls_found = _extract_urls(body, base_url)
            for found_url in urls_found:
                if found_url not in visited and found_url not in discovered_urls:
                    discovered_urls.append(found_url)
                    # Only follow same-origin URLs
                    if found_url.startswith(base_url):
                        to_visit.append(found_url)

        except Exception as e:
            log(f"  -> Error crawling {url}: {e}")

    log(f"[Deep Crawler] Found {len(discovered_urls)} URLs total")
    return discovered_urls


def _extract_urls(body: str, base_url: str) -> list[str]:
    """Extract URLs from response body (JSON or HTML-like content)."""
    urls: list[str] = []
    base = base_url.rstrip("/")

    # Try to parse as JSON and look for URL-like values
    try:
        data = json.loads(body)
        _extract_urls_from_json(data, base, urls)
        return urls
    except (json.JSONDecodeError, ValueError):
        pass

    # Simple extraction of href and src attributes from HTML-like content
    import re
    pattern = re.compile(r'(?:href|src|action)=["\']([^"\']+)["\']', re.IGNORECASE)
    for match in pattern.finditer(body):
        found = match.group(1)
        if found.startswith("http"):
            urls.append(found)
        elif found.startswith("/"):
            urls.append(base + found)

    return urls


def _extract_urls_from_json(data: Any, base_url: str, urls: list[str]) -> None:
    """Recursively extract URL-like strings from JSON data."""
    if isinstance(data, str):
        if data.startswith("http"):
            urls.append(data)
        elif data.startswith("/") and len(data) > 1:
            urls.append(base_url + data)
    elif isinstance(data, dict):
        for value in data.values():
            _extract_urls_from_json(value, base_url, urls)
    elif isinstance(data, list):
        for item in data:
            _extract_urls_from_json(item, base_url, urls)
