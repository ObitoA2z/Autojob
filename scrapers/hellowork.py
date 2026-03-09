import asyncio
import json
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


class HelloWorkScraper(BaseScraper):
    platform_name = "hellowork"
    BASE_URL = "https://www.hellowork.com"

    async def search(self, keywords: str, location: str, max_results: int = 25) -> list[ScrapedJob]:
        jobs = []
        query = quote_plus(keywords)
        loc = quote_plus(location)

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
            page_num = 1
            while len(jobs) < max_results:
                url = f"{self.BASE_URL}/fr-fr/emploi/recherche.html?k={query}&l={loc}&p={page_num}"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        break
                except Exception:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                # Find job links (pattern: /fr-fr/emplois/XXXXX.html)
                links = soup.select("a[href*='/fr-fr/emplois/']")
                if not links:
                    break

                seen = set()
                for link in links:
                    href = link.get("href", "")
                    if href in seen or "recherche" in href:
                        continue
                    seen.add(href)

                    # Title + company are concatenated in the link text
                    raw_text = link.get_text(strip=True)
                    if not raw_text or len(raw_text) < 3:
                        continue

                    if not href.startswith("http"):
                        href = f"{self.BASE_URL}{href}"

                    # Get structured data from detail page (JSON-LD)
                    title = raw_text
                    company = ""
                    description = ""
                    loc_text = location
                    salary = ""
                    job_type = ""
                    try:
                        detail = await client.get(href)
                        if detail.status_code == 200:
                            dsoup = BeautifulSoup(detail.text, "html.parser")
                            # Use JSON-LD structured data (most reliable)
                            for script in dsoup.select('script[type="application/ld+json"]'):
                                try:
                                    ld = json.loads(script.string)
                                    if isinstance(ld, dict) and ld.get("@type") == "JobPosting":
                                        title = ld.get("title", title)
                                        org = ld.get("hiringOrganization", {})
                                        company = org.get("name", "") if isinstance(org, dict) else ""
                                        description = BeautifulSoup(ld.get("description", ""), "html.parser").get_text(strip=True)
                                        locs = ld.get("jobLocation", [])
                                        if isinstance(locs, list) and locs:
                                            addr = locs[0].get("address", {})
                                            loc_text = addr.get("addressLocality", location)
                                        salary_info = ld.get("baseSalary", {})
                                        if isinstance(salary_info, dict):
                                            val = salary_info.get("value", {})
                                            if isinstance(val, dict):
                                                salary = f"{val.get('minValue', '')}-{val.get('maxValue', '')} {val.get('unitText', '')}"
                                        job_type = ld.get("employmentType", "")
                                        break
                                except (json.JSONDecodeError, TypeError):
                                    pass
                    except Exception:
                        pass

                    jobs.append(ScrapedJob(
                        title=title,
                        company=company,
                        location=loc_text,
                        description=description[:5000],
                        url=href,
                        platform=self.platform_name,
                        salary=salary,
                        job_type=job_type,
                    ))

                    if len(jobs) >= max_results:
                        break

                page_num += 1
                await asyncio.sleep(1)

        return jobs

    async def apply(self, job_url: str, cv_path: str, cover_letter: str = "") -> dict:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="fr-FR",
            )
            page = await context.new_page()

            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                apply_btn = await page.query_selector(
                    "a:has-text('Postuler'), button:has-text('Postuler'), "
                    "a[data-cy='apply-button'], button[data-cy='apply-button']"
                )

                if not apply_btn:
                    return {"success": False, "message": "Bouton postuler non trouvé"}

                await apply_btn.click()
                await page.wait_for_timeout(3000)

                file_input = await page.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(cv_path)
                    await page.wait_for_timeout(1000)

                if cover_letter:
                    textarea = await page.query_selector(
                        "textarea[name*='letter'], textarea[name*='motivation'], textarea[name*='message']"
                    )
                    if textarea:
                        await textarea.fill(cover_letter)

                submit_btn = await page.query_selector(
                    "button[type='submit'], button:has-text('Envoyer'), button:has-text('Postuler')"
                )
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_timeout(3000)
                    return {"success": True, "message": "Candidature envoyée via HelloWork"}

                return {"success": False, "message": "Impossible de finaliser la candidature"}
            except Exception as e:
                return {"success": False, "message": f"Erreur: {str(e)}"}
            finally:
                await browser.close()
