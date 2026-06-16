"""Integration tests for the HTTP server."""

import http.server
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import create_server, AutoTestHandler


def _start_server():
    """Start the application server on a random port and return (server, port)."""
    server = create_server("127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Give the server a moment to start
    time.sleep(0.1)
    return server, port


class TestServerIntegration:
    """Integration tests that start the real server and exercise API endpoints."""

    def setup_method(self):
        self.server, self.port = _start_server()
        self.base_url = f"http://127.0.0.1:{self.port}"

    def teardown_method(self):
        self.server.shutdown()

    def test_root_serves_index_html(self):
        """GET / should serve the index.html page."""
        url = f"{self.base_url}/"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")
            assert "<html" in body.lower() or "<!doctype" in body.lower()

    def test_static_css(self):
        """GET /static/style.css should serve the CSS file."""
        url = f"{self.base_url}/static/style.css"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            assert "text/css" in resp.headers.get("Content-Type", "")
            assert len(body) > 0

    def test_static_js(self):
        """GET /static/app.js should serve the JavaScript file."""
        url = f"{self.base_url}/static/app.js"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            assert len(body) > 0

    def test_api_start_missing_frontend_url(self):
        """POST /api/start without frontendUrl returns 400."""
        url = f"{self.base_url}/api/start"
        data = json.dumps({"backendUrl": "http://example.com"}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            assert False, "Expected HTTP error"
        except urllib.error.HTTPError as e:
            assert e.code == 400
            resp_body = json.loads(e.read().decode("utf-8"))
            assert "error" in resp_body
            assert "frontendUrl" in resp_body["error"]

    def test_api_start_valid_request(self):
        """POST /api/start with valid data returns session info."""
        url = f"{self.base_url}/api/start"
        data = json.dumps({
            "frontendUrl": "http://example.com",
            "backendUrl": "http://example.com/api",
            "username": "user",
            "password": "pass",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            resp_body = json.loads(resp.read().decode("utf-8"))
            assert "sessionId" in resp_body
            assert resp_body["status"] == "started"
            assert len(resp_body["sessionId"]) > 0

    def test_api_start_with_custom_session_id(self):
        """POST /api/start with a custom sessionId uses it."""
        url = f"{self.base_url}/api/start"
        data = json.dumps({
            "frontendUrl": "http://example.com",
            "sessionId": "custom-test-session",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            resp_body = json.loads(resp.read().decode("utf-8"))
            assert resp_body["sessionId"] == "custom-test-session"

    def test_api_start_invalid_json(self):
        """POST /api/start with invalid JSON returns 400."""
        url = f"{self.base_url}/api/start"
        data = b"not json"
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            assert False, "Expected HTTP error"
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_api_otp_valid(self):
        """POST /api/otp with valid data returns confirmation."""
        # First start a session
        start_url = f"{self.base_url}/api/start"
        start_data = json.dumps({"frontendUrl": "http://example.com", "sessionId": "otp-test"}).encode("utf-8")
        req = urllib.request.Request(start_url, data=start_data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req)

        # Now submit OTP
        otp_url = f"{self.base_url}/api/otp"
        otp_data = json.dumps({"sessionId": "otp-test", "otp": "123456"}).encode("utf-8")
        req = urllib.request.Request(otp_url, data=otp_data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            resp_body = json.loads(resp.read().decode("utf-8"))
            assert resp_body["status"] == "otp_received"
            assert resp_body["sessionId"] == "otp-test"

    def test_api_otp_missing_fields(self):
        """POST /api/otp without required fields returns 400."""
        url = f"{self.base_url}/api/otp"
        data = json.dumps({"sessionId": ""}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            assert False, "Expected HTTP error"
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_404_for_unknown_get_path(self):
        """GET to an unknown path returns 404."""
        url = f"{self.base_url}/api/nonexistent"
        req = urllib.request.Request(url)
        try:
            urllib.request.urlopen(req)
            assert False, "Expected HTTP error"
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_404_for_unknown_post_path(self):
        """POST to an unknown path returns 404."""
        url = f"{self.base_url}/api/unknown"
        data = b"{}"
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            assert False, "Expected HTTP error"
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_cors_options(self):
        """OPTIONS request returns CORS headers."""
        url = f"{self.base_url}/api/start"
        req = urllib.request.Request(url, method="OPTIONS")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            assert resp.headers.get("Access-Control-Allow-Origin") == "*"

    def test_report_not_found(self):
        """GET /api/report/ for unknown session returns 404."""
        url = f"{self.base_url}/api/report/nonexistent-session-id"
        req = urllib.request.Request(url)
        try:
            urllib.request.urlopen(req)
            assert False, "Expected HTTP error"
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_report_existing(self):
        """GET /api/report/ for an existing report returns HTML."""
        # We know test-session-001.html exists from FEAT-002
        url = f"{self.base_url}/api/report/test-session-001"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")
            assert len(body) > 0

    def test_download_report_existing(self):
        """GET /api/download/report/ for an existing report returns file with Content-Disposition."""
        url = f"{self.base_url}/api/download/report/test-session-001"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")
            content_disp = resp.headers.get("Content-Disposition", "")
            assert "attachment" in content_disp
            assert "report_test-session-001.html" in content_disp
            assert len(body) > 0

    def test_download_report_not_found(self):
        """GET /api/download/report/ for unknown session returns 404."""
        url = f"{self.base_url}/api/download/report/nonexistent-session"
        req = urllib.request.Request(url)
        try:
            urllib.request.urlopen(req)
            assert False, "Expected HTTP error"
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_download_script_existing(self):
        """GET /api/download/script/ for a session with scripts returns file."""
        # We know crawl_custom-test-session.py exists
        url = f"{self.base_url}/api/download/script/custom-test-session"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            assert resp.status == 200
            content_disp = resp.headers.get("Content-Disposition", "")
            assert "attachment" in content_disp
            assert len(body) > 0

    def test_download_script_not_found(self):
        """GET /api/download/script/ for unknown session returns 404."""
        url = f"{self.base_url}/api/download/script/nonexistent-session"
        req = urllib.request.Request(url)
        try:
            urllib.request.urlopen(req)
            assert False, "Expected HTTP error"
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_list_downloads_existing(self):
        """GET /api/downloads/ for a session with report returns download list."""
        url = f"{self.base_url}/api/downloads/test-session-001"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            resp_body = json.loads(resp.read().decode("utf-8"))
            assert "downloads" in resp_body
            assert "sessionId" in resp_body
            assert resp_body["sessionId"] == "test-session-001"
            # Should have at least the report
            assert len(resp_body["downloads"]) >= 1
            report_entry = [d for d in resp_body["downloads"] if d["type"] == "report"]
            assert len(report_entry) == 1
            assert "/api/download/report/" in report_entry[0]["url"]

    def test_list_downloads_empty(self):
        """GET /api/downloads/ for unknown session returns empty downloads list."""
        url = f"{self.base_url}/api/downloads/nonexistent-session"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            resp_body = json.loads(resp.read().decode("utf-8"))
            assert resp_body["downloads"] == []

    def test_download_report_path_traversal(self):
        """GET /api/download/report/ with path traversal attempt is safe."""
        url = f"{self.base_url}/api/download/report/..%2F..%2Fetc%2Fpasswd"
        req = urllib.request.Request(url)
        try:
            urllib.request.urlopen(req)
            assert False, "Expected HTTP error"
        except urllib.error.HTTPError as e:
            assert e.code == 404
