import asyncio
import json
import os
from pathlib import Path
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper, ScrapedJob
from ai.form_answerer import answer_form_question, get_profile_value

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

COOKIES_PATH = Path(__file__).resolve().parent.parent / "uploads" / "cookies_linkedin.json"


def _save_cookies(cookies: list):
    COOKIES_PATH.parent.mkdir(exist_ok=True)
    with open(COOKIES_PATH, "w") as f:
        json.dump(cookies, f)


def _load_cookies() -> list:
    if COOKIES_PATH.exists():
        try:
            with open(COOKIES_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return []


class LinkedInScraper(BaseScraper):
    platform_name = "linkedin"
    BASE_URL = "https://www.linkedin.com"

    # Shared browser for reuse across multiple apply() calls (faster - no startup per job)
    _shared_playwright = None
    _shared_browser = None
    _shared_context = None

    async def _make_context(self, p, headless=True):
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="fr-FR",
            viewport={"width": 1920, "height": 1080},
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        cookies = _load_cookies()
        if cookies:
            await context.add_cookies(cookies)
        return browser, context

    async def _get_shared_page(self):
        """Reuse a single browser context across multiple apply() calls."""
        if self._shared_browser is None or not self._shared_browser.is_connected():
            LinkedInScraper._shared_playwright = await async_playwright().start()
            LinkedInScraper._shared_browser = await LinkedInScraper._shared_playwright.chromium.launch(headless=True)
            LinkedInScraper._shared_context = await LinkedInScraper._shared_browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="fr-FR",
                viewport={"width": 1920, "height": 1080},
            )
            await LinkedInScraper._shared_context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            cookies = _load_cookies()
            if cookies:
                await LinkedInScraper._shared_context.add_cookies(cookies)
        return await LinkedInScraper._shared_context.new_page()

    async def login(self, email: str, password: str) -> dict:
        """Se connecte à LinkedIn et sauvegarde les cookies de session."""
        async with async_playwright() as p:
            browser, context = await self._make_context(p, headless=False)
            page = await context.new_page()
            try:
                await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                await page.fill("#username", email)
                await page.fill("#password", password)
                await page.click("button[type='submit']")
                await page.wait_for_timeout(5000)

                # Handle 2FA if needed
                if "/checkpoint/" in page.url or "/challenge/" in page.url:
                    # Wait up to 60s for user to complete 2FA
                    for _ in range(12):
                        await page.wait_for_timeout(5000)
                        if "feed" in page.url or "/in/" in page.url:
                            break

                if "feed" in page.url or "/mynetwork" in page.url or "/jobs" in page.url:
                    cookies = await context.cookies()
                    _save_cookies(cookies)
                    return {"success": True, "message": "Connecté à LinkedIn, session sauvegardée"}
                else:
                    return {"success": False, "message": f"Échec connexion LinkedIn. URL: {page.url}"}
            except Exception as e:
                return {"success": False, "message": f"Erreur: {str(e)}"}
            finally:
                await browser.close()

    def _is_logged_in_url(self, url: str) -> bool:
        return "authwall" not in url and "/login" not in url and "/signup" not in url

    async def search(self, keywords: str, location: str, max_results: int = 25) -> list[ScrapedJob]:
        jobs = []
        query = quote_plus(keywords)
        loc = quote_plus(location)

        # Try with cookies (logged in) first, then fallback to public API
        async with async_playwright() as p:
            browser, context = await self._make_context(p, headless=True)
            page = await context.new_page()
            try:
                start = 0
                while len(jobs) < max_results:
                    # f_LF=f_AL filters for Easy Apply jobs only
                    url = (
                        f"{self.BASE_URL}/jobs/search/?keywords={query}&location={loc}"
                        f"&start={start}&f_LF=f_AL&f_TPR=r604800"
                    )
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(1500)

                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")

                    # Extract all job links from the page
                    job_links = soup.select("a[href*='/jobs/view/']")
                    if not job_links:
                        break

                    seen_urls = {j.url for j in jobs}
                    for link_el in job_links:
                        href = link_el.get("href", "").split("?")[0]
                        if not href:
                            continue
                        if not href.startswith("http"):
                            href = f"{self.BASE_URL}{href}"
                        if href in seen_urls:
                            continue
                        seen_urls.add(href)

                        # Extract title from link text
                        raw_text = link_el.get_text(separator=" ", strip=True)
                        # LinkedIn often puts "Title\nCompany" in the link text
                        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
                        title = lines[0] if lines else raw_text[:80]
                        if not title or len(title) < 3:
                            continue

                        # Try to get company from nearby element
                        parent = link_el.parent
                        company = ""
                        if parent:
                            comp_el = parent.select_one(
                                "[class*='company'], [class*='subtitle'], [class*='employer']"
                            )
                            if comp_el:
                                company = comp_el.get_text(strip=True)

                        jobs.append(ScrapedJob(
                            title=title,
                            company=company,
                            location=location,
                            description="",
                            url=href,
                            platform=self.platform_name,
                        ))

                        if len(jobs) >= max_results:
                            break

                    if len(jobs) >= max_results:
                        break
                    start += 25
                    await asyncio.sleep(2)

                # Fetch descriptions for found jobs
                for job in jobs[:10]:  # Limit detail fetches
                    if not job.url:
                        continue
                    try:
                        await page.goto(job.url, wait_until="domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(2000)
                        content = await page.content()
                        dsoup = BeautifulSoup(content, "html.parser")
                        desc_el = dsoup.select_one(
                            "div.description__text, div.show-more-less-html, "
                            "section.description, div.jobs-description__content"
                        )
                        if desc_el:
                            job.description = desc_el.get_text(strip=True)[:5000]
                    except Exception:
                        pass

            finally:
                await browser.close()

        return jobs

    async def apply(self, job_url: str, cv_path: str, cover_letter: str = "", profile=None) -> dict:
        """Apply via LinkedIn Easy Apply avec session sauvegardée."""
        cookies = _load_cookies()
        if not cookies:
            return {
                "success": False,
                "message": "LinkedIn: pas de session sauvegardée. Allez dans Paramètres > Connexion LinkedIn pour vous connecter."
            }

        try:
            page = await self._get_shared_page()
        except Exception as e:
            return {"success": False, "message": f"LinkedIn: erreur navigateur: {str(e)[:100]}"}

        try:
            # Close any stale dialog from a previous job
            try:
                stale = await page.query_selector("div[role='dialog']")
                if stale:
                    dismiss = await page.query_selector("button[aria-label*='Rejeter'], button[aria-label*='Dismiss'], button[aria-label*='Fermer'], button[aria-label*='Close']")
                    if dismiss:
                        await dismiss.click()
                        await page.wait_for_timeout(400)
            except Exception:
                pass

            await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)

            if not self._is_logged_in_url(page.url):
                LinkedInScraper._shared_browser = None
                _save_cookies([])
                return {"success": False, "message": "LinkedIn: session expirée. Reconnectez-vous dans Paramètres."}

            # Find Easy Apply link (newer LinkedIn UI uses <a> tag)
            easy_apply = await page.query_selector("a[href*='/apply/']")
            if not easy_apply:
                easy_apply = await page.query_selector("button.jobs-apply-button:not([disabled])")
            if not easy_apply:
                easy_apply = await page.query_selector("button[aria-label*='Easy Apply'], button[aria-label*='Candidature simplifiée']")

            if not easy_apply:
                return {"success": False, "message": "LinkedIn: bouton Easy Apply non trouvé (emploi sans Easy Apply)"}

            await easy_apply.click()
            await page.wait_for_timeout(800)

            yaml_profile = getattr(profile, "yaml_profile", {}) if profile else {}

            async def click_btn_text(texts):
                btns = await page.query_selector_all("button")
                for b in btns:
                    t = (await b.inner_text()).strip().lower()
                    for text in texts:
                        if text.lower() in t:
                            await b.click()
                            return True
                return False

            # Navigate multi-step form (up to 20 steps)
            for step in range(20):
                await page.wait_for_timeout(600)

                modal = await page.query_selector("div[role='dialog']")
                if not modal:
                    # Modal closed - could mean submitted or cancelled
                    break

                modal_text = (await modal.inner_text()).lower()

                # Check for success confirmation
                if any(w in modal_text for w in ['envoy\u00e9e \u00e0', 'application submitted', 'candidature a \u00e9t\u00e9 envoy\u00e9e', 'votre candidature a', 'your application was']):
                    _save_cookies(await LinkedInScraper._shared_context.cookies())
                    # Click "Terminé"/"Done" to close the success modal
                    await click_btn_text(['termin\u00e9', 'done', 'fermer', 'close'])
                    return {"success": True, "message": "Candidature envoyée via LinkedIn Easy Apply"}

                # Upload CV if file input present
                file_input = await page.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(cv_path)
                    await page.wait_for_timeout(400)

                # Fill form fields
                await self._fill_form_fields(page, profile, yaml_profile, cover_letter)

                # Fill number inputs (years of experience etc.)
                num_inputs = await page.query_selector_all("input[type='number']")
                for inp in num_inputs:
                    try:
                        val = await inp.input_value()
                        if val:
                            continue
                        inp_id = await inp.get_attribute("id") or ""
                        label = ""
                        if inp_id:
                            lbl_el = await page.query_selector(f"label[for='{inp_id}']")
                            if lbl_el:
                                label = (await lbl_el.inner_text()).lower()
                        if not label:
                            label = (await inp.get_attribute("aria-label") or "").lower()
                        fill_val = "5" if any(w in label for w in ['ann\u00e9e', 'year', 'exp']) else "3"
                        await inp.fill(fill_val)
                    except Exception:
                        pass

                # Auto-answer radio buttons: Oui/Yes
                radios = await page.query_selector_all("input[type='radio']")
                answered_names = set()
                for r in radios:
                    name = await r.get_attribute("name") or ""
                    if name in answered_names:
                        continue
                    if await r.is_checked():
                        answered_names.add(name)
                        continue
                    rid = await r.get_attribute("id") or ""
                    lbl = await page.query_selector(f"label[for='{rid}']") if rid else None
                    lbl_text = (await lbl.inner_text()).strip().lower() if lbl else ""
                    val = (await r.get_attribute("value") or "").lower()
                    if lbl_text in ("oui", "yes") or val in ("yes", "oui", "true", "1"):
                        await r.click()
                        answered_names.add(name)

                # Handle LinkedIn custom combobox/select dropdowns
                await self._fill_linkedin_dropdowns(page, yaml_profile)

                # Click "Envoyer la candidature" (final submit)
                submit_clicked = await click_btn_text([
                    'envoyer la candidature', 'envoyer ma candidature',
                    'soumettre', 'soumettre la candidature',
                    'submit application', 'submit my application',
                    'postuler maintenant',
                ])
                if submit_clicked:
                    await page.wait_for_timeout(2500)
                    final_modal = await page.query_selector("div[role='dialog']")
                    if final_modal:
                        result_text = (await final_modal.inner_text()).lower()
                        if any(w in result_text for w in ['envoy', 'submitted', 'sent', 'termin', 'done']):
                            _save_cookies(await LinkedInScraper._shared_context.cookies())
                            await click_btn_text(['termin\u00e9', 'done', 'fermer', 'close'])
                            return {"success": True, "message": "Candidature envoyée via LinkedIn Easy Apply"}
                        # Modal still open but no clear success text - still consider it sent
                        # if it wasn't an error page
                        if not any(w in result_text for w in ['erreur', 'error', 'requis', 'required', 'obligatoire']):
                            _save_cookies(await LinkedInScraper._shared_context.cookies())
                            return {"success": True, "message": "Candidature envoyée via LinkedIn Easy Apply"}
                    else:
                        # Modal closed = submitted successfully
                        _save_cookies(await LinkedInScraper._shared_context.cookies())
                        return {"success": True, "message": "Candidature envoyée via LinkedIn Easy Apply"}

                # Click Next/Vérifier/Continuer
                advanced = await click_btn_text([
                    'suivant', 'v\u00e9rifier', 'verifier',
                    'next', 'review', 'continuer', 'continue',
                ])
                if not advanced:
                    # No button found - check if we're stuck on required fields
                    error_els = await page.query_selector_all("[class*='error'], [class*='invalid'], [aria-invalid='true']")
                    if error_els:
                        # Try to fill any remaining required fields
                        for err_el in error_els[:5]:
                            try:
                                inp = await err_el.query_selector("input, select, textarea")
                                if inp:
                                    tag = await inp.evaluate("el => el.tagName.toLowerCase()")
                                    if tag in ("input", "textarea"):
                                        await inp.fill("Oui")
                            except Exception:
                                pass
                        # Try clicking next again
                        if not await click_btn_text(['suivant', 'next', 'continuer', 'v\u00e9rifier']):
                            break
                    else:
                        break

            return {"success": False, "message": "LinkedIn Easy Apply: impossible de finaliser"}

        except Exception as e:
            LinkedInScraper._shared_browser = None  # Reset on error
            return {"success": False, "message": f"Erreur LinkedIn: {str(e)[:200]}"}
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def _fill_form_fields(self, page, profile, yaml_profile: dict, cover_letter: str):
        """
        AIHawk-style: detect all form fields and fill them using profile + LLM.
        Handles: text inputs, selects, radios, checkboxes, textareas.
        """
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        loop = asyncio.get_event_loop()

        # Direct field mapping from profile
        direct_map = {
            "first name": getattr(profile, "first_name", "") if profile else "",
            "prénom": getattr(profile, "first_name", "") if profile else "",
            "last name": getattr(profile, "last_name", "") if profile else "",
            "nom": getattr(profile, "last_name", "") if profile else "",
            "email": getattr(profile, "email", "") if profile else "",
            "phone": getattr(profile, "phone", "") if profile else "",
            "téléphone": getattr(profile, "phone", "") if profile else "",
            "mobile": getattr(profile, "phone", "") if profile else "",
            "city": getattr(profile, "city", "") if profile else "",
            "ville": getattr(profile, "city", "") if profile else "",
        }

        # Fill text inputs
        try:
            inputs = await page.query_selector_all("input[type='text'], input[type='tel'], input[type='email'], input[type='number']")
            for inp in inputs:
                try:
                    current = await inp.input_value()
                    if current:
                        continue
                    label_text = ""
                    # Try aria-label
                    label_text = (await inp.get_attribute("aria-label") or "").lower()
                    if not label_text:
                        # Try associated label
                        inp_id = await inp.get_attribute("id")
                        if inp_id:
                            label_el = await page.query_selector(f"label[for='{inp_id}']")
                            if label_el:
                                label_text = (await label_el.inner_text()).lower().strip()
                    if not label_text:
                        label_text = (await inp.get_attribute("placeholder") or "").lower()

                    # Direct match
                    value = ""
                    for key, val in direct_map.items():
                        if key in label_text and val:
                            value = val
                            break

                    # LLM fallback for unknown fields
                    if not value and label_text and yaml_profile:
                        inp_type = await inp.get_attribute("type") or "text"
                        field_type = "number" if inp_type == "number" else "text"
                        value = await loop.run_in_executor(
                            executor, answer_form_question, yaml_profile, label_text, field_type, None
                        )

                    if value:
                        await inp.fill(str(value))
                        await page.wait_for_timeout(300)
                except Exception:
                    continue
        except Exception:
            pass

        # Fill textareas (cover letter / motivation)
        try:
            textareas = await page.query_selector_all("textarea")
            for ta in textareas:
                try:
                    current = await ta.input_value()
                    if current:
                        continue
                    if cover_letter:
                        await ta.fill(cover_letter)
                    elif yaml_profile:
                        label_text = (await ta.get_attribute("aria-label") or "").lower()
                        value = await loop.run_in_executor(
                            executor, answer_form_question, yaml_profile, label_text or "motivation", "textarea", None
                        )
                        if value:
                            await ta.fill(value)
                    await page.wait_for_timeout(300)
                except Exception:
                    continue
        except Exception:
            pass

        # Fill selects (dropdowns)
        try:
            selects = await page.query_selector_all("select")
            for sel in selects:
                try:
                    current = await sel.input_value()
                    if current and current != "Select an option":
                        continue
                    label_text = (await sel.get_attribute("aria-label") or "").lower()
                    options_els = await sel.query_selector_all("option")
                    options = []
                    for o in options_els:
                        t = (await o.inner_text()).strip()
                        if t and t.lower() not in ("select an option", "sélectionnez", ""):
                            options.append(t)
                    if options and yaml_profile:
                        chosen = await loop.run_in_executor(
                            executor, answer_form_question, yaml_profile, label_text or "select", "select", options
                        )
                        if chosen and chosen in options:
                            await sel.select_option(label=chosen)
                    await page.wait_for_timeout(300)
                except Exception:
                    continue
        except Exception:
            pass

        # Handle radio buttons (Yes/No questions)
        try:
            fieldsets = await page.query_selector_all("fieldset")
            for fs in fieldsets:
                try:
                    legend = await fs.query_selector("legend")
                    question = (await legend.inner_text()).strip() if legend else ""
                    radios = await fs.query_selector_all("input[type='radio']")
                    if not radios or not question:
                        continue
                    # Check if any radio is already selected
                    any_checked = False
                    for r in radios:
                        if await r.is_checked():
                            any_checked = True
                            break
                    if any_checked:
                        continue
                    # Get options
                    options = []
                    for r in radios:
                        lbl_id = await r.get_attribute("id")
                        lbl = await page.query_selector(f"label[for='{lbl_id}']")
                        if lbl:
                            options.append((await lbl.inner_text()).strip())
                    if options and yaml_profile:
                        chosen = await loop.run_in_executor(
                            executor, answer_form_question, yaml_profile, question, "radio", options
                        )
                        for r in radios:
                            lbl_id = await r.get_attribute("id")
                            lbl = await page.query_selector(f"label[for='{lbl_id}']")
                            if lbl and chosen in (await lbl.inner_text()):
                                await r.click()
                                break
                    await page.wait_for_timeout(300)
                except Exception:
                    continue
        except Exception:
            pass

    async def _fill_linkedin_dropdowns(self, page, yaml_profile: dict):
        """Handle LinkedIn's custom select dropdowns."""
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        loop = asyncio.get_event_loop()
        try:
            combos = await page.query_selector_all(
                "select[data-test-text-entity-list-form-select], "
                "select[data-test-text-selectable-option__trigger]"
            )
            for combo in combos:
                try:
                    current = await combo.input_value()
                    if current and current.lower() not in ("select an option", "sélectionnez une option", ""):
                        continue
                    label_text = (await combo.get_attribute("aria-label") or "").lower()
                    if not label_text:
                        cid = await combo.get_attribute("id")
                        if cid:
                            lbl = await page.query_selector(f"label[for='{cid}']")
                            if lbl:
                                label_text = (await lbl.inner_text()).lower().strip()
                    options_els = await combo.query_selector_all("option")
                    options = []
                    for o in options_els:
                        t = (await o.inner_text()).strip()
                        if t and t.lower() not in ("select an option", "sélectionnez", ""):
                            options.append(t)
                    if not options:
                        continue
                    if yaml_profile:
                        chosen = await loop.run_in_executor(
                            executor, answer_form_question, yaml_profile, label_text or "select", "select", options
                        )
                        if chosen and chosen in options:
                            await combo.select_option(label=chosen)
                            await page.wait_for_timeout(200)
                            continue
                    # Default: pick first option
                    await combo.select_option(label=options[0])
                    await page.wait_for_timeout(200)
                except Exception:
                    continue
        except Exception:
            pass
