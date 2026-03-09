import asyncio
import json
from urllib.parse import quote_plus
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, ScrapedJob

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class IndeedScraper(BaseScraper):
    platform_name = "indeed"
    BASE_URL = "https://fr.indeed.com"

    async def _make_context(self, p, headless=True):
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=UA,
            locale="fr-FR",
            viewport={"width": 1920, "height": 1080},
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return browser, context

    async def search(self, keywords: str, location: str, max_results: int = 25) -> list[ScrapedJob]:
        jobs = []
        query = quote_plus(keywords)
        loc = quote_plus(location)

        async with async_playwright() as p:
            browser, context = await self._make_context(p)
            page = await context.new_page()

            try:
                start = 0
                while len(jobs) < max_results:
                    url = f"{self.BASE_URL}/jobs?q={query}&l={loc}&start={start}"
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(3000)

                    # Check if blocked
                    title = await page.title()
                    if "blocked" in title.lower() or "captcha" in title.lower():
                        break

                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")

                    # Try JSON-LD first
                    for script in soup.select('script[type="application/ld+json"]'):
                        try:
                            ld = json.loads(script.string)
                            items = []
                            if isinstance(ld, dict) and ld.get("@type") == "ItemList":
                                items = ld.get("itemListElement", [])
                            elif isinstance(ld, list):
                                items = ld

                            for item in items:
                                posting = item if item.get("@type") == "JobPosting" else item.get("item", {})
                                if posting.get("@type") != "JobPosting":
                                    continue

                                job_title = posting.get("title", "")
                                org = posting.get("hiringOrganization", {})
                                company = org.get("name", "") if isinstance(org, dict) else ""
                                desc = BeautifulSoup(posting.get("description", ""), "html.parser").get_text(strip=True)
                                job_url = posting.get("url", "")

                                loc_data = posting.get("jobLocation", {})
                                if isinstance(loc_data, list) and loc_data:
                                    loc_data = loc_data[0]
                                loc_text = ""
                                if isinstance(loc_data, dict):
                                    addr = loc_data.get("address", {})
                                    loc_text = addr.get("addressLocality", "") if isinstance(addr, dict) else ""

                                if job_title:
                                    jobs.append(ScrapedJob(
                                        title=job_title,
                                        company=company,
                                        location=loc_text,
                                        description=desc[:5000],
                                        url=job_url,
                                        platform=self.platform_name,
                                    ))
                                    if len(jobs) >= max_results:
                                        break
                        except (json.JSONDecodeError, TypeError):
                            pass

                    if jobs:
                        break  # Got results from JSON-LD

                    # Fallback: parse HTML
                    cards = await page.query_selector_all("div.job_seen_beacon, div.cardOutline, div[data-jk]")
                    if not cards:
                        break

                    for card in cards:
                        try:
                            title_el = await card.query_selector("h2 a, h2 span, a[data-jk]")
                            if not title_el:
                                continue

                            job_title = (await title_el.inner_text()).strip()
                            company_el = await card.query_selector("[data-testid='company-name'], span.companyName")
                            company = (await company_el.inner_text()).strip() if company_el else ""
                            loc_el = await card.query_selector("[data-testid='text-location'], div.companyLocation")
                            loc_text = (await loc_el.inner_text()).strip() if loc_el else ""

                            link_el = await card.query_selector("a[data-jk], h2 a")
                            href = ""
                            if link_el:
                                jk = await link_el.get_attribute("data-jk")
                                if jk:
                                    href = f"{self.BASE_URL}/viewjob?jk={jk}"
                                else:
                                    h = await link_el.get_attribute("href")
                                    href = f"{self.BASE_URL}{h}" if h and not h.startswith("http") else (h or "")

                            jobs.append(ScrapedJob(
                                title=job_title,
                                company=company,
                                location=loc_text,
                                description="",
                                url=href,
                                platform=self.platform_name,
                            ))

                            if len(jobs) >= max_results:
                                break
                        except Exception:
                            continue

                    start += 10
            finally:
                await browser.close()

        return jobs

    async def apply(self, job_url: str, cv_path: str, cover_letter: str = "") -> dict:
        async with async_playwright() as p:
            browser, context = await self._make_context(p, headless=False)
            page = await context.new_page()

            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                apply_btn = await page.query_selector(
                    "button#indeedApplyButton, button.jobsearch-IndeedApplyButton-newDesign, "
                    "a[href*='apply'], button:has-text('Postuler'), button:has-text('Apply')"
                )

                if not apply_btn:
                    return {"success": False, "message": "Bouton postuler non trouvé"}

                await apply_btn.click()
                await page.wait_for_timeout(3000)

                file_input = await page.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(cv_path)
                    await page.wait_for_timeout(1000)

                submit_btn = await page.query_selector(
                    "button[type='submit'], button:has-text('Soumettre'), "
                    "button:has-text('Submit'), button:has-text('Continuer'), button:has-text('Continue')"
                )

                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_timeout(3000)
                    return {"success": True, "message": "Candidature envoyée via Indeed"}

                return {"success": False, "message": "Impossible de finaliser la candidature"}
            except Exception as e:
                return {"success": False, "message": f"Erreur: {str(e)}"}
            finally:
                await browser.close()
