import asyncio
import json
from urllib.parse import quote_plus, urlencode
import httpx
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, ScrapedJob

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": "https://www.meteojob.com/",
}


class MeteojobScraper(BaseScraper):
    """Meteojob - site d'emploi français."""
    platform_name = "meteojob"
    BASE_URL = "https://www.meteojob.com"

    async def search(self, keywords: str, location: str, max_results: int = 25) -> list[ScrapedJob]:
        jobs = []
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
            page_num = 1
            while len(jobs) < max_results:
                params = {
                    "q": keywords,
                    "loc": location,
                    "page": page_num,
                }
                url = f"{self.BASE_URL}/jobsearch/offres?" + urlencode(params)
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        break
                except Exception:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                found_in_page = 0

                # JSON-LD
                for script in soup.select('script[type="application/ld+json"]'):
                    try:
                        ld = json.loads(script.string or "")
                        items = []
                        if isinstance(ld, dict) and ld.get("@type") == "ItemList":
                            items = ld.get("itemListElement", [])
                        elif isinstance(ld, dict) and ld.get("@type") == "JobPosting":
                            items = [ld]
                        elif isinstance(ld, list):
                            items = ld

                        for item in items:
                            posting = item if item.get("@type") == "JobPosting" else item.get("item", {})
                            if posting.get("@type") != "JobPosting":
                                continue
                            title = posting.get("title", "")
                            org = posting.get("hiringOrganization", {})
                            company = org.get("name", "") if isinstance(org, dict) else ""
                            desc_html = posting.get("description", "")
                            desc = BeautifulSoup(desc_html, "html.parser").get_text(strip=True) if desc_html else ""
                            job_url = posting.get("url", "")
                            contract = posting.get("employmentType", "")
                            loc_data = posting.get("jobLocation", {})
                            if isinstance(loc_data, list) and loc_data:
                                loc_data = loc_data[0]
                            loc_text = location
                            if isinstance(loc_data, dict):
                                addr = loc_data.get("address", {})
                                if isinstance(addr, dict):
                                    loc_text = addr.get("addressLocality", location)
                            salary_info = posting.get("baseSalary", {})
                            salary = ""
                            if isinstance(salary_info, dict):
                                val = salary_info.get("value", {})
                                if isinstance(val, dict):
                                    salary = f"{val.get('minValue','')}-{val.get('maxValue','')} {val.get('unitText','')}".strip(" -")

                            if title and job_url and not any(j.url == job_url for j in jobs):
                                jobs.append(ScrapedJob(
                                    title=title, company=company, location=loc_text,
                                    description=desc[:5000], url=job_url,
                                    platform=self.platform_name, salary=salary, job_type=contract,
                                ))
                                found_in_page += 1
                                if len(jobs) >= max_results:
                                    break
                    except Exception:
                        pass
                    if len(jobs) >= max_results:
                        break

                # HTML fallback
                if found_in_page == 0:
                    cards = soup.select(
                        "article.offer, li.offer-item, div[data-offer-id], "
                        "[class*='offer-card'], [class*='job-offer'], [class*='offre']"
                    )
                    for card in cards:
                        try:
                            title_el = card.select_one("h2 a, h3 a, a[class*='title'], [class*='offer-title'] a")
                            if not title_el:
                                continue
                            title = title_el.get_text(strip=True)
                            if len(title) < 3:
                                continue
                            href = title_el.get("href", "")
                            if not href:
                                continue
                            if not href.startswith("http"):
                                href = f"{self.BASE_URL}{href}"
                            company_el = card.select_one("[class*='company'], [class*='employer']")
                            company = company_el.get_text(strip=True) if company_el else ""
                            loc_el = card.select_one("[class*='location'], [class*='city'], [class*='lieu']")
                            loc_text = loc_el.get_text(strip=True) if loc_el else location
                            if not any(j.url == href for j in jobs):
                                jobs.append(ScrapedJob(
                                    title=title, company=company, location=loc_text,
                                    description="", url=href, platform=self.platform_name,
                                ))
                                found_in_page += 1
                        except Exception:
                            continue

                if found_in_page == 0:
                    break
                if len(jobs) >= max_results:
                    break
                page_num += 1
                await asyncio.sleep(1)

        return jobs[:max_results]

    async def apply(self, job_url: str, cv_path: str, cover_letter: str = "") -> dict:
        return {"success": False, "message": "Meteojob: candidature manuelle sur meteojob.com"}
