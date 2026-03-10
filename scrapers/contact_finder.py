import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright
import json

COOKIES_PATH = Path(__file__).resolve().parent.parent / "uploads" / "cookies_linkedin.json"
HEADERS_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

RECRUITER_TITLES = [
    "recruteur", "recruiter", "talent acquisition",
    "drh", "responsable rh", "chargé rh", "charge rh",
    "hiring manager", "rh", "human resources",
    "people", "talent",
]


def _load_cookies():
    if COOKIES_PATH.exists():
        try:
            return json.load(open(COOKIES_PATH))
        except Exception:
            pass
    return []


def _guess_emails(first: str, last: str, domain: str) -> list:
    """Generate common email pattern guesses."""
    if not domain or not first or not last:
        return []
    f = first.lower().strip()
    l = last.lower().strip()
    patterns = [
        f"{f}.{l}@{domain}",
        f"{f[0]}.{l}@{domain}",
        f"{f}@{domain}",
        f"{f}{l}@{domain}",
        f"{f[0]}{l}@{domain}",
        f"{l}.{f}@{domain}",
    ]
    return patterns


async def find_contacts_for_company(company: str, limit: int = 10) -> list[dict]:
    """
    Search LinkedIn for HR/recruiter contacts at a company.
    Returns list of dicts: {name, role, linkedin_url, email_guesses}.
    """
    cookies = _load_cookies()
    if not cookies:
        return []

    contacts = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=HEADERS_UA, locale="fr-FR",
            viewport={"width": 1920, "height": 1080},
        )
        await context.add_init_script("Object.defineProperty(navigator, "webdriver", {get: () => undefined})")
        await context.add_cookies(cookies)
        page = await context.new_page()

        try:
            # Search for recruiters at this company
            from urllib.parse import quote_plus
            query = quote_plus(f"recruteur {company}")
            url = f"https://www.linkedin.com/search/results/people/?keywords={query}&origin=GLOBAL_SEARCH_HEADER"
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            content = await page.content()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, "html.parser")

            # Extract people results
            results = soup.select(".entity-result, [class*="entity-result__item"]")
            if not results:
                results = soup.select(".search-result, [class*="search-results__result-item"]")

            for r in results[:limit * 2]:
                try:
                    # Name
                    name_el = r.select_one(".entity-result__title-text, [class*="actor-name"]")
                    if not name_el:
                        name_el = r.select_one("span[aria-hidden="true"]")
                    name = name_el.get_text(strip=True) if name_el else ""

                    # Role / headline
                    subtitle_el = r.select_one(".entity-result__primary-subtitle, [class*="primary-subtitle"]")
                    role = subtitle_el.get_text(strip=True) if subtitle_el else ""

                    # Filter: only keep HR/recruiter titles
                    role_lower = role.lower()
                    is_recruiter = any(t in role_lower for t in RECRUITER_TITLES)
                    # Also check if company matches
                    secondary_el = r.select_one(".entity-result__secondary-subtitle, [class*="secondary-subtitle"]")
                    company_in_result = (secondary_el.get_text(strip=True) if secondary_el else "").lower()

                    if not is_recruiter and company.lower() not in company_in_result:
                        continue

                    # LinkedIn URL
                    link_el = r.select_one("a[href*="/in/"]")
                    linkedin_url = ""
                    if link_el:
                        href = link_el.get("href", "")
                        # Clean tracking params
                        linkedin_url = href.split("?")[0]
                        if not linkedin_url.startswith("http"):
                            linkedin_url = "https://www.linkedin.com" + linkedin_url

                    if name and linkedin_url:
                        # Parse first/last name
                        parts = name.split()
                        first = parts[0] if parts else ""
                        last = parts[-1] if len(parts) > 1 else ""
                        contacts.append({
                            "name": name,
                            "role": role,
                            "company": company,
                            "linkedin_url": linkedin_url,
                            "email_guesses": [],  # filled by caller with domain
                        })
                        if len(contacts) >= limit:
                            break
                except Exception:
                    continue

        except Exception as e:
            print(f"[ContactFinder] Erreur LinkedIn pour {company}: {e}")
        finally:
            await browser.close()

    return contacts
