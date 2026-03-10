import asyncio
from urllib.parse import quote_plus
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper, ScrapedJob

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class WTTJScraper(BaseScraper):
    """Welcome to the Jungle scraper - needs Playwright (SPA)."""
    platform_name = "wttj"
    BASE_URL = "https://www.welcometothejungle.com"

    async def _make_context(self, p):
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA,
            locale="fr-FR",
            viewport={"width": 1920, "height": 1080},
        )
        # Stealth: remove webdriver flag
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return browser, context

    async def search(self, keywords: str, location: str, max_results: int = 25) -> list[ScrapedJob]:
        jobs = []

        async with async_playwright() as p:
            browser, context = await self._make_context(p)
            page = await context.new_page()

            try:
                page_num = 1
                while len(jobs) < max_results:
                    url = f"{self.BASE_URL}/fr/jobs?query={quote_plus(keywords)}&page={page_num}&aroundQuery={quote_plus(location)}"
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(3000)

                    # Get all job links from the rendered page
                    job_links = await page.query_selector_all("a[href*='/fr/companies/'][href*='/jobs/']")
                    if not job_links:
                        break

                    for link_el in job_links:
                        try:
                            href = await link_el.get_attribute("href") or ""
                            title = (await link_el.inner_text()).strip()

                            if not href or not title or len(title) < 3:
                                continue

                            if not href.startswith("http"):
                                href = f"{self.BASE_URL}{href}"

                            # Avoid duplicates
                            if any(j.url == href for j in jobs):
                                continue

                            jobs.append(ScrapedJob(
                                title=title,
                                company="",
                                location=location,
                                description="",
                                url=href,
                                platform=self.platform_name,
                            ))

                            if len(jobs) >= max_results:
                                break
                        except Exception:
                            continue

                    # Get descriptions from detail pages for collected jobs
                    for job in jobs:
                        if job.description:
                            continue
                        try:
                            await page.goto(job.url, wait_until="domcontentloaded", timeout=15000)
                            await page.wait_for_timeout(2000)

                            # Title
                            h2 = await page.query_selector("h2")
                            if h2:
                                job.title = (await h2.inner_text()).strip()

                            # Company
                            comp = await page.query_selector("a[href*='/fr/companies/'] span, h3")
                            if comp:
                                job.company = (await comp.inner_text()).strip()

                            # Description
                            desc = await page.query_selector("div[data-testid='job-section-description'], div.sc-dkrFOg, section[class*='description']")
                            if desc:
                                job.description = (await desc.inner_text()).strip()[:5000]

                            # Location
                            loc = await page.query_selector("span[class*='location'], i[name='location'] + span")
                            if loc:
                                job.location = (await loc.inner_text()).strip()
                        except Exception:
                            pass

                    page_num += 1
            finally:
                await browser.close()

        return jobs

    async def apply(self, job_url: str, cv_path: str, cover_letter: str = "") -> dict:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(user_agent=UA, locale="fr-FR")
            page = await context.new_page()

            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                # Dismiss cookie banners
                for btn_sel in ["button:has-text('Tout accepter')", "button:has-text('Accepter')", "#axeptio_btn_acceptAll"]:
                    try:
                        btn = await page.query_selector(btn_sel)
                        if btn:
                            await btn.click(timeout=3000)
                            await page.wait_for_timeout(500)
                            break
                    except Exception:
                        pass

                apply_btn = await page.query_selector(
                    "button:has-text('Postuler'), a:has-text('Postuler'), button[data-testid='apply-button']"
                )
                if not apply_btn:
                    return {"success": False, "message": "WTTJ: bouton postuler non trouvé - connexion compte requis"}

                try:
                    await apply_btn.click(timeout=10000)
                except Exception:
                    await apply_btn.evaluate("el => el.click()")
                await page.wait_for_timeout(3000)

                # Check if redirected to external site
                if "welcometothejungle.com" not in page.url:
                    return {"success": False, "message": f"WTTJ: redirigé vers site employeur - candidature manuelle"}

                file_input = await page.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(cv_path)
                    await page.wait_for_timeout(1000)

                if cover_letter:
                    textarea = await page.query_selector("textarea")
                    if textarea:
                        await textarea.fill(cover_letter)

                submit_btn = await page.query_selector(
                    "button[type='submit'], button:has-text('Envoyer'), button:has-text('Postuler')"
                )
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_timeout(3000)
                    return {"success": True, "message": "Candidature envoyée via WTTJ"}

                return {"success": False, "message": "Impossible de finaliser la candidature"}
            except Exception as e:
                return {"success": False, "message": f"Erreur: {str(e)}"}
            finally:
                await browser.close()
