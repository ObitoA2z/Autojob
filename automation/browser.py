from __future__ import annotations

import logging

from playwright.async_api import async_playwright

from automation.openclaw_client import OpenClawClient
from backend.core.config import settings

logger = logging.getLogger(__name__)


class BrowserAutomation:
    def __init__(self) -> None:
        self.openclaw = OpenClawClient()

    async def submit_application(self, url: str, message: str) -> dict:
        # Prefer OpenClaw for browser control if available.
        openclaw_result = await self.openclaw.run_action(
            "submit_application",
            {"url": url, "message": message},
        )
        if openclaw_result.get("success"):
            return {"success": True, "message": "Submitted via OpenClaw"}

        # Fallback to direct Playwright flow.
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=settings.playwright_headless)
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Generic fallback: the selectors should be overridden per connector.
                textarea = await page.query_selector("textarea")
                if textarea:
                    await textarea.fill(message[:1800])
                button = await page.query_selector("button[type='submit'], button:has-text('Apply'), button:has-text('Submit')")
                if button:
                    await button.click()
                await browser.close()
            return {"success": True, "message": "Submitted via Playwright fallback"}
        except Exception as exc:
            logger.exception("Playwright submit failed")
            return {"success": False, "message": str(exc)}
