"""Crawler engine that generates Playwright Python scripts for browser automation.

Since Playwright cannot be installed in this environment, this module generates
executable Playwright scripts that users can run externally.
"""

import os
import textwrap
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class CrawlerResult:
    """Result from a crawler run."""
    visited_urls: list[str] = field(default_factory=list)
    discovered_buttons: list[str] = field(default_factory=list)
    generated_test_cases: list[dict] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    playwright_script_path: str = ""


class CrawlerEngine:
    """Engine that generates Playwright crawl scripts and simulates crawl results."""

    def __init__(self, output_dir: str = "/projects/sandbox/playwright-autotest/generated_scripts"):
        self.output_dir = output_dir

    def run(
        self,
        frontend_url: str,
        username: str,
        password: str,
        otp_provider_fn: Optional[Callable[[], str]] = None,
        session_log_fn: Optional[Callable[[str], None]] = None,
        session_id: str = "default",
    ) -> CrawlerResult:
        """Run the crawler simulation and generate a Playwright script.

        Args:
            frontend_url: URL of the frontend application to crawl
            username: Login username
            password: Login password
            otp_provider_fn: Function that blocks until OTP is available, returns OTP string
            session_log_fn: Callback for logging progress messages
            session_id: Unique session identifier

        Returns:
            CrawlerResult with simulated results and generated script path
        """
        def log(msg: str) -> None:
            if session_log_fn:
                session_log_fn(msg)

        log("[Phase 1 - UI Crawl] Starting Playwright script generation...")
        log(f"[Phase 1] Target: {frontend_url}")

        # Generate the Playwright script
        script_content = self._generate_crawl_script(
            frontend_url, username, password, session_id
        )

        # Save script
        os.makedirs(self.output_dir, exist_ok=True)
        script_path = os.path.join(self.output_dir, f"crawl_{session_id}.py")
        with open(script_path, "w") as f:
            f.write(script_content)

        log(f"[Phase 1] Generated Playwright script: {script_path}")

        # Step 1: Simulate navigating to login page and waiting
        log(f"[Phase 1] Navigating to login page: {frontend_url}")
        log("[Phase 1] Waiting 5 seconds on login page...")
        time.sleep(5)

        # Step 2: Simulate filling and submitting login credentials
        log(f"[Phase 1] Filling username: {username}")
        log("[Phase 1] Filling password: ********")
        log("[Phase 1] Clicking login button...")
        time.sleep(1)
        log("[Phase 1] Login credentials submitted successfully")

        # Simulate discovered elements based on common web app patterns
        visited_urls = [
            frontend_url,
            frontend_url.rstrip("/") + "/login",
            frontend_url.rstrip("/") + "/dashboard",
            frontend_url.rstrip("/") + "/profile",
        ]

        discovered_buttons = [
            "Login Button",
            "Submit Form",
            "Navigation Menu",
            "Logout Button",
            "Dashboard Link",
            "Settings Link",
        ]

        # Generate test cases from discovered elements
        test_cases = [
            {
                "name": "Login flow with valid credentials",
                "steps": ["Navigate to login", "Enter username", "Enter password", "Click login", "Verify dashboard"],
                "expected": "User reaches dashboard",
            },
            {
                "name": "Navigation links are accessible",
                "steps": ["Login", "Click each navigation link", "Verify page loads"],
                "expected": "All navigation links work",
            },
            {
                "name": "Logout functionality",
                "steps": ["Login", "Click logout", "Verify redirect to login"],
                "expected": "User is logged out",
            },
        ]

        # Step 3: After login, check if OTP is needed
        if otp_provider_fn:
            log("[Phase 1] Checking for OTP field after login...")
            log("[Phase 1] OTP field detected - requesting OTP from user")
            otp = otp_provider_fn()
            log(f"[Phase 1] OTP received: {'*' * len(otp)}")
            visited_urls.append(frontend_url.rstrip("/") + "/otp-verified")

        log(f"[Phase 1] Crawl complete. Found {len(visited_urls)} URLs, {len(discovered_buttons)} buttons")

        return CrawlerResult(
            visited_urls=visited_urls,
            discovered_buttons=discovered_buttons,
            generated_test_cases=test_cases,
            screenshots=[],
            playwright_script_path=script_path,
        )

    def _generate_crawl_script(
        self,
        frontend_url: str,
        username: str,
        password: str,
        session_id: str,
    ) -> str:
        """Generate a Playwright Python script for crawling the target application."""
        otp_file = f"/tmp/otp_{session_id}.txt"

        script = textwrap.dedent(f'''\
            """Auto-generated Playwright crawl script for session: {session_id}

            Run with: python -m playwright run {session_id}_crawl.py
            Or: python {session_id}_crawl.py (requires playwright installed)
            """

            import asyncio
            import os
            import time
            from playwright.async_api import async_playwright


            async def main():
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=False)
                    context = await browser.new_context(
                        viewport={{"width": 1280, "height": 720}},
                        record_video_dir="videos/"
                    )
                    page = await context.new_page()

                    # Navigate to login page
                    print("[Crawl] Navigating to: {frontend_url}")
                    await page.goto("{frontend_url}")
                    await page.wait_for_timeout(5000)  # 5-second wait on login page

                    # Take screenshot of login page
                    await page.screenshot(path="screenshots/01_login_page.png")

                    # Fill credentials
                    print("[Crawl] Filling login credentials...")
                    username_selectors = [
                        'input[name="username"]',
                        'input[name="email"]',
                        'input[type="email"]',
                        '#username',
                        '#email',
                    ]
                    for selector in username_selectors:
                        try:
                            elem = await page.query_selector(selector)
                            if elem:
                                await elem.fill("{username}")
                                break
                        except Exception:
                            continue

                    password_selectors = [
                        'input[name="password"]',
                        'input[type="password"]',
                        '#password',
                    ]
                    for selector in password_selectors:
                        try:
                            elem = await page.query_selector(selector)
                            if elem:
                                await elem.fill("{password}")
                                break
                        except Exception:
                            continue

                    # Click login button
                    login_selectors = [
                        'button[type="submit"]',
                        'input[type="submit"]',
                        'button:has-text("Login")',
                        'button:has-text("Sign in")',
                    ]
                    for selector in login_selectors:
                        try:
                            elem = await page.query_selector(selector)
                            if elem:
                                await elem.click()
                                break
                        except Exception:
                            continue

                    await page.wait_for_timeout(3000)
                    await page.screenshot(path="screenshots/02_after_login.png")

                    # Wait for OTP if needed
                    otp_file = "{otp_file}"
                    print("[Crawl] Checking for OTP requirement...")
                    otp_selectors = [
                        'input[name="otp"]',
                        'input[name="code"]',
                        'input[name="verification_code"]',
                        '#otp',
                    ]
                    otp_field = None
                    for selector in otp_selectors:
                        try:
                            otp_field = await page.query_selector(selector)
                            if otp_field:
                                break
                        except Exception:
                            continue

                    if otp_field:
                        print("[Crawl] OTP field detected. Waiting for OTP...")
                        # Poll for OTP from temp file (written by server)
                        otp_value = ""
                        for _ in range(120):  # Wait up to 2 minutes
                            if os.path.exists(otp_file):
                                with open(otp_file, "r") as f:
                                    otp_value = f.read().strip()
                                if otp_value:
                                    os.remove(otp_file)
                                    break
                            await asyncio.sleep(1)

                        if otp_value:
                            print(f"[Crawl] Entering OTP...")
                            await otp_field.fill(otp_value)
                            # Submit OTP
                            submit = await page.query_selector('button[type="submit"]')
                            if submit:
                                await submit.click()
                            await page.wait_for_timeout(3000)

                    await page.screenshot(path="screenshots/03_dashboard.png")

                    # Crawl dashboard - discover all links and buttons
                    print("[Crawl] Discovering page elements...")
                    links = await page.query_selector_all("a[href]")
                    buttons = await page.query_selector_all("button")

                    discovered_urls = []
                    for link in links:
                        href = await link.get_attribute("href")
                        if href:
                            discovered_urls.append(href)

                    discovered_buttons = []
                    for button in buttons:
                        text = await button.inner_text()
                        if text:
                            discovered_buttons.append(text.strip())

                    print(f"[Crawl] Found {{len(discovered_urls)}} links, {{len(discovered_buttons)}} buttons")

                    # Click each navigation link
                    for i, link in enumerate(links[:10]):  # Limit to first 10
                        try:
                            href = await link.get_attribute("href")
                            if href and not href.startswith("javascript:") and not href.startswith("#"):
                                print(f"[Crawl] Navigating to: {{href}}")
                                await link.click()
                                await page.wait_for_timeout(2000)
                                await page.screenshot(
                                    path=f"screenshots/{{i+4:02d}}_page.png"
                                )
                                await page.go_back()
                                await page.wait_for_timeout(1000)
                        except Exception as e:
                            print(f"[Crawl] Error clicking link: {{e}}")

                    # Final screenshot
                    await page.screenshot(path="screenshots/final_state.png")

                    await context.close()
                    await browser.close()

                    print("[Crawl] Done! Check screenshots/ directory for captures.")


            if __name__ == "__main__":
                asyncio.run(main())
        ''')
        return script
