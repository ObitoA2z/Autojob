import asyncio
import json
import re
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

BLOCKED_EMAIL_DOMAINS = {"noreply", "no-reply", "donotreply", "hellowork", "welcometothejungle",
                         "linkedin", "indeed", "apec", "francetravail", "example", "test",
                         "monster", "jobteaser", "talentsoft"}


def _extract_contact_email(html: str) -> str:
    """Extract a real contact email from page HTML, ignoring placeholder attributes."""
    # Remove placeholder="..." attributes to avoid false positives
    clean = re.sub(r'placeholder\s*=\s*"[^"]*"', '', html)
    clean = re.sub(r"placeholder\s*=\s*'[^']*'", '', clean)
    # Also strip value="" attributes in input fields
    clean = re.sub(r'<input[^>]*>', '', clean)
    emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", clean)
    for e in emails:
        if not any(b in e.lower() for b in BLOCKED_EMAIL_DOMAINS):
            return e
    return ""


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
                links = soup.select("a[href*='/fr-fr/emplois/']")
                if not links:
                    break

                seen = set()
                for link in links:
                    href = link.get("href", "")
                    if href in seen or "recherche" in href:
                        continue
                    seen.add(href)

                    raw_text = link.get_text(strip=True)
                    if not raw_text or len(raw_text) < 3:
                        continue

                    if not href.startswith("http"):
                        href = f"{self.BASE_URL}{href}"

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
        """
        Strategy:
        1. Fetch job page via HTTP - look for contact email (fastest, most reliable)
        2. If external apply link found - follow it and look for email there
        3. If HelloWork native form - try browser submit
        """
        # Step 1: HTTP fetch - fast, no browser
        contact_email = ""
        external_apply_url = ""
        try:
            async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as client:
                resp = await client.get(job_url)
                if resp.status_code == 200:
                    html = resp.text
                    contact_email = _extract_contact_email(html)

                    # Find apply button href (external link)
                    soup = BeautifulSoup(html, "html.parser")
                    for btn in soup.select("a[href]"):
                        text = btn.get_text(strip=True).lower()
                        href = btn.get("href", "")
                        if "postul" in text and href.startswith("http") and "hellowork" not in href:
                            external_apply_url = href
                            break
        except Exception:
            pass

        # If we already have a contact email from the main page
        if contact_email:
            return {
                "success": False,
                "message": f"Email trouvé: {contact_email}",
                "contact_email": contact_email,
            }

        # If external URL - follow it and look for email
        if external_apply_url:
            try:
                async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as client:
                    ext_resp = await client.get(external_apply_url)
                    if ext_resp.status_code == 200:
                        ext_email = _extract_contact_email(ext_resp.text)
                        if ext_email:
                            return {
                                "success": False,
                                "message": f"Email trouvé sur site employeur: {ext_email}",
                                "contact_email": ext_email,
                            }
            except Exception:
                pass
            return {
                "success": False,
                "message": f"Redirigé vers site employeur: {external_apply_url[:80]}",
                "contact_email": "",
            }

        # Step 2: Browser try (HelloWork native form)
        try:
            result = await asyncio.wait_for(
                self._browser_apply(job_url, cv_path, cover_letter),
                timeout=45
            )
            return result
        except Exception as e:
            return {
                "success": False,
                "message": f"HelloWork: {str(e)[:100]}",
                "contact_email": contact_email,
            }

    async def _browser_apply(self, job_url: str, cv_path: str, cover_letter: str) -> dict:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="fr-FR",
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()
            contact_email = ""
            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1000)

                # Remove all overlays via JS
                await page.evaluate(
                    "() => {"
                    "document.querySelectorAll('[class*=\"cookie\"],[class*=\"consent\"],[class*=\"gdpr\"],[id*=\"cookie\"],[class*=\"overlay\"],[class*=\"popup\"]')"
                    ".forEach(el => { try { el.remove(); } catch(e) {} });"
                    "document.body.style.overflow = 'auto';"
                    "}"
                )

                content = await page.content()
                contact_email = _extract_contact_email(content)

                apply_btn = await page.query_selector(
                    "a:has-text('Postuler'), button:has-text('Postuler'), "
                    "a[data-cy='apply-button'], button[data-cy='apply-button']"
                )

                if not apply_btn:
                    return {"success": False, "message": "HelloWork: bouton postuler non trouvé", "contact_email": contact_email}

                # Check if external link
                tag = await apply_btn.evaluate("el => el.tagName")
                if tag.lower() == "a":
                    href = await apply_btn.get_attribute("href") or ""
                    if href and "hellowork" not in href and href.startswith("http"):
                        try:
                            async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=10) as c:
                                r = await c.get(href)
                                ext_email = _extract_contact_email(r.text) if r.status_code == 200 else ""
                        except Exception:
                            ext_email = ""
                        return {"success": False, "message": "Redirigé vers site employeur", "contact_email": ext_email or contact_email}

                # JS click to bypass overlays
                await apply_btn.evaluate("el => el.click()")
                await page.wait_for_timeout(2000)

                if "hellowork.com" not in page.url:
                    try:
                        ext_email = _extract_contact_email(await page.content())
                    except Exception:
                        ext_email = ""
                    return {"success": False, "message": "Redirigé vers site employeur", "contact_email": ext_email or contact_email}

                if await page.query_selector("input[type='password']"):
                    return {"success": False, "message": "HelloWork: connexion compte requis", "contact_email": contact_email}

                file_input = await page.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(cv_path)
                    await page.wait_for_timeout(800)

                if cover_letter:
                    ta = await page.query_selector("textarea")
                    if ta:
                        await ta.fill(cover_letter)

                submit_btn = await page.query_selector(
                    "button[type='submit'], button:has-text('Envoyer'), button:has-text('Postuler')"
                )
                if submit_btn:
                    await submit_btn.evaluate("el => el.click()")
                    await page.wait_for_timeout(2000)
                    return {"success": True, "message": "Candidature envoyée via HelloWork"}

                return {"success": False, "message": "HelloWork: compte requis pour postuler", "contact_email": contact_email}
            finally:
                await browser.close()
