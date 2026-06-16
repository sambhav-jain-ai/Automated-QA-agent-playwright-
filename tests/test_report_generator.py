"""Tests for the report_generator module."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.report_generator import generate_html_report


class TestGenerateHtmlReport:
    """Tests for generate_html_report function."""

    def test_basic_report_generation(self, tmp_path):
        """Test generating a report with minimal data."""
        # Temporarily override reports dir by monkeypatching
        import src.report_generator as rg
        original_line = None

        report = generate_html_report(
            session_id="test-session-001",
            phase1_result={
                "visited_urls": ["http://example.com", "http://example.com/login"],
                "discovered_buttons": ["Login", "Submit"],
                "generated_test_cases": [
                    {"name": "Login test", "steps": ["Go to login", "Enter creds"], "expected": "Dashboard shown"}
                ],
                "screenshots": [],
            },
            phase2_result=[
                {
                    "method": "GET",
                    "url": "http://example.com/api/users",
                    "status": 200,
                    "expected_status": 200,
                    "passed": True,
                    "duration_ms": 42,
                    "error": None,
                },
                {
                    "method": "POST",
                    "url": "http://example.com/api/users",
                    "status": 500,
                    "expected_status": 201,
                    "passed": False,
                    "duration_ms": 100,
                    "error": "Internal Server Error",
                },
            ],
            phase3_result={
                "suggestions": ["1 endpoint returned 5xx errors."],
                "retry_plan": [
                    {"method": "POST", "endpoint": "/api/users", "suggested_url": "/api/v2/users", "reason": "Version mismatch"}
                ],
            },
            screenshots=[],
        )

        assert "<!DOCTYPE html>" in report
        assert "test-session-001" in report
        assert "Login" in report
        assert "http://example.com/api/users" in report
        assert "PASS" in report
        assert "FAIL" in report
        assert "AI Suggestions" in report
        assert "5xx errors" in report

    def test_empty_report(self):
        """Test generating a report with no data."""
        report = generate_html_report(session_id="empty-session")

        assert "<!DOCTYPE html>" in report
        assert "empty-session" in report
        assert "0%" in report or "0.0%" in report

    def test_report_saved_to_file(self):
        """Test that the report is saved to the reports directory."""
        session_id = "file-save-test"
        report = generate_html_report(session_id=session_id)

        report_path = f"/projects/sandbox/playwright-autotest/reports/{session_id}.html"
        assert os.path.isfile(report_path)

        with open(report_path, "r") as f:
            content = f.read()
        assert content == report

        # Cleanup
        os.remove(report_path)

    def test_html_escaping(self):
        """Test that HTML special characters are escaped."""
        report = generate_html_report(
            session_id="xss-test",
            phase2_result=[
                {
                    "method": "GET",
                    "url": "http://example.com/api?foo=<script>alert(1)</script>",
                    "status": 200,
                    "expected_status": 200,
                    "passed": True,
                    "duration_ms": 10,
                    "error": None,
                },
            ],
        )

        # The raw <script> tag should NOT appear
        assert "<script>alert(1)</script>" not in report
        # But the escaped version should
        assert "&lt;script&gt;" in report

        # Cleanup
        report_path = "/projects/sandbox/playwright-autotest/reports/xss-test.html"
        if os.path.exists(report_path):
            os.remove(report_path)
