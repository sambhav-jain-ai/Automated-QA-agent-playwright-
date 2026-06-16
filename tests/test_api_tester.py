"""Tests for the api_tester module."""

import http.server
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api_tester import run_api_tests, deep_crawler


class MockHandler(http.server.BaseHTTPRequestHandler):
    """Simple mock HTTP server handler for testing."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/api/users":
            body = json.dumps([{"id": 1, "name": "Alice"}]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/health":
            body = json.dumps({"status": "ok"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/links":
            body = json.dumps({
                "links": ["/api/users", "/api/health", "/api/settings"]
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body_data = self.rfile.read(content_length)
        if self.path == "/api/users":
            response = json.dumps({"id": 2, "name": "Created"}).encode()
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()


def _start_mock_server():
    """Start a mock server on a random port and return (server, port)."""
    server = http.server.HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


class TestRunApiTests:
    """Tests for the run_api_tests function."""

    def setup_method(self):
        self.server, self.port = _start_mock_server()
        self.base_url = f"http://127.0.0.1:{self.port}"

    def teardown_method(self):
        self.server.shutdown()

    def test_successful_get(self):
        """Test a successful GET request."""
        endpoints = [
            {"method": "GET", "url": "/api/users", "headers": {}, "body": None, "expected_status": 200}
        ]
        logs = []
        results = run_api_tests(endpoints, self.base_url, session_log_fn=logs.append)

        assert len(results) == 1
        assert results[0]["passed"] is True
        assert results[0]["status"] == 200
        assert results[0]["error"] is None
        assert results[0]["duration_ms"] > 0

    def test_successful_post(self):
        """Test a successful POST request."""
        endpoints = [
            {
                "method": "POST",
                "url": "/api/users",
                "headers": {"Content-Type": "application/json"},
                "body": {"name": "test"},
                "expected_status": 201,
            }
        ]
        results = run_api_tests(endpoints, self.base_url)

        assert len(results) == 1
        assert results[0]["passed"] is True
        assert results[0]["status"] == 201

    def test_expected_404(self):
        """Test that expected 404 is marked as passed."""
        endpoints = [
            {"method": "GET", "url": "/nonexistent", "headers": {}, "body": None, "expected_status": 404}
        ]
        results = run_api_tests(endpoints, self.base_url)

        assert len(results) == 1
        assert results[0]["passed"] is True
        assert results[0]["status"] == 404

    def test_unexpected_404(self):
        """Test that unexpected 404 is marked as failed."""
        endpoints = [
            {"method": "GET", "url": "/nonexistent", "headers": {}, "body": None, "expected_status": 200}
        ]
        results = run_api_tests(endpoints, self.base_url)

        assert len(results) == 1
        assert results[0]["passed"] is False
        assert results[0]["status"] == 404

    def test_connection_error(self):
        """Test handling of connection errors."""
        endpoints = [
            {"method": "GET", "url": "http://127.0.0.1:1/nope", "headers": {}, "body": None, "expected_status": 200}
        ]
        results = run_api_tests(endpoints, "http://127.0.0.1:1")

        assert len(results) == 1
        assert results[0]["passed"] is False
        assert results[0]["error"] is not None

    def test_multiple_endpoints(self):
        """Test running multiple endpoints."""
        endpoints = [
            {"method": "GET", "url": "/api/users", "headers": {}, "body": None, "expected_status": 200},
            {"method": "GET", "url": "/api/health", "headers": {}, "body": None, "expected_status": 200},
            {"method": "GET", "url": "/missing", "headers": {}, "body": None, "expected_status": 200},
        ]
        results = run_api_tests(endpoints, self.base_url)

        assert len(results) == 3
        assert results[0]["passed"] is True
        assert results[1]["passed"] is True
        assert results[2]["passed"] is False


class TestDeepCrawler:
    """Tests for the deep_crawler function."""

    def setup_method(self):
        self.server, self.port = _start_mock_server()
        self.base_url = f"http://127.0.0.1:{self.port}"

    def teardown_method(self):
        self.server.shutdown()

    def test_discovers_urls(self):
        """Test that the deep crawler discovers URLs from JSON responses."""
        logs = []
        urls = deep_crawler(f"{self.base_url}/api/links", session_log_fn=logs.append)

        # Should discover the relative URLs from the JSON response
        assert len(urls) > 0
        assert len(logs) > 0
