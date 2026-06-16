"""HTML report generator using Python stdlib.

Generates detailed test reports with inline CSS styling.
"""

import html
import os
from typing import Any, Optional


def generate_html_report(
    session_id: str,
    phase1_result: Optional[dict[str, Any]] = None,
    phase2_result: Optional[list[dict[str, Any]]] = None,
    phase3_result: Optional[dict[str, Any]] = None,
    screenshots: Optional[list[str]] = None,
) -> str:
    """Generate a complete HTML report for a test session.

    Args:
        session_id: Unique session identifier
        phase1_result: CrawlerResult as dict (visited_urls, discovered_buttons, etc.)
        phase2_result: List of API test result dicts
        phase3_result: AI analysis result as dict (retry_plan, suggestions, etc.)
        screenshots: List of screenshot file paths

    Returns:
        Complete HTML string with inline CSS
    """
    phase1_result = phase1_result or {}
    phase2_result = phase2_result or []
    phase3_result = phase3_result or {}
    screenshots = screenshots or []

    # Calculate summary stats
    total_api_tests = len(phase2_result)
    passed_api_tests = sum(1 for r in phase2_result if r.get("passed"))
    failed_api_tests = total_api_tests - passed_api_tests
    pass_rate = round((passed_api_tests / max(total_api_tests, 1)) * 100, 1)

    # Build HTML sections
    summary_html = _build_summary_section(
        total_api_tests, passed_api_tests, failed_api_tests, pass_rate, phase1_result
    )
    phase1_html = _build_phase1_section(phase1_result)
    phase2_html = _build_phase2_section(phase2_result)
    phase3_html = _build_phase3_section(phase3_result)
    screenshots_html = _build_screenshots_section(screenshots)

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Report - {html.escape(session_id)}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               line-height: 1.6; color: #333; background: #f5f7fa; padding: 2rem; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #1a1a2e; margin-bottom: 1rem; font-size: 1.8rem; }}
        h2 {{ color: #16213e; margin: 1.5rem 0 0.75rem; font-size: 1.3rem;
              border-bottom: 2px solid #0f3460; padding-bottom: 0.5rem; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                   gap: 1rem; margin: 1rem 0; }}
        .stat-card {{ background: white; border-radius: 8px; padding: 1.25rem;
                     box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }}
        .stat-card .value {{ font-size: 2rem; font-weight: bold; color: #0f3460; }}
        .stat-card .label {{ font-size: 0.85rem; color: #666; text-transform: uppercase; }}
        .stat-card.pass .value {{ color: #27ae60; }}
        .stat-card.fail .value {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0;
                background: white; border-radius: 8px; overflow: hidden;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #16213e; color: white; font-weight: 500; }}
        tr:hover {{ background: #f8f9fa; }}
        .pass-badge {{ background: #d4edda; color: #155724; padding: 0.2rem 0.6rem;
                      border-radius: 4px; font-size: 0.8rem; font-weight: bold; }}
        .fail-badge {{ background: #f8d7da; color: #721c24; padding: 0.2rem 0.6rem;
                      border-radius: 4px; font-size: 0.8rem; font-weight: bold; }}
        .url-list {{ list-style: none; padding: 0; }}
        .url-list li {{ padding: 0.4rem 0; border-bottom: 1px solid #eee; font-family: monospace;
                       font-size: 0.9rem; }}
        .section {{ margin: 1.5rem 0; background: white; border-radius: 8px;
                   padding: 1.5rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .suggestion {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 0.75rem 1rem;
                      margin: 0.5rem 0; border-radius: 0 4px 4px 0; }}
        .gallery {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                   gap: 1rem; margin: 1rem 0; }}
        .gallery img {{ max-width: 100%; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }}
        .timestamp {{ color: #666; font-size: 0.85rem; margin-bottom: 1.5rem; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Test Report</h1>
        <p class="timestamp">Session: {html.escape(session_id)}</p>
        {summary_html}
        {phase1_html}
        {phase2_html}
        {phase3_html}
        {screenshots_html}
    </div>
</body>
</html>"""

    # Save report to file
    reports_dir = "/projects/sandbox/playwright-autotest/reports"
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, f"{session_id}.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_html)

    return report_html


def _build_summary_section(
    total: int, passed: int, failed: int, pass_rate: float, phase1: dict
) -> str:
    """Build the summary statistics section."""
    visited = len(phase1.get("visited_urls", []))
    buttons = len(phase1.get("discovered_buttons", []))

    return f"""
        <div class="summary">
            <div class="stat-card">
                <div class="value">{total}</div>
                <div class="label">Total API Tests</div>
            </div>
            <div class="stat-card pass">
                <div class="value">{passed}</div>
                <div class="label">Passed</div>
            </div>
            <div class="stat-card fail">
                <div class="value">{failed}</div>
                <div class="label">Failed</div>
            </div>
            <div class="stat-card">
                <div class="value">{pass_rate}%</div>
                <div class="label">Pass Rate</div>
            </div>
            <div class="stat-card">
                <div class="value">{visited}</div>
                <div class="label">URLs Visited</div>
            </div>
            <div class="stat-card">
                <div class="value">{buttons}</div>
                <div class="label">Buttons Found</div>
            </div>
        </div>"""


def _build_phase1_section(phase1: dict) -> str:
    """Build Phase 1 (UI Crawl) section."""
    if not phase1:
        return '<div class="section"><h2>Phase 1: UI Crawl</h2><p>No data available.</p></div>'

    visited_urls = phase1.get("visited_urls", [])
    buttons = phase1.get("discovered_buttons", [])
    test_cases = phase1.get("generated_test_cases", [])

    urls_html = ""
    if visited_urls:
        items = "".join(f"<li>{html.escape(u)}</li>" for u in visited_urls)
        urls_html = f'<h3>Visited URLs</h3><ul class="url-list">{items}</ul>'

    buttons_html = ""
    if buttons:
        items = "".join(f"<li>{html.escape(b)}</li>" for b in buttons)
        buttons_html = f'<h3>Discovered Buttons</h3><ul class="url-list">{items}</ul>'

    cases_html = ""
    if test_cases:
        rows = ""
        for tc in test_cases:
            name = html.escape(tc.get("name", ""))
            steps = html.escape(", ".join(tc.get("steps", [])))
            expected = html.escape(tc.get("expected", ""))
            rows += f"<tr><td>{name}</td><td>{steps}</td><td>{expected}</td></tr>"
        cases_html = f"""<h3>Generated Test Cases</h3>
        <table><thead><tr><th>Name</th><th>Steps</th><th>Expected</th></tr></thead>
        <tbody>{rows}</tbody></table>"""

    return f"""<div class="section">
        <h2>Phase 1: UI Crawl</h2>
        {urls_html}
        {buttons_html}
        {cases_html}
    </div>"""


def _build_phase2_section(phase2: list[dict]) -> str:
    """Build Phase 2 (API Tests) section."""
    if not phase2:
        return '<div class="section"><h2>Phase 2: API Tests</h2><p>No API tests executed.</p></div>'

    rows = ""
    for r in phase2:
        method = html.escape(r.get("method", ""))
        url = html.escape(r.get("url", ""))
        status = r.get("status", "-")
        expected = r.get("expected_status", "-")
        passed = r.get("passed", False)
        badge = '<span class="pass-badge">PASS</span>' if passed else '<span class="fail-badge">FAIL</span>'
        duration = r.get("duration_ms", 0)
        error = html.escape(r.get("error", "") or "")

        rows += f"""<tr>
            <td>{method}</td><td>{url}</td><td>{status}</td>
            <td>{expected}</td><td>{badge}</td><td>{duration}ms</td>
            <td>{error}</td>
        </tr>"""

    return f"""<div class="section">
        <h2>Phase 2: API Tests</h2>
        <table>
            <thead><tr><th>Method</th><th>URL</th><th>Status</th><th>Expected</th>
            <th>Result</th><th>Duration</th><th>Error</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>"""


def _build_phase3_section(phase3: dict) -> str:
    """Build Phase 3 (AI Retry) section."""
    if not phase3:
        return '<div class="section"><h2>Phase 3: AI Analysis & Retry</h2><p>No AI analysis data.</p></div>'

    suggestions = phase3.get("suggestions", [])
    retry_plan = phase3.get("retry_plan", [])

    suggestions_html = ""
    if suggestions:
        items = "".join(f'<div class="suggestion">{html.escape(s)}</div>' for s in suggestions)
        suggestions_html = f"<h3>AI Suggestions</h3>{items}"

    plan_html = ""
    if retry_plan:
        rows = ""
        for item in retry_plan:
            endpoint = html.escape(item.get("endpoint", ""))
            suggested = html.escape(item.get("suggested_url", ""))
            reason = html.escape(item.get("reason", ""))
            method = html.escape(item.get("method", ""))
            rows += f"<tr><td>{method}</td><td>{endpoint}</td><td>{suggested}</td><td>{reason}</td></tr>"
        plan_html = f"""<h3>Retry Plan</h3>
        <table><thead><tr><th>Method</th><th>Original</th><th>Suggested URL</th><th>Reason</th></tr></thead>
        <tbody>{rows}</tbody></table>"""

    return f"""<div class="section">
        <h2>Phase 3: AI Analysis & Retry</h2>
        {suggestions_html}
        {plan_html}
    </div>"""


def _build_screenshots_section(screenshots: list[str]) -> str:
    """Build screenshots gallery section."""
    if not screenshots:
        return '<div class="section"><h2>Screenshots</h2><p>No screenshots captured.</p></div>'

    images_html = ""
    for path in screenshots:
        filename = html.escape(os.path.basename(path))
        # Reference by path (not base64 embedding for now)
        images_html += f'<div><p>{filename}</p><img src="file://{html.escape(path)}" alt="{filename}"></div>'

    return f"""<div class="section">
        <h2>Screenshots</h2>
        <div class="gallery">{images_html}</div>
    </div>"""
