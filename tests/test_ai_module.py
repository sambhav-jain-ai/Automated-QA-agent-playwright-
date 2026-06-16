"""Tests for the ai_module module."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai_module import AIModule, AIAnalysis


class TestAnalyzeFailures:
    """Tests for AIModule.analyze_failures."""

    def setup_method(self):
        self.ai = AIModule()

    def test_no_failures(self):
        """When all tests pass, suggestions say so and confidence is 1.0."""
        results = [
            {"url": "/api/users", "method": "GET", "status": 200, "passed": True, "error": None},
            {"url": "/api/health", "method": "GET", "status": 200, "passed": True, "error": None},
        ]
        analysis = self.ai.analyze_failures(results)

        assert isinstance(analysis, AIAnalysis)
        assert analysis.confidence_score == 1.0
        assert len(analysis.suggestions) == 1
        assert "All tests passed" in analysis.suggestions[0]
        assert analysis.failure_groups == {}
        assert analysis.retry_plan == []

    def test_404_failures_grouped(self):
        """404 failures are grouped under 'not_found' category."""
        results = [
            {"url": "/api/users", "method": "GET", "status": 200, "passed": True, "error": None},
            {"url": "/api/missing", "method": "GET", "status": 404, "passed": False, "error": "Not Found", "endpoint": "/api/missing"},
            {"url": "/api/gone", "method": "GET", "status": 404, "passed": False, "error": "Not Found", "endpoint": "/api/gone"},
        ]
        analysis = self.ai.analyze_failures(results)

        assert "not_found" in analysis.failure_groups
        assert len(analysis.failure_groups["not_found"]) == 2
        assert analysis.confidence_score == round(1 / 3, 2)

    def test_500_failures_grouped(self):
        """Server errors (5xx) are grouped under 'server_error' category."""
        results = [
            {"url": "/api/crash", "method": "POST", "status": 500, "passed": False, "error": "Internal Server Error", "endpoint": "/api/crash"},
            {"url": "/api/fail", "method": "GET", "status": 502, "passed": False, "error": "Bad Gateway", "endpoint": "/api/fail"},
        ]
        analysis = self.ai.analyze_failures(results)

        assert "server_error" in analysis.failure_groups
        assert len(analysis.failure_groups["server_error"]) == 2

    def test_connection_refused_grouped(self):
        """Connection errors are grouped under 'connection_refused' category."""
        results = [
            {"url": "/api/down", "method": "GET", "status": None, "passed": False, "error": "Connection refused", "endpoint": "/api/down"},
        ]
        analysis = self.ai.analyze_failures(results)

        assert "connection_refused" in analysis.failure_groups
        assert len(analysis.failure_groups["connection_refused"]) == 1

    def test_timeout_grouped(self):
        """Timeout errors are grouped under 'timeout' category."""
        results = [
            {"url": "/api/slow", "method": "GET", "status": None, "passed": False, "error": "Request timed out", "endpoint": "/api/slow"},
        ]
        analysis = self.ai.analyze_failures(results)

        assert "timeout" in analysis.failure_groups
        assert len(analysis.failure_groups["timeout"]) == 1

    def test_unauthorized_grouped(self):
        """401/403 errors are grouped under 'unauthorized' category."""
        results = [
            {"url": "/api/admin", "method": "GET", "status": 401, "passed": False, "error": "Unauthorized", "endpoint": "/api/admin"},
            {"url": "/api/secret", "method": "GET", "status": 403, "passed": False, "error": "Forbidden", "endpoint": "/api/secret"},
        ]
        analysis = self.ai.analyze_failures(results)

        assert "unauthorized" in analysis.failure_groups
        assert len(analysis.failure_groups["unauthorized"]) == 2

    def test_mixed_failures_generate_suggestions(self):
        """Mixed failure types produce multiple suggestions."""
        results = [
            {"url": "/api/ok", "method": "GET", "status": 200, "passed": True, "error": None},
            {"url": "/api/missing", "method": "GET", "status": 404, "passed": False, "error": "Not Found", "endpoint": "/api/missing"},
            {"url": "/api/crash", "method": "POST", "status": 500, "passed": False, "error": "Server Error", "endpoint": "/api/crash"},
            {"url": "/api/slow", "method": "GET", "status": None, "passed": False, "error": "timed out", "endpoint": "/api/slow"},
        ]
        analysis = self.ai.analyze_failures(results)

        # Should have suggestions for each failure type
        assert len(analysis.suggestions) >= 3
        # Confidence: 1 passed out of 4 total
        assert analysis.confidence_score == 0.25

    def test_suggestions_mention_urls_for_not_found(self):
        """Suggestions for 404 errors mention the failing URLs."""
        results = [
            {"url": "http://example.com/api/users", "method": "GET", "status": 404, "passed": False, "error": "Not Found", "endpoint": "/api/users"},
        ]
        analysis = self.ai.analyze_failures(results)

        found_suggestion = [s for s in analysis.suggestions if "/api/users" in s]
        assert len(found_suggestion) > 0

    def test_retry_plan_with_crawler_urls(self):
        """Retry plan matches failed endpoints against deep crawler URLs."""
        results = [
            {"url": "http://example.com/api/users", "method": "GET", "status": 404, "passed": False, "error": "Not Found", "endpoint": "/api/users"},
        ]
        crawler_urls = [
            "http://example.com/api/v2/users",
            "http://example.com/api/health",
        ]
        analysis = self.ai.analyze_failures(results, deep_crawler_urls=crawler_urls)

        assert len(analysis.retry_plan) == 1
        plan_item = analysis.retry_plan[0]
        assert plan_item["endpoint"] == "/api/users"
        # Should suggest the crawler URL that matches
        assert plan_item["suggested_url"] == "http://example.com/api/v2/users"
        assert "Matched" in plan_item["reason"]

    def test_retry_plan_no_match_uses_original(self):
        """When no crawler URL matches, retry plan uses the original URL."""
        results = [
            {"url": "http://example.com/api/obscure", "method": "GET", "status": 404, "passed": False, "error": "Not Found", "endpoint": "/api/obscure"},
        ]
        crawler_urls = [
            "http://example.com/totally/different/path",
        ]
        analysis = self.ai.analyze_failures(results, deep_crawler_urls=crawler_urls)

        assert len(analysis.retry_plan) == 1
        plan_item = analysis.retry_plan[0]
        assert plan_item["suggested_url"] == "http://example.com/api/obscure"
        assert "No alternative" in plan_item["reason"]

    def test_empty_test_results(self):
        """Empty test results produce no failures with confidence 1.0."""
        analysis = self.ai.analyze_failures([])

        assert analysis.confidence_score == 1.0
        assert "All tests passed" in analysis.suggestions[0]


class TestGeneratePlaywrightScript:
    """Tests for AIModule.generate_playwright_script."""

    def setup_method(self):
        self.ai = AIModule()

    def test_basic_script_generation(self):
        """Generated script contains the retry endpoints and key structure."""
        retry_plan = [
            {
                "endpoint": "/api/users",
                "method": "GET",
                "original_url": "http://example.com/api/users",
                "suggested_url": "http://example.com/api/v2/users",
                "reason": "Matched crawler URL",
            },
        ]
        script = self.ai.generate_playwright_script(
            retry_plan=retry_plan,
            frontend_url="http://example.com",
            session_id="test-session",
        )

        assert "http://example.com/api/v2/users" in script
        assert "test-session" in script
        assert "async def main" in script
        assert "playwright" in script.lower()
        assert "import asyncio" in script

    def test_empty_retry_plan(self):
        """Empty retry plan produces a script with no retry steps message."""
        script = self.ai.generate_playwright_script(
            retry_plan=[],
            frontend_url="http://example.com",
            session_id="empty-session",
        )

        assert "No retry steps" in script
        assert "empty-session" in script
        assert "async def main" in script

    def test_multiple_steps(self):
        """Multiple retry plan items produce numbered steps."""
        retry_plan = [
            {"endpoint": "/api/a", "method": "GET", "suggested_url": "http://example.com/api/a", "reason": "Retry A"},
            {"endpoint": "/api/b", "method": "POST", "suggested_url": "http://example.com/api/b", "reason": "Retry B"},
            {"endpoint": "/api/c", "method": "GET", "suggested_url": "http://example.com/api/c", "reason": "Retry C"},
        ]
        script = self.ai.generate_playwright_script(
            retry_plan=retry_plan,
            frontend_url="http://example.com",
            session_id="multi",
        )

        assert "Step 1" in script
        assert "Step 2" in script
        assert "Step 3" in script
        assert "http://example.com/api/a" in script
        assert "http://example.com/api/b" in script
        assert "http://example.com/api/c" in script
        assert "async def main" in script

    def test_script_uses_correct_methods(self):
        """Script includes the correct HTTP methods from the retry plan."""
        retry_plan = [
            {"endpoint": "/api/data", "method": "POST", "suggested_url": "http://example.com/api/data", "reason": "test"},
        ]
        script = self.ai.generate_playwright_script(
            retry_plan=retry_plan,
            frontend_url="http://example.com",
            session_id="methods-test",
        )

        assert 'method="POST"' in script
