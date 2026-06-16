"""AI module - rule-based mock for analyzing test failures and suggesting fixes.

This module simulates AI behavior using pattern matching and heuristics.
No external AI API calls are made.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
import textwrap


@dataclass
class AIAnalysis:
    """Analysis result from the AI module."""
    failure_groups: dict[str, list[dict]] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    retry_plan: list[dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0


class AIModule:
    """Rule-based AI mock that analyzes failures and suggests fixes."""

    # Error pattern categories
    ERROR_PATTERNS = {
        "connection_refused": ["Connection refused", "ECONNREFUSED", "connection error"],
        "not_found": ["404", "Not Found", "not found"],
        "unauthorized": ["401", "Unauthorized", "unauthorized", "forbidden"],
        "server_error": ["500", "Internal Server Error", "server error"],
        "timeout": ["timeout", "Timeout", "timed out", "ETIMEDOUT"],
    }

    def analyze_failures(
        self,
        test_results: list[dict[str, Any]],
        deep_crawler_urls: Optional[list[str]] = None,
        xlsx_data: Optional[list[dict]] = None,
    ) -> AIAnalysis:
        """Analyze test failures and produce suggestions.

        Args:
            test_results: List of test result dicts from api_tester
            deep_crawler_urls: URLs discovered by deep crawler
            xlsx_data: Raw data from xlsx parsing

        Returns:
            AIAnalysis with grouped failures, suggestions, and retry plan
        """
        deep_crawler_urls = deep_crawler_urls or []
        xlsx_data = xlsx_data or []

        analysis = AIAnalysis()

        # Separate failures
        failures = [r for r in test_results if not r.get("passed", False)]
        if not failures:
            analysis.suggestions.append("All tests passed. No failures to analyze.")
            analysis.confidence_score = 1.0
            return analysis

        # Group failures by error type
        analysis.failure_groups = self._group_failures(failures)

        # Generate suggestions based on patterns
        analysis.suggestions = self._generate_suggestions(analysis.failure_groups)

        # Build retry plan by matching crawler URLs to failed endpoints
        analysis.retry_plan = self._build_retry_plan(failures, deep_crawler_urls)

        # Calculate confidence score
        total_tests = len(test_results)
        passed_tests = total_tests - len(failures)
        analysis.confidence_score = round(passed_tests / max(total_tests, 1), 2)

        return analysis

    def generate_playwright_script(
        self,
        retry_plan: list[dict[str, Any]],
        frontend_url: str,
        session_id: str = "default",
    ) -> str:
        """Generate a Playwright Python script based on the retry plan.

        Args:
            retry_plan: List of endpoint dicts with suggested corrections
            frontend_url: Base frontend URL
            session_id: Session identifier

        Returns:
            Complete Playwright Python script as a string
        """
        test_steps = []
        for i, plan_item in enumerate(retry_plan):
            method = plan_item.get("method", "GET")
            url = plan_item.get("suggested_url", plan_item.get("endpoint", ""))
            reason = plan_item.get("reason", "AI-suggested retry")
            test_steps.append(
                f'    # Step {i+1}: {reason}\n'
                f'    print("[Phase 3] Testing: {method} {url}")\n'
                f'    response = await page.request.fetch("{url}", method="{method}")\n'
                f'    assert response.ok, f"Expected success but got {{response.status}}"\n'
            )

        steps_code = "\n".join(test_steps) if test_steps else '    print("[Phase 3] No retry steps to execute")'

        script = textwrap.dedent(f'''\
            """Auto-generated Phase 3 Playwright script (AI-guided retry)
            Session: {session_id}

            This script retries failed endpoints using AI-suggested corrections.
            Run with: python -m playwright run this_script.py
            """

            import asyncio
            from playwright.async_api import async_playwright


            async def main():
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    context = await browser.new_context()
                    page = await context.new_page()

                    # Navigate to frontend
                    await page.goto("{frontend_url}")
                    await page.wait_for_timeout(2000)

                    print("[Phase 3] Starting AI-guided retry tests...")

            {steps_code}

                    print("[Phase 3] All retry tests complete.")
                    await context.close()
                    await browser.close()


            if __name__ == "__main__":
                asyncio.run(main())
        ''')
        return script

    def _group_failures(self, failures: list[dict]) -> dict[str, list[dict]]:
        """Group failures by detected error pattern."""
        groups: dict[str, list[dict]] = {}

        for failure in failures:
            error = failure.get("error", "") or ""
            status = failure.get("status")
            category = "unknown"

            # Check by status code first
            if status == 404:
                category = "not_found"
            elif status == 401 or status == 403:
                category = "unauthorized"
            elif status is not None and status >= 500:
                category = "server_error"
            else:
                # Check error message patterns
                for cat, patterns in self.ERROR_PATTERNS.items():
                    if any(p.lower() in error.lower() for p in patterns):
                        category = cat
                        break

            if category not in groups:
                groups[category] = []
            groups[category].append(failure)

        return groups

    def _generate_suggestions(self, failure_groups: dict[str, list[dict]]) -> list[str]:
        """Generate human-readable suggestions based on failure groups."""
        suggestions: list[str] = []

        if "connection_refused" in failure_groups:
            count = len(failure_groups["connection_refused"])
            suggestions.append(
                f"{count} endpoint(s) returned connection errors. "
                "The backend server may not be running or the base URL may be incorrect."
            )

        if "not_found" in failure_groups:
            count = len(failure_groups["not_found"])
            endpoints = [f.get("url", "unknown") for f in failure_groups["not_found"][:3]]
            suggestions.append(
                f"{count} endpoint(s) returned 404 Not Found. "
                f"Check these URLs: {', '.join(endpoints)}. "
                "The API paths may have changed or are prefixed differently."
            )

        if "unauthorized" in failure_groups:
            count = len(failure_groups["unauthorized"])
            suggestions.append(
                f"{count} endpoint(s) returned 401/403. "
                "Authentication may be required. Add auth headers or login first."
            )

        if "server_error" in failure_groups:
            count = len(failure_groups["server_error"])
            suggestions.append(
                f"{count} endpoint(s) returned 5xx errors. "
                "The server is encountering internal errors on these routes."
            )

        if "timeout" in failure_groups:
            count = len(failure_groups["timeout"])
            suggestions.append(
                f"{count} endpoint(s) timed out. "
                "Consider increasing timeout or checking server responsiveness."
            )

        return suggestions

    def _build_retry_plan(
        self,
        failures: list[dict],
        deep_crawler_urls: list[str],
    ) -> list[dict[str, Any]]:
        """Build a retry plan matching failed endpoints against discovered URLs.

        Tries to find correct URLs in the deep crawler results that match
        the failed endpoint paths.
        """
        retry_plan: list[dict[str, Any]] = []

        for failure in failures:
            failed_url = failure.get("url", "")
            method = failure.get("method", "GET")
            endpoint_path = failure.get("endpoint", "")

            # Try to find a matching URL from crawler results
            suggested_url = self._find_matching_url(endpoint_path, deep_crawler_urls)

            if suggested_url:
                reason = f"Matched crawler URL '{suggested_url}' to failed path '{endpoint_path}'"
            else:
                suggested_url = failed_url
                reason = f"No alternative found; retrying original URL"

            retry_plan.append({
                "endpoint": endpoint_path,
                "method": method,
                "original_url": failed_url,
                "suggested_url": suggested_url,
                "reason": reason,
            })

        return retry_plan

    def _find_matching_url(self, endpoint_path: str, crawler_urls: list[str]) -> Optional[str]:
        """Try to find a crawler URL that matches the failed endpoint path."""
        if not endpoint_path or not crawler_urls:
            return None

        # Extract the path part from the endpoint
        path_parts = endpoint_path.strip("/").split("/")
        if not path_parts:
            return None

        # Look for the last segment match
        last_segment = path_parts[-1].lower()

        best_match: Optional[str] = None
        best_score = 0

        for url in crawler_urls:
            url_lower = url.lower()
            score = 0

            # Check if last path segment appears in the URL
            if last_segment in url_lower:
                score += 2

            # Check for partial path match
            for part in path_parts:
                if part.lower() in url_lower:
                    score += 1

            if score > best_score:
                best_score = score
                best_match = url

        return best_match if best_score >= 2 else None
