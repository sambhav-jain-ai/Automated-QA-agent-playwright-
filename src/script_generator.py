"""Script generator for Phase 3 Playwright scripts.

Generates complete Playwright Python scripts incorporating AI suggestions.
"""

import os
import textwrap
from typing import Any, Optional


def generate_phase3_script(
    session_id: str,
    retry_plan: list[dict[str, Any]],
    frontend_url: str,
    ai_guidance: Optional[list[str]] = None,
) -> str:
    """Generate a Phase 3 Playwright script based on AI retry plan.

    Args:
        session_id: Unique session identifier
        retry_plan: List of retry plan items from AIModule
        frontend_url: Base frontend URL
        ai_guidance: Optional list of AI suggestion strings

    Returns:
        Complete Playwright Python script as string. Also saves to generated_scripts/.
    """
    ai_guidance = ai_guidance or []

    # Build guidance comments
    guidance_comments = ""
    if ai_guidance:
        lines = "\n".join(f"# - {g}" for g in ai_guidance)
        guidance_comments = f"\n# AI Guidance:\n{lines}\n"

    # Build test steps from retry plan
    test_steps = []
    for i, item in enumerate(retry_plan):
        method = item.get("method", "GET")
        url = item.get("suggested_url", item.get("endpoint", ""))
        reason = item.get("reason", "Retry")
        original = item.get("original_url", item.get("endpoint", ""))

        test_steps.append(textwrap.dedent(f'''\
            # Step {i+1}: {reason}
            # Original: {original}
            print(f"[Phase 3 - Step {i+1}] {method} {url}")
            try:
                response_{i} = await page.request.fetch(
                    "{url}",
                    method="{method}",
                )
                status_{i} = response_{i}.status
                print(f"  -> Status: {{status_{i}}}")
                results.append({{
                    "step": {i+1},
                    "method": "{method}",
                    "url": "{url}",
                    "status": status_{i},
                    "passed": 200 <= status_{i} < 400,
                }})
            except Exception as e:
                print(f"  -> Error: {{e}}")
                results.append({{
                    "step": {i+1},
                    "method": "{method}",
                    "url": "{url}",
                    "status": None,
                    "passed": False,
                    "error": str(e),
                }})
        '''))

    steps_code = "\n".join(f"        {line}" for step in test_steps for line in step.split("\n"))

    if not steps_code.strip():
        steps_code = '        print("[Phase 3] No retry steps defined.")'

    script = textwrap.dedent(f'''\
        """Auto-generated Phase 3 Playwright Script
        Session: {session_id}

        This script retries failed API endpoints using AI-corrected URLs.
        Run with: python -m pytest {session_id}_phase3.py (with playwright installed)
        Or: python {session_id}_phase3.py
        """
        {guidance_comments}
        import asyncio
        import json
        from playwright.async_api import async_playwright


        async def main():
            results = []

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                # Navigate to frontend first
                print("[Phase 3] Navigating to frontend: {frontend_url}")
                await page.goto("{frontend_url}")
                await page.wait_for_timeout(2000)

                print("[Phase 3] Starting AI-guided retry tests...")
                print("[Phase 3] Retry plan has {{}} endpoint(s)".format({len(retry_plan)}))

        {steps_code}

                # Summary
                passed = sum(1 for r in results if r.get("passed"))
                total = len(results)
                print(f"\\n[Phase 3] Results: {{passed}}/{{total}} passed")

                # Save results to JSON
                with open("phase3_results_{session_id}.json", "w") as f:
                    json.dump(results, f, indent=2)

                await context.close()
                await browser.close()

            return results


        if __name__ == "__main__":
            asyncio.run(main())
    ''')

    # Save to generated_scripts directory
    output_dir = "/projects/sandbox/playwright-autotest/generated_scripts"
    os.makedirs(output_dir, exist_ok=True)
    script_path = os.path.join(output_dir, f"phase3_{session_id}.py")
    with open(script_path, "w") as f:
        f.write(script)

    return script
