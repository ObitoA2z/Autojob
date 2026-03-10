import asyncio
from urllib.parse import quote_plus
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper, ScrapedJob

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class ApecScraper(BaseScraper):
    platform_name = "apec"
    BASE_URL = "https://www.apec.fr"

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

        async with async_playwright() as p:
            browser, context = await self._make_context(p)
            page = await context.new_page()

            try:
                page_num = 1
                while len(jobs) < max_results:
                    url = f"{self.BASE_URL}/candidat/recherche-emploi.html/emploi?motsCles={query}&lieu={quote_plus(location)}&page={page_num}"
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(3000)

                    # Handle cookie consent
                    try:
                        cookie_btn = await page.query_selector(
                            "button:has-text('Tout accepter'), #onetrust-accept-btn-handler, button:has-text('Accepter')"
                        )
                        if cookie_btn:
                            await cookie_btn.click()
                            await page.wait_for_timeout(1000)
                    except Exception:
                        pass

                    # Find job cards
                    cards = await page.query_selector_all(
                        "div.card-offer, a[href*='/offres/detailoffre'], "
                        "div[class*='offer-item'], article"
                    )
                    if not cards:
                        # Try finding links directly
                        cards = await page.query_selector_all("a[href*='/offres/']")
                    if not cards:
                        break

                    for card in cards:
                        try:
                            # Get title
                            title_el = await card.query_selector("h2, h3, span[class*='title'], div[class*='title']")
                            if not title_el:
                                text = (await card.inner_text()).strip()
                                if len(text) < 5:
                                    continue
                                title = text.split("\n")[0][:100]
                            else:
                                title = (await title_el.inner_text()).strip()

                            # Get company
                            comp_el = await card.query_selector("span[class*='company'], div[class*='company'], p[class*='company']")
                            company = (await comp_el.inner_text()).strip() if comp_el else ""

                            # Get location
                            loc_el = await card.query_selector("span[class*='location'], div[class*='location']")
                            loc_text = (await loc_el.inner_text()).strip() if loc_el else location

                            # Get URL
                            href = ""
                            tag = await card.evaluate("el => el.tagName")
                            if tag.lower() == "a":
                                href = await card.get_attribute("href") or ""
                            else:
                                link_el = await card.query_selector("a[href*='/offres/']")
                                if link_el:
                                    href = await link_el.get_attribute("href") or ""

                            if href and not href.startswith("http"):
                                href = f"{self.BASE_URL}{href}"

                            if not title or len(title) < 3:
                                continue

                            jobs.append(ScrapedJob(
                                title=title,
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

                    page_num += 1
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

                # Dismiss cookie banners
                for btn_sel in ["button:has-text('Tout accepter')", "button:has-text('Accepter')", "#onetrust-accept-btn-handler"]:
                    try:
                        btn = await page.query_selector(btn_sel)
                        if btn:
                            await btn.click(timeout=3000)
                            await page.wait_for_timeout(500)
                            break
                    except Exception:
                        pass

                apply_btn = await page.query_selector(
                    "button:has-text('Postuler'), a:has-text('Postuler'), "
                    "a[class*='apply'], button[class*='apply']"
                )

                if not apply_btn:
                    return {"success": False, "message": "APEC: bouton postuler non trouvé - connexion compte requis"}

                try:
                    await apply_btn.click(timeout=10000)
                except Exception:
                    await apply_btn.evaluate("el => el.click()")
                await page.wait_for_timeout(3000)

                # Check if APEC requires login
                if await page.query_selector("input[type='email'], input[type='password'], [class*='login']"):
                    return {"success": False, "message": "APEC: connexion compte requis pour postuler"}

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
                    return {"success": True, "message": "Candidature envoyée via APEC"}

                return {"success": False, "message": "Impossible de finaliser la candidature APEC"}
            except Exception as e:
                return {"success": False, "message": f"Erreur: {str(e)}"}
            finally:
                await browser.close()
