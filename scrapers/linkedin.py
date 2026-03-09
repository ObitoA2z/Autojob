import asyncio
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper, ScrapedJob

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "DNT": "1",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


class LinkedInScraper(BaseScraper):
    """LinkedIn scraper using public job listings (no login required for search)."""
    platform_name = "linkedin"
    BASE_URL = "https://www.linkedin.com"

    async def search(self, keywords: str, location: str, max_results: int = 25) -> list[ScrapedJob]:
        jobs = []
        query = quote_plus(keywords)
        loc = quote_plus(location)

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
            start = 0
            while len(jobs) < max_results:
                url = f"{self.BASE_URL}/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={query}&location={loc}&start={start}"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        # Fallback to regular page
                        url = f"{self.BASE_URL}/jobs/search/?keywords={query}&location={loc}&start={start}"
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            break
                except Exception:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                cards = soup.select("div.base-card, li.base-card, div.base-search-card")
                if not cards:
                    cards = soup.select("div.job-search-card")
                if not cards:
                    break

                for card in cards:
                    try:
                        title_el = card.select_one("h3.base-search-card__title, h4.base-search-card__title, a.base-card__full-link")
                        company_el = card.select_one("h4.base-search-card__subtitle, a.base-search-card__subtitle-link")
                        location_el = card.select_one("span.job-search-card__location")

                        if not title_el:
                            continue

                        title = title_el.get_text(strip=True)
                        company = company_el.get_text(strip=True) if company_el else "N/A"
                        loc_text = location_el.get_text(strip=True) if location_el else ""

                        link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
                        href = link_el.get("href", "").split("?")[0] if link_el else ""

                        description = ""
                        if href:
                            try:
                                detail = await client.get(href)
                                if detail.status_code == 200:
                                    dsoup = BeautifulSoup(detail.text, "html.parser")
                                    desc_el = dsoup.select_one("div.description__text, div.show-more-less-html, section.description")
                                    if desc_el:
                                        description = desc_el.get_text(strip=True)
                            except Exception:
                                pass

                        date_el = card.select_one("time")
                        posted_date = date_el.get("datetime", "") if date_el else ""

                        jobs.append(ScrapedJob(
                            title=title,
                            company=company,
                            location=loc_text,
                            description=description[:5000],
                            url=href,
                            platform=self.platform_name,
                            posted_date=posted_date,
                        ))

                        if len(jobs) >= max_results:
                            break
                    except Exception:
                        continue

                start += 25
                await asyncio.sleep(2)

        return jobs

    async def apply(self, job_url: str, cv_path: str, cover_letter: str = "") -> dict:
        """Apply via LinkedIn Easy Apply (requires user to be logged in)."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="fr-FR",
            )
            page = await context.new_page()

            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                if "/login" in page.url or "/authwall" in page.url:
                    return {
                        "success": False,
                        "message": "LinkedIn nécessite une connexion. Connectez-vous d'abord manuellement."
                    }

                easy_apply = await page.query_selector(
                    "button.jobs-apply-button, button:has-text('Candidature simplifiée'), "
                    "button:has-text('Easy Apply'), button:has-text('Postuler')"
                )

                if not easy_apply:
                    return {"success": False, "message": "Pas de bouton Easy Apply trouvé"}

                await easy_apply.click()
                await page.wait_for_timeout(2000)

                file_input = await page.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(cv_path)
                    await page.wait_for_timeout(1000)

                for _ in range(5):
                    submit_btn = await page.query_selector(
                        "button:has-text('Soumettre'), button:has-text('Submit'), button:has-text('Envoyer')"
                    )
                    if submit_btn:
                        await submit_btn.click()
                        await page.wait_for_timeout(3000)
                        return {"success": True, "message": "Candidature envoyée via LinkedIn Easy Apply"}

                    next_btn = await page.query_selector(
                        "button:has-text('Suivant'), button:has-text('Next'), button:has-text('Réviser'), button:has-text('Review')"
                    )
                    if next_btn:
                        await next_btn.click()
                        await page.wait_for_timeout(1500)
                    else:
                        break

                return {"success": False, "message": "Impossible de finaliser la candidature LinkedIn"}
            except Exception as e:
                return {"success": False, "message": f"Erreur: {str(e)}"}
            finally:
                await browser.close()
