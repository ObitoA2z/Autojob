import asyncio
import json
from urllib.parse import quote_plus, urlencode
import httpx
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, ScrapedJob

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": "https://candidat.francetravail.fr/",
}


class FranceTravailScraper(BaseScraper):
    """France Travail (ex Pôle Emploi) scraper."""
    platform_name = "francetravail"

    async def search(self, keywords: str, location: str, max_results: int = 25) -> list[ScrapedJob]:
        jobs = []

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
            page_num = 0
            while len(jobs) < max_results:
                url = "https://candidat.francetravail.fr/offres/recherche?" + urlencode({
                    "motsCles": keywords,
                    "lieuTravail.libelle": location,
                })
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        break
                except Exception:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                # Extract job links from HTML (they appear as /offres/recherche/detail/{id})
                links = soup.select("a[href*='/offres/recherche/detail/']")
                if not links:
                    break

                seen_ids = {j.url.split("/")[-1] for j in jobs}
                batch_urls = []
                for link in links:
                    href = link.get("href", "")
                    if not href:
                        continue
                    offer_id = href.rstrip("/").split("/")[-1]
                    if offer_id in seen_ids:
                        continue
                    seen_ids.add(offer_id)
                    full_url = f"https://candidat.francetravail.fr{href}" if not href.startswith("http") else href
                    title_text = link.get_text(strip=True)
                    # Strip "(déjà vu)" prefix
                    title_text = title_text.replace("(déjà vu)", "").replace("(d\u00e9j\u00e0 vu)", "").strip()
                    if len(title_text) < 3:
                        continue
                    batch_urls.append((offer_id, full_url, title_text))
                    if len(jobs) + len(batch_urls) >= max_results:
                        break

                # Fetch details for each job
                for offer_id, full_url, title_fallback in batch_urls:
                    try:
                        detail_resp = await client.get(full_url)
                        if detail_resp.status_code != 200:
                            jobs.append(ScrapedJob(
                                title=title_fallback, company="", location=location,
                                description="", url=full_url, platform=self.platform_name,
                            ))
                            continue
                        dsoup = BeautifulSoup(detail_resp.text, "html.parser")

                        # Try JSON-LD first
                        title = title_fallback
                        company = ""
                        description = ""
                        loc_text = location
                        salary = ""
                        contract = ""

                        for script in dsoup.select('script[type="application/ld+json"]'):
                            try:
                                ld = json.loads(script.string or "")
                                if isinstance(ld, dict) and ld.get("@type") == "JobPosting":
                                    title = ld.get("title", title)
                                    org = ld.get("hiringOrganization", {})
                                    company = org.get("name", "") if isinstance(org, dict) else ""
                                    description = BeautifulSoup(ld.get("description", ""), "html.parser").get_text(strip=True)
                                    loc_data = ld.get("jobLocation", {})
                                    if isinstance(loc_data, list) and loc_data:
                                        loc_data = loc_data[0]
                                    if isinstance(loc_data, dict):
                                        addr = loc_data.get("address", {})
                                        if isinstance(addr, dict):
                                            loc_text = addr.get("addressLocality", location)
                                    salary_info = ld.get("baseSalary", {})
                                    if isinstance(salary_info, dict):
                                        val = salary_info.get("value", {})
                                        if isinstance(val, dict):
                                            salary = f"{val.get('minValue','')}-{val.get('maxValue','')} {val.get('unitText','')}".strip(" -")
                                    contract = ld.get("employmentType", "")
                                    break
                            except Exception:
                                pass

                        # Fallback to HTML extraction
                        if not company:
                            comp_el = dsoup.select_one(
                                "[class*='company'], [class*='entreprise'], [itemprop='hiringOrganization']"
                            )
                            if comp_el:
                                company = comp_el.get_text(strip=True)

                        if not description:
                            desc_el = dsoup.select_one(
                                "[class*='description'], [itemprop='description'], .offre-details"
                            )
                            if desc_el:
                                description = desc_el.get_text(strip=True)[:5000]

                        jobs.append(ScrapedJob(
                            title=title,
                            company=company,
                            location=loc_text,
                            description=description[:5000],
                            url=full_url,
                            platform=self.platform_name,
                            salary=salary,
                            job_type=contract,
                        ))
                        await asyncio.sleep(0.5)
                    except Exception:
                        pass

                    if len(jobs) >= max_results:
                        break

                if not batch_urls or len(jobs) >= max_results:
                    break
                page_num += 1

        return jobs

    async def apply(self, job_url: str, cv_path: str, cover_letter: str = "") -> dict:
        """France Travail nécessite un compte Mon Espace - redirige l'utilisateur."""
        return {
            "success": False,
            "message": "France Travail: candidature manuelle sur candidat.francetravail.fr"
        }
