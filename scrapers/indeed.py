import asyncio
import json
import re
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper, ScrapedJob

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}


class IndeedScraper(BaseScraper):
    platform_name = "indeed"
    BASE_URL = "https://fr.indeed.com"

    async def search(self, keywords: str, location: str, max_results: int = 25) -> list[ScrapedJob]:
        jobs = []
        query = quote_plus(keywords)
        loc = quote_plus(location)

        # Try httpx first (faster, avoids Playwright startup)
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
            start = 0
            while len(jobs) < max_results:
                url = f"{self.BASE_URL}/jobs?q={query}&l={loc}&start={start}&sort=date"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        break
                except Exception:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                # Extract from JSON-LD
                for script in soup.select('script[type="application/ld+json"]'):
                    try:
                        ld = json.loads(script.string or "")
                        items = []
                        if isinstance(ld, dict):
                            if ld.get("@type") == "ItemList":
                                items = ld.get("itemListElement", [])
                            elif ld.get("@type") == "JobPosting":
                                items = [{"item": ld}]
                        elif isinstance(ld, list):
                            items = ld

                        for item in items:
                            posting = item if item.get("@type") == "JobPosting" else item.get("item", {})
                            if posting.get("@type") != "JobPosting":
                                continue

                            job_title = posting.get("title", "")
                            org = posting.get("hiringOrganization", {})
                            company = org.get("name", "") if isinstance(org, dict) else ""
                            desc_html = posting.get("description", "")
                            desc = BeautifulSoup(desc_html, "html.parser").get_text(strip=True) if desc_html else ""
                            job_url = posting.get("url", "") or posting.get("mainEntityOfPage", "")
                            salary_info = posting.get("baseSalary", {})
                            salary = ""
                            if isinstance(salary_info, dict):
                                val = salary_info.get("value", {})
                                if isinstance(val, dict):
                                    salary = f"{val.get('minValue', '')}-{val.get('maxValue', '')} {val.get('unitText', '')}".strip(" -")
                            contract = posting.get("employmentType", "")

                            loc_data = posting.get("jobLocation", {})
                            if isinstance(loc_data, list) and loc_data:
                                loc_data = loc_data[0]
                            loc_text = location
                            if isinstance(loc_data, dict):
                                addr = loc_data.get("address", {})
                                if isinstance(addr, dict):
                                    loc_text = addr.get("addressLocality", addr.get("addressRegion", location))

                            if job_title:
                                jobs.append(ScrapedJob(
                                    title=job_title,
                                    company=company,
                                    location=loc_text,
                                    description=desc[:5000],
                                    url=job_url,
                                    platform=self.platform_name,
                                    salary=salary,
                                    job_type=contract,
                                ))
                                if len(jobs) >= max_results:
                                    break
                    except (json.JSONDecodeError, TypeError, AttributeError):
                        pass

                if len(jobs) >= max_results:
                    break

                # Fallback: try to extract job data from JavaScript variables
                if not jobs:
                    scripts = soup.find_all("script")
                    for script in scripts:
                        text = script.string or ""
                        if "jobKeysWithTitles" in text or "jobResults" in text or '"jobTitle"' in text:
                            try:
                                # Find JSON arrays/objects in script
                                matches = re.findall(r'\{[^{}]*"jobTitle"[^{}]*\}', text)
                                for m in matches[:max_results]:
                                    d = json.loads(m)
                                    title = d.get("jobTitle", "")
                                    if title:
                                        jobs.append(ScrapedJob(
                                            title=title,
                                            company=d.get("company", ""),
                                            location=d.get("jobLocation", location),
                                            description="",
                                            url=d.get("jobUrl", ""),
                                            platform=self.platform_name,
                                        ))
                            except Exception:
                                pass

                # HTML card fallback
                cards = soup.select("div.job_seen_beacon, div.cardOutline, div[data-jk], li[data-jk]")
                for card in cards:
                    try:
                        title_el = card.select_one("h2 a, h2 span[title], a[data-jk]")
                        if not title_el:
                            continue

                        job_title = title_el.get("title") or title_el.get_text(strip=True)
                        company_el = card.select_one("[data-testid='company-name'], span.companyName, [class*='companyName']")
                        company = company_el.get_text(strip=True) if company_el else ""
                        loc_el = card.select_one("[data-testid='text-location'], div.companyLocation, [class*='location']")
                        loc_text = loc_el.get_text(strip=True) if loc_el else location

                        link_el = card.select_one("a[data-jk], h2 a")
                        href = ""
                        if link_el:
                            jk = link_el.get("data-jk")
                            if jk:
                                href = f"{self.BASE_URL}/viewjob?jk={jk}"
                            else:
                                h = link_el.get("href", "")
                                href = f"{self.BASE_URL}{h}" if h and not h.startswith("http") else h

                        if job_title and not any(j.title == job_title for j in jobs):
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

                if not cards and not jobs:
                    break

                start += 10
                await asyncio.sleep(2)

        return jobs

    async def apply(self, job_url: str, cv_path: str, cover_letter: str = "") -> dict:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                user_agent=UA,
                locale="fr-FR",
                viewport={"width": 1920, "height": 1080},
            )
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = await context.new_page()

            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                # Check for "Apply with Indeed" button (built-in apply)
                apply_btn = await page.query_selector(
                    "#indeedApplyButton, button.jobsearch-IndeedApplyButton-newDesign, "
                    "button[class*='IndeedApplyButton'], span[data-indeed-apply]"
                )

                if not apply_btn:
                    # Check for external apply
                    ext_btn = await page.query_selector("a:has-text('Postuler'), button:has-text('Postuler')")
                    if ext_btn:
                        href = await ext_btn.get_attribute("href") or ""
                        if href and "indeed" not in href and href.startswith("http"):
                            return {"success": False, "message": f"Indeed: redirige vers site employeur - candidature manuelle"}
                    return {"success": False, "message": "Indeed: pas de bouton 'Postuler avec Indeed' - candidature manuelle requise"}

                await apply_btn.click()
                await page.wait_for_timeout(3000)

                # Handle multi-step form
                for step in range(10):
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        await file_input.set_input_files(cv_path)
                        await page.wait_for_timeout(1000)

                    if cover_letter:
                        textarea = await page.query_selector("textarea")
                        if textarea:
                            current = await textarea.input_value()
                            if not current:
                                await textarea.fill(cover_letter)

                    submit_btn = await page.query_selector(
                        "button[type='submit']:has-text('Soumettre'), button:has-text('Submit application'), "
                        "button:has-text('Envoyer ma candidature')"
                    )
                    if submit_btn:
                        await submit_btn.click()
                        await page.wait_for_timeout(3000)
                        return {"success": True, "message": "Candidature envoyée via Indeed"}

                    next_btn = await page.query_selector(
                        "button:has-text('Continuer'), button:has-text('Continue'), "
                        "button:has-text('Suivant'), button:has-text('Next')"
                    )
                    if next_btn:
                        await next_btn.click()
                        await page.wait_for_timeout(1500)
                    else:
                        break

                return {"success": False, "message": "Indeed: impossible de finaliser (compte Indeed requis)"}
            except Exception as e:
                return {"success": False, "message": f"Erreur Indeed: {str(e)[:200]}"}
            finally:
                await browser.close()
