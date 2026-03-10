from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from playwright.async_api import Page, async_playwright

from automation.openclaw_client import OpenClawClient
from backend.core.config import settings
from platforms.base import CampaignCandidate

logger = logging.getLogger(__name__)


class CollabstrConnector:
    name = "collabstr"

    LOGIN_EMAIL_SELECTORS = [
        "input[type='email']",
        "input[name='email']",
        "input[id*='email']",
        "input[autocomplete='email']",
    ]
    LOGIN_PASSWORD_SELECTORS = [
        "input[type='password']",
        "input[name='password']",
        "input[id*='password']",
        "input[autocomplete='current-password']",
    ]
    LOGIN_SUBMIT_SELECTORS = [
        "button[type='submit']",
        "button:has-text('Log in')",
        "button:has-text('Sign in')",
        "button:has-text('Continue')",
    ]
    APPLY_BUTTON_SELECTORS = [
        "button:has-text('Apply now')",
        "button:has-text('Apply')",
        "a:has-text('Apply now')",
        "a:has-text('Apply')",
        "[role='button']:has-text('Apply')",
    ]
    MESSAGE_TEXTAREA_SELECTORS = [
        "textarea[name*='message']",
        "textarea[id*='message']",
        "textarea[placeholder*='message' i]",
        "textarea",
    ]
    SUBMIT_SELECTORS = [
        "button[type='submit']",
        "button:has-text('Submit')",
        "button:has-text('Send')",
        "button:has-text('Apply')",
    ]
    SUCCESS_TOKENS = [
        "application sent",
        "application submitted",
        "submitted",
        "thank you",
        "success",
    ]

    def __init__(self) -> None:
        self._openclaw = OpenClawClient()
        self._state_path = Path(settings.collabstr_storage_state_path)
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

    async def login(self) -> None:
        """Persist Collabstr session for scan/apply runs (OpenClaw first, then Playwright fallback)."""
        if not settings.collabstr_email or not settings.collabstr_password:
            logger.warning("Collabstr credentials are missing; skipping authenticated login")
            return

        openclaw_result = await self._openclaw.run_action(
            "collabstr_login",
            {
                "login_url": settings.collabstr_login_url,
                "email": settings.collabstr_email,
                "password": settings.collabstr_password,
                "selectors": {
                    "email": self.LOGIN_EMAIL_SELECTORS,
                    "password": self.LOGIN_PASSWORD_SELECTORS,
                    "submit": self.LOGIN_SUBMIT_SELECTORS,
                },
            },
        )
        if openclaw_result.get("success"):
            persisted = self._persist_storage_state_from_openclaw(openclaw_result)
            if persisted:
                logger.info("Collabstr session saved from OpenClaw login")
            else:
                logger.info("OpenClaw Collabstr login succeeded")
            return

        await self._login_with_playwright()

    async def _login_with_playwright(self) -> None:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.playwright_headless)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                await page.goto(settings.collabstr_login_url, wait_until="domcontentloaded", timeout=45000)

                email_el = await self._pick_first(
                    page,
                    self.LOGIN_EMAIL_SELECTORS,
                )
                password_el = await self._pick_first(
                    page,
                    self.LOGIN_PASSWORD_SELECTORS,
                )

                if not email_el or not password_el:
                    logger.warning("Could not detect Collabstr login fields")
                    return

                await email_el.fill(settings.collabstr_email)
                await password_el.fill(settings.collabstr_password)

                submit_btn = await self._pick_first(
                    page,
                    self.LOGIN_SUBMIT_SELECTORS,
                )
                if submit_btn:
                    await submit_btn.click()
                await page.wait_for_timeout(3000)

                if "login" not in page.url.lower():
                    await context.storage_state(path=str(self._state_path))
                    logger.info("Collabstr session saved")
                else:
                    logger.warning("Collabstr login likely failed; still on login page")
            finally:
                await browser.close()

    async def scan_campaigns(self) -> list[CampaignCandidate]:
        openclaw_result = await self._openclaw.run_action(
            "collabstr_scan",
            {
                "campaigns_url": settings.collabstr_campaigns_url,
                "storage_state": self._read_storage_state(),
                "max_items": 50,
            },
        )
        openclaw_campaigns = self._extract_openclaw_campaigns(openclaw_result)
        if openclaw_campaigns:
            return openclaw_campaigns[:50]

        campaigns: list[CampaignCandidate] = []
        seen_urls: set[str] = set()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.playwright_headless)
            context_kwargs: dict[str, str] = {}
            if self._state_path.exists():
                context_kwargs["storage_state"] = str(self._state_path)
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            try:
                await page.goto(settings.collabstr_campaigns_url, wait_until="domcontentloaded", timeout=45000)
                await self._scroll_campaign_feed(page)

                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                next_data = soup.select_one("script#__NEXT_DATA__")
                if next_data and next_data.text:
                    campaigns.extend(self._extract_from_next_data(next_data.text, seen_urls))

                if not campaigns:
                    for anchor in soup.select("a[href]"):
                        href = anchor.get("href", "")
                        full_url = self._normalize_campaign_url(href)
                        if not full_url:
                            continue
                        if full_url in seen_urls:
                            continue
                        seen_urls.add(full_url)
                        title = anchor.get_text(" ", strip=True) or "Collabstr Campaign"
                        campaigns.append(
                            CampaignCandidate(
                                platform=self.name,
                                external_id=self._url_to_id(full_url),
                                title=title[:255],
                                brand="",
                                description="",
                                campaign_url=full_url,
                                budget=None,
                                niche=None,
                                target_platform=None,
                            )
                        )
            finally:
                await browser.close()

        return campaigns[:50]

    async def auto_apply(self, campaign: CampaignCandidate, message: str) -> dict:
        payload = {
            "url": campaign.campaign_url,
            "message": message,
            "campaign_id": campaign.external_id,
            "storage_state": self._read_storage_state(),
            "selectors": {
                "apply": self.APPLY_BUTTON_SELECTORS,
                "message": self.MESSAGE_TEXTAREA_SELECTORS,
                "submit": self.SUBMIT_SELECTORS,
            },
        }
        for action_name in ("collabstr_submit", "collabstr_apply"):
            openclaw_result = await self._openclaw.run_action(action_name, payload)
            if openclaw_result.get("success"):
                self._persist_storage_state_from_openclaw(openclaw_result)
                return {
                    "success": True,
                    "message": self._extract_openclaw_message(openclaw_result)
                    or "Application submitted via OpenClaw (Collabstr)",
                }

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.playwright_headless)
            context_kwargs: dict[str, str] = {}
            if self._state_path.exists():
                context_kwargs["storage_state"] = str(self._state_path)
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            try:
                await page.goto(campaign.campaign_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(1500)

                apply_button = await self._pick_first(
                    page,
                    self.APPLY_BUTTON_SELECTORS,
                )
                if not apply_button:
                    return {"success": False, "message": "Collabstr apply button not found"}

                await apply_button.click()
                await page.wait_for_timeout(1000)

                text_area = await self._pick_first(page, self.MESSAGE_TEXTAREA_SELECTORS)
                if text_area:
                    await text_area.fill(message[:1800])

                submit_btn = await self._pick_first(
                    page,
                    self.SUBMIT_SELECTORS,
                )
                if not submit_btn:
                    return {"success": False, "message": "Collabstr submit button not found"}

                await submit_btn.click()
                await page.wait_for_timeout(2000)
                text = (await page.content()).lower()
                ok = any(token in text for token in self.SUCCESS_TOKENS)

                await context.storage_state(path=str(self._state_path))

                if ok:
                    return {"success": True, "message": "Application submitted on Collabstr"}
                return {"success": True, "message": "Submitted on Collabstr (confirmation not explicit)"}
            except Exception as exc:
                logger.exception("Collabstr apply failed")
                return {"success": False, "message": str(exc)}
            finally:
                await browser.close()

    async def _scroll_campaign_feed(self, page: Page) -> None:
        await page.wait_for_timeout(2000)
        for _ in range(4):
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(1200)

    def _extract_openclaw_campaigns(self, openclaw_result: dict[str, Any]) -> list[CampaignCandidate]:
        payload = openclaw_result.get("data")
        if isinstance(payload, dict):
            rows = payload.get("campaigns") or payload.get("items") or payload.get("results")
        elif isinstance(payload, list):
            rows = payload
        else:
            rows = None

        if not isinstance(rows, list):
            return []

        campaigns: list[CampaignCandidate] = []
        seen_urls: set[str] = set()
        for row in rows:
            candidate = self._campaign_from_openclaw_row(row)
            if not candidate:
                continue
            if candidate.campaign_url in seen_urls:
                continue
            seen_urls.add(candidate.campaign_url)
            campaigns.append(candidate)
        return campaigns

    def _campaign_from_openclaw_row(self, row: Any) -> CampaignCandidate | None:
        if isinstance(row, str):
            full_url = self._normalize_campaign_url(row)
            if not full_url:
                return None
            return CampaignCandidate(
                platform=self.name,
                external_id=self._url_to_id(full_url),
                title="Collabstr Campaign",
                brand="",
                description="",
                campaign_url=full_url,
            )

        if not isinstance(row, dict):
            return None

        url_candidate = (
            row.get("url")
            or row.get("campaign_url")
            or row.get("campaignUrl")
            or row.get("href")
            or row.get("slug")
        )
        if not isinstance(url_candidate, str):
            return None
        full_url = self._normalize_campaign_url(url_candidate)
        if not full_url:
            return None

        title = self._coerce_str(row.get("title")) or self._coerce_str(row.get("name")) or "Collabstr Campaign"
        brand = self._coerce_str(row.get("brand")) or self._coerce_str(row.get("company")) or ""
        description = self._coerce_str(row.get("description")) or self._coerce_str(row.get("brief")) or ""
        niche = self._coerce_str(row.get("niche")) or self._coerce_str(row.get("category"))
        target_platform = self._coerce_str(row.get("target_platform")) or self._coerce_str(row.get("platform"))
        budget = self._pick_budget({k.lower(): v for k, v in row.items()})

        external_id = self._coerce_str(row.get("external_id")) or self._coerce_str(row.get("id")) or self._url_to_id(full_url)

        return CampaignCandidate(
            platform=self.name,
            external_id=external_id,
            title=title[:255],
            brand=brand[:255],
            description=description[:5000],
            campaign_url=full_url,
            budget=budget,
            niche=niche,
            target_platform=target_platform,
        )

    def _extract_from_next_data(self, raw_json: str, seen_urls: set[str]) -> list[CampaignCandidate]:
        campaigns: list[CampaignCandidate] = []
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            return campaigns

        for node in self._walk_dicts(payload):
            values = {str(k).lower(): v for k, v in node.items()}
            url_candidate = values.get("url") or values.get("campaignurl") or values.get("slug")
            if not isinstance(url_candidate, str):
                continue

            full_url = self._normalize_campaign_url(url_candidate)
            if not full_url:
                continue
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            title = self._pick_str(values, ["title", "name", "campaigntitle"]) or "Collabstr Campaign"
            brand = self._pick_str(values, ["brand", "brandname", "company"]) or ""
            description = self._pick_str(values, ["description", "brief", "summary"]) or ""
            niche = self._pick_str(values, ["niche", "category", "vertical"])
            target_platform = self._pick_str(values, ["platform", "socialplatform", "channel"])
            budget = self._pick_budget(values)

            campaigns.append(
                CampaignCandidate(
                    platform=self.name,
                    external_id=self._url_to_id(full_url),
                    title=title[:255],
                    brand=brand[:255],
                    description=description[:5000],
                    campaign_url=full_url,
                    budget=budget,
                    niche=niche,
                    target_platform=target_platform,
                )
            )

        return campaigns

    def _walk_dicts(self, node):
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from self._walk_dicts(value)
        elif isinstance(node, list):
            for item in node:
                yield from self._walk_dicts(item)

    @staticmethod
    def _pick_str(values: dict[str, object], keys: list[str]) -> str | None:
        for key in keys:
            val = values.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None

    @staticmethod
    def _pick_budget(values: dict[str, object]) -> float | None:
        for key in ["budget", "budgetamount", "price", "payout"]:
            val = values.get(key)
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                match = re.search(r"\d+(?:[.,]\d+)?", val.replace(" ", ""))
                if match:
                    return float(match.group(0).replace(",", "."))
        return None

    @staticmethod
    def _url_to_id(url: str) -> str:
        return url.rstrip("/").split("/")[-1]

    @staticmethod
    async def _pick_first(page: Page, selectors: list[str]):
        for selector in selectors:
            el = await page.query_selector(selector)
            if el:
                return el
        return None

    @staticmethod
    def _coerce_str(value: Any) -> str | None:
        if isinstance(value, str):
            clean = value.strip()
            return clean or None
        return None

    @staticmethod
    def _extract_openclaw_message(openclaw_result: dict[str, Any]) -> str | None:
        payload = openclaw_result.get("data")
        if isinstance(payload, dict):
            for key in ("message", "status", "result"):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        message = openclaw_result.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        return None

    def _persist_storage_state_from_openclaw(self, openclaw_result: dict[str, Any]) -> bool:
        payload = openclaw_result.get("data")
        if not isinstance(payload, dict):
            return False
        state = payload.get("storage_state") or payload.get("storageState")
        if not isinstance(state, (dict, list)):
            return False
        self._state_path.write_text(json.dumps(state), encoding="utf-8")
        return True

    def _read_storage_state(self) -> dict[str, Any] | None:
        if not self._state_path.exists():
            return None
        try:
            raw = self._state_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception:
            logger.warning("Invalid Collabstr storage state file; ignoring")
            return None
        if isinstance(data, dict):
            return data
        return None

    @staticmethod
    def _normalize_campaign_url(raw_url: str) -> str | None:
        value = raw_url.strip()
        if not value:
            return None
        if value.startswith("/"):
            full = f"https://collabstr.com{value}"
        elif value.startswith("http://") or value.startswith("https://"):
            full = value
        else:
            full = f"https://collabstr.com/campaigns/{value.lstrip('/')}"

        if "/campaign" not in full.lower():
            return None
        return full
