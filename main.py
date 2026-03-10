import asyncio
import os
import shutil
import yaml
from datetime import datetime
from pathlib import Path

import pdfplumber
from fastapi import FastAPI, UploadFile, File, Form, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from sqlalchemy.orm import Session

from config import UPLOAD_DIR, BASE_DIR
from database import init_db, get_db, JobOffer, UserProfile, ApplicationLog, ProspectContact
from ai.matcher import analyze_match, generate_cover_letter
from ai.email_apply import send_application_email
from ai.outreach import generate_outreach_email

PROFILE_YAML_PATH = UPLOAD_DIR / "plain_text_resume.yaml"
CONFIG_YAML_PATH = UPLOAD_DIR / "config.yaml"


def load_profile_yaml() -> dict:
    if PROFILE_YAML_PATH.exists():
        try:
            with open(PROFILE_YAML_PATH, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


def load_job_config() -> dict:
    if CONFIG_YAML_PATH.exists():
        try:
            with open(CONFIG_YAML_PATH, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}
from scrapers.indeed import IndeedScraper
from scrapers.hellowork import HelloWorkScraper
from scrapers.linkedin import LinkedInScraper
from scrapers.wttj import WTTJScraper
from scrapers.apec import ApecScraper
from scrapers.francetravail import FranceTravailScraper
from scrapers.cadremploi import CadremploiScraper
from scrapers.monster import MonsterScraper
from scrapers.jobijoba import JobijobasScraper
from scrapers.meteojob import MeteojobScraper

app = FastAPI(title="AutoJob", description="Candidature automatique")

# Static files and templates
(BASE_DIR / "static").mkdir(exist_ok=True)
(BASE_DIR / "templates").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Init DB on startup
init_db()

SCRAPERS = {
    "indeed": IndeedScraper(),
    "hellowork": HelloWorkScraper(),
    "linkedin": LinkedInScraper(),
    "wttj": WTTJScraper(),
    "apec": ApecScraper(),
    "francetravail": FranceTravailScraper(),
    "cadremploi": CadremploiScraper(),
    "monster": MonsterScraper(),
    "jobijoba": JobijobasScraper(),
    "meteojob": MeteojobScraper(),
}

# --- Track running tasks ---
running_tasks = {"scraping": False, "applying": False}


def extract_cv_text(filepath: str) -> str:
    """Extract text from a PDF CV."""
    text = ""
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        text = f"Erreur extraction PDF: {str(e)}"
    return text.strip()


# ==================== PAGES ====================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ==================== API ====================

@app.post("/api/upload-cv")
async def upload_cv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Seuls les fichiers PDF sont acceptés"}, status_code=400)

    filepath = UPLOAD_DIR / file.filename
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    cv_text = extract_cv_text(str(filepath))

    # Update or create profile
    profile = db.query(UserProfile).first()
    if profile:
        profile.cv_filename = file.filename
        profile.cv_text = cv_text
        profile.updated_at = datetime.utcnow()
    else:
        profile = UserProfile(cv_filename=file.filename, cv_text=cv_text)
        db.add(profile)

    db.commit()
    return {"success": True, "filename": file.filename, "text_length": len(cv_text)}


@app.get("/api/profile")
async def get_profile(db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()
    if not profile:
        return {"exists": False}
    return {
        "exists": True,
        "cv_filename": profile.cv_filename,
        "keywords": profile.keywords,
        "location": profile.location,
        "min_match_score": profile.min_match_score,
        "auto_apply": profile.auto_apply,
        "platforms": profile.platforms,
        "first_name": profile.first_name or "",
        "last_name": profile.last_name or "",
        "email": profile.email or "",
        "phone": profile.phone or "",
        "city": profile.city or "",
        "linkedin_email": profile.linkedin_email or "",
        "smtp_user": profile.smtp_user or "",
    }


@app.post("/api/profile/update")
async def update_profile(
    keywords: str = Form(""),
    location: str = Form("France"),
    min_match_score: float = Form(0.5),
    auto_apply: bool = Form(False),
    platforms: str = Form("indeed,hellowork,wttj,apec,linkedin,francetravail,cadremploi,monster,jobijoba,meteojob"),
    first_name: str = Form(""),
    last_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    city: str = Form(""),
    linkedin_email: str = Form(""),
    linkedin_password: str = Form(""),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    db: Session = Depends(get_db),
):
    profile = db.query(UserProfile).first()
    if not profile:
        return JSONResponse({"error": "Uploadez d'abord votre CV"}, status_code=400)

    profile.keywords = keywords
    profile.location = location
    profile.min_match_score = min_match_score
    profile.auto_apply = auto_apply
    profile.platforms = platforms
    profile.first_name = first_name
    profile.last_name = last_name
    profile.email = email
    profile.phone = phone
    profile.city = city
    if linkedin_email:
        profile.linkedin_email = linkedin_email
    if linkedin_password:
        profile.linkedin_password = linkedin_password
    if smtp_user:
        profile.smtp_user = smtp_user
    if smtp_password:
        profile.smtp_password = smtp_password
    profile.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True}


@app.post("/api/upload-yaml")
async def upload_yaml(file: UploadFile = File(...), yaml_type: str = Form("resume")):
    """Upload plain_text_resume.yaml or config.yaml (style AIHawk)."""
    if not file.filename.lower().endswith((".yaml", ".yml")):
        return JSONResponse({"error": "Fichier YAML requis"}, status_code=400)
    dest = PROFILE_YAML_PATH if yaml_type == "resume" else CONFIG_YAML_PATH
    content = await file.read()
    try:
        yaml.safe_load(content)  # Validate YAML
    except Exception as e:
        return JSONResponse({"error": f"YAML invalide: {e}"}, status_code=400)
    with open(dest, "wb") as f:
        f.write(content)
    return {"success": True, "file": yaml_type, "size": len(content)}


@app.get("/api/yaml-config")
async def get_yaml_config():
    """Get current YAML config and profile."""
    profile = load_profile_yaml()
    config = load_job_config()
    return {
        "profile_loaded": bool(profile),
        "config_loaded": bool(config),
        "profile": profile,
        "config": config,
    }


@app.post("/api/linkedin/login")
async def linkedin_login(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Ouvre un navigateur pour se connecter à LinkedIn et sauvegarde la session."""
    profile = db.query(UserProfile).first()
    if not profile or not profile.linkedin_email:
        return JSONResponse({"error": "Renseignez votre email LinkedIn dans le profil"}, status_code=400)

    scraper = SCRAPERS["linkedin"]
    result = await scraper.login(profile.linkedin_email, profile.linkedin_password or "")
    return result


@app.get("/api/linkedin/status")
async def linkedin_status():
    """Vérifie si la session LinkedIn est active."""
    from pathlib import Path
    cookies_path = Path("uploads/cookies_linkedin.json")
    return {"logged_in": cookies_path.exists() and cookies_path.stat().st_size > 10}


@app.post("/api/search")
async def search_jobs(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if running_tasks["scraping"]:
        return {"error": "Une recherche est déjà en cours"}

    profile = db.query(UserProfile).first()
    if not profile:
        return JSONResponse({"error": "Uploadez d'abord votre CV"}, status_code=400)

    profile_data = {
        "first_name": profile.first_name or "", "last_name": profile.last_name or "",
        "email": profile.email or "", "phone": profile.phone or "", "city": profile.city or "",
        "smtp_user": profile.smtp_user or "", "smtp_password": profile.smtp_password or "",
    }
    background_tasks.add_task(
        _run_search, profile.keywords, profile.location, profile.platforms, profile.cv_text,
        profile.auto_apply, profile.min_match_score, profile.cv_filename, profile_data
    )
    return {"success": True, "message": "Recherche lancée en arrière-plan"}


def _job_passes_filters(job_title: str, job_company: str, config: dict) -> tuple[bool, str]:
    """Check if a job passes AIHawk-style filters from config.yaml."""
    title_lower = job_title.lower()
    company_lower = job_company.lower()

    # Company blacklist
    for blacklisted in config.get("company_blacklist", []):
        if blacklisted.lower() in company_lower:
            return False, f"Entreprise blacklistée: {blacklisted}"

    # Title blacklist
    for word in config.get("title_blacklist", []):
        if word.lower() in title_lower:
            return False, f"Mot blacklisté dans le titre: {word}"

    return True, ""


async def _run_search(keywords: str, location: str, platforms_str: str, cv_text: str,
                      auto_apply: bool = False, min_score: float = 0.5,
                      cv_filename: str = "", profile_data: dict = None):
    running_tasks["scraping"] = True
    platforms = [p.strip() for p in platforms_str.split(",") if p.strip()]
    loop = asyncio.get_event_loop()
    job_config = load_job_config()

    # Use positions from config.yaml if no keywords provided
    if not keywords and job_config.get("positions"):
        keywords = ", ".join(job_config["positions"])

    # Use locations from config.yaml if default
    if location == "France" and job_config.get("locations"):
        location = job_config["locations"][0]

    # Support multiple comma-separated keywords: search each one independently
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not keyword_list:
        keyword_list = [keywords]

    try:
        for platform_name in platforms:
            scraper = SCRAPERS.get(platform_name)
            if not scraper:
                continue

            # Gather jobs for all keywords on this platform
            all_jobs = []
            seen_urls = set()
            for kw in keyword_list:
                try:
                    kw_jobs = await scraper.search(kw, location, max_results=20)
                    for j in kw_jobs:
                        if j.url and j.url not in seen_urls:
                            seen_urls.add(j.url)
                            all_jobs.append(j)
                except Exception as e:
                    print(f"[{platform_name}] Erreur scraping '{kw}': {e}")
                    continue

            jobs = all_jobs

            db = next(get_db())
            try:
                for job in jobs:
                    existing = db.query(JobOffer).filter(JobOffer.url == job.url).first()
                    if existing:
                        continue

                    # Apply AIHawk-style filters
                    if job_config:
                        passes, reason = _job_passes_filters(job.title, job.company, job_config)
                        if not passes:
                            print(f"[FILTRE] {job.title} @ {job.company}: {reason}")
                            continue

                    # Analyze match with AI (run in thread to avoid blocking event loop)
                    try:
                        match_result = await loop.run_in_executor(
                            None, analyze_match, cv_text, job.title, job.description
                        )
                    except Exception:
                        match_result = {"score": 0.5, "reasoning": "Analyse indisponible"}

                    offer = JobOffer(
                        platform=job.platform,
                        title=job.title,
                        company=job.company,
                        location=job.location,
                        description=job.description,
                        url=job.url,
                        salary=job.salary,
                        job_type=job.job_type,
                        posted_date=job.posted_date,
                        match_score=match_result.get("score", 0.5),
                        status="matched",
                    )
                    db.add(offer)
                db.commit()
            finally:
                db.close()
    finally:
        running_tasks["scraping"] = False

    # Auto-apply after search if enabled
    if auto_apply and cv_filename and not running_tasks["applying"]:
        print("[AUTO-APPLY] Lancement automatique des candidatures après recherche...")
        db2 = next(get_db())
        try:
            jobs_to_apply = (
                db2.query(JobOffer)
                .filter(JobOffer.status == "matched")
                .filter(JobOffer.match_score >= min_score)
                .order_by(JobOffer.match_score.desc())
                .limit(50)
                .all()
            )
            job_ids = [j.id for j in jobs_to_apply]
        finally:
            db2.close()
        if job_ids:
            asyncio.create_task(_apply_batch(job_ids, cv_filename, cv_text, profile_data or {}))


@app.get("/api/jobs")
async def get_jobs(
    status: str = None,
    platform: str = None,
    min_score: float = 0,
    db: Session = Depends(get_db),
):
    query = db.query(JobOffer)
    if status:
        query = query.filter(JobOffer.status == status)
    if platform:
        query = query.filter(JobOffer.platform == platform)
    if min_score > 0:
        query = query.filter(JobOffer.match_score >= min_score)

    jobs = query.order_by(JobOffer.match_score.desc()).limit(200).all()
    return [
        {
            "id": j.id,
            "platform": j.platform,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "url": j.url,
            "salary": j.salary,
            "match_score": j.match_score,
            "status": j.status,
            "applied_at": j.applied_at.isoformat() if j.applied_at else None,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@app.post("/api/apply/{job_id}")
async def apply_to_job(job_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = db.query(JobOffer).filter(JobOffer.id == job_id).first()
    if not job:
        return JSONResponse({"error": "Offre non trouvée"}, status_code=404)

    profile = db.query(UserProfile).first()
    if not profile:
        return JSONResponse({"error": "Uploadez d'abord votre CV"}, status_code=400)

    profile_data = {
        "first_name": profile.first_name or "", "last_name": profile.last_name or "",
        "email": profile.email or "", "phone": profile.phone or "", "city": profile.city or "",
        "smtp_user": profile.smtp_user or "", "smtp_password": profile.smtp_password or "",
    }
    background_tasks.add_task(_apply_single, job.id, job.platform, job.url, profile.cv_filename, profile.cv_text, profile_data)
    return {"success": True, "message": "Candidature en cours..."}


async def _apply_single(job_id: int, platform: str, job_url: str, cv_filename: str, cv_text: str, profile_data: dict = None):
    db = next(get_db())
    loop = asyncio.get_event_loop()
    try:
        job = db.query(JobOffer).filter(JobOffer.id == job_id).first()
        if not job:
            return
        cv_path = str(UPLOAD_DIR / cv_filename)

        # Load YAML profile (AIHawk-style) - enriches profile_data
        yaml_profile = load_profile_yaml()
        if yaml_profile and profile_data:
            # Merge YAML profile into profile_data for richer form filling
            pi = yaml_profile.get("personal_information", {})
            profile_data.setdefault("first_name", pi.get("name", profile_data.get("first_name", "")))
            profile_data.setdefault("last_name", pi.get("surname", profile_data.get("last_name", "")))
            profile_data.setdefault("email", pi.get("email", profile_data.get("email", "")))
            profile_data.setdefault("phone", f"{pi.get('phone_prefix', '')}{pi.get('phone', '')}".strip() or profile_data.get("phone", ""))
            profile_data.setdefault("city", pi.get("city", profile_data.get("city", "")))
            profile_data["yaml_profile"] = yaml_profile  # Full profile for LLM

        # Generate cover letter in thread (blocking Ollama call)
        try:
            cover_letter = await loop.run_in_executor(
                None, generate_cover_letter, cv_text, job.title, job.company, job.description
            )
        except Exception as e:
            cover_letter = ""
            print(f"Cover letter error: {e}")

        job.cover_letter = cover_letter

        scraper = SCRAPERS.get(platform)
        if not scraper:
            job.status = "error"
            log = ApplicationLog(job_offer_id=job_id, platform=platform, status="failed", message="Scraper inconnu")
            db.add(log)
            db.commit()
            return

        from types import SimpleNamespace
        profile_ns = SimpleNamespace(**(profile_data or {}))

        # Apply with timeout
        try:
            if platform == "linkedin":
                result = await asyncio.wait_for(
                    scraper.apply(job_url, cv_path, cover_letter, profile=profile_ns),
                    timeout=180
                )
            else:
                result = await asyncio.wait_for(
                    scraper.apply(job_url, cv_path, cover_letter),
                    timeout=90
                )
        except asyncio.TimeoutError:
            result = {"success": False, "message": f"Timeout ({platform})", "contact_email": ""}
        except Exception as e:
            result = {"success": False, "message": f"Erreur {platform}: {str(e)[:100]}", "contact_email": ""}

        # Email fallback: always try if SMTP configured and contact email found
        if not result.get("success") and profile_data:
            smtp_user = profile_data.get("smtp_user", "")
            smtp_password = profile_data.get("smtp_password", "")
            contact_email = result.get("contact_email", "")

            # Also scan message for email addresses
            if not contact_email:
                import re as _re
                found = _re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", result.get("message", ""))
                blocked = {"noreply", "no-reply", "hellowork", "linkedin", "indeed", "apec", "francetravail"}
                contact_email = next((e for e in found if not any(b in e.lower() for b in blocked)), "")

            if smtp_user and smtp_password and contact_email:
                full_name = f"{profile_data.get('first_name', '')} {profile_data.get('last_name', '')}".strip()
                subject = f"Candidature - {job.title} - {full_name}"
                body = cover_letter if cover_letter else (
                    f"Madame, Monsieur,\n\n"
                    f"Je vous adresse ma candidature pour le poste de {job.title} au sein de {job.company or 'votre entreprise'}.\n\n"
                    f"Vous trouverez ci-joint mon CV.\n\n"
                    f"Cordialement,\n{full_name}\n{profile_data.get('phone', '')}\n{smtp_user}"
                )
                print(f"[EMAIL] Envoi candidature à {contact_email} pour {job.title}")
                email_result = await loop.run_in_executor(
                    None, send_application_email,
                    smtp_user, smtp_password, contact_email,
                    subject, body, cv_path, full_name
                )
                if email_result["success"]:
                    result = email_result
                    print(f"[EMAIL] ✓ Candidature envoyée à {contact_email}")

        if result["success"]:
            job.status = "applied"
            job.applied_at = datetime.utcnow()
        else:
            job.status = "error"

        log = ApplicationLog(
            job_offer_id=job_id,
            platform=platform,
            status="success" if result["success"] else "failed",
            message=result.get("message", ""),
        )
        db.add(log)
        db.commit()
    except Exception as e:
        try:
            job = db.query(JobOffer).filter(JobOffer.id == job_id).first()
            if job:
                job.status = "error"
            log = ApplicationLog(
                job_offer_id=job_id, platform=platform, status="failed", message=f"Exception: {str(e)}"
            )
            db.add(log)
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


@app.post("/api/apply-all")
async def apply_all(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if running_tasks["applying"]:
        return {"error": "Des candidatures sont déjà en cours"}

    profile = db.query(UserProfile).first()
    if not profile:
        return JSONResponse({"error": "Uploadez d'abord votre CV"}, status_code=400)

    jobs = (
        db.query(JobOffer)
        .filter(JobOffer.status == "matched")
        .filter(JobOffer.match_score >= profile.min_match_score)
        .order_by(JobOffer.match_score.desc())
        .limit(50)
        .all()
    )

    if not jobs:
        return {"error": "Aucune offre à traiter"}

    profile_data = {
        "first_name": profile.first_name or "", "last_name": profile.last_name or "",
        "email": profile.email or "", "phone": profile.phone or "", "city": profile.city or "",
        "smtp_user": profile.smtp_user or "", "smtp_password": profile.smtp_password or "",
    }
    background_tasks.add_task(_apply_batch, [j.id for j in jobs], profile.cv_filename, profile.cv_text, profile_data)
    return {"success": True, "message": f"Candidature lancée pour {len(jobs)} offres"}


async def _apply_batch(job_ids: list[int], cv_filename: str, cv_text: str, profile_data: dict = None):
    running_tasks["applying"] = True
    try:
        # Separate LinkedIn (sequential, reuses browser) from others (can run faster)
        linkedin_ids = []
        other_ids = []
        for job_id in job_ids:
            db = next(get_db())
            try:
                job = db.query(JobOffer).filter(JobOffer.id == job_id).first()
                if job:
                    (linkedin_ids if job.platform == "linkedin" else other_ids).append(
                        (job_id, job.platform, job.url)
                    )
            finally:
                db.close()

        # Process non-LinkedIn jobs with shorter sleep (they fail fast)
        for job_id, platform, url in other_ids:
            await _apply_single(job_id, platform, url, cv_filename, cv_text, profile_data)
            await asyncio.sleep(1)  # Was 5s, now 1s

        # Process LinkedIn jobs sequentially (reuses browser, no startup overhead)
        for job_id, platform, url in linkedin_ids:
            await _apply_single(job_id, platform, url, cv_filename, cv_text, profile_data)
            await asyncio.sleep(2)  # Brief pause between LinkedIn jobs
    finally:
        running_tasks["applying"] = False


@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    total = db.query(JobOffer).count()
    matched = db.query(JobOffer).filter(JobOffer.status == "matched").count()
    applied = db.query(JobOffer).filter(JobOffer.status == "applied").count()
    errors = db.query(JobOffer).filter(JobOffer.status == "error").count()
    return {
        "total": total,
        "matched": matched,
        "applied": applied,
        "errors": errors,
        "scraping": running_tasks["scraping"],
        "applying": running_tasks["applying"],
    }


@app.get("/api/logs")
async def get_logs(db: Session = Depends(get_db)):
    logs = db.query(ApplicationLog).order_by(ApplicationLog.created_at.desc()).limit(100).all()
    return [
        {
            "id": l.id,
            "job_offer_id": l.job_offer_id,
            "platform": l.platform,
            "status": l.status,
            "message": l.message,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@app.post("/api/reset-errors")
async def reset_errors(db: Session = Depends(get_db)):
    """Remet les offres en erreur au statut 'matched' pour re-tenter."""
    jobs = db.query(JobOffer).filter(JobOffer.status == "error").all()
    for j in jobs:
        j.status = "matched"
    db.commit()
    return {"success": True, "reset": len(jobs)}


@app.post("/api/reset-state")
async def reset_state():
    """Réinitialise les états scraping/applying en cas de blocage."""
    running_tasks["scraping"] = False
    running_tasks["applying"] = False
    return {"success": True}


@app.post("/api/retry/{job_id}")
async def retry_job(job_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Remet un job en 'matched' et relance la candidature."""
    job = db.query(JobOffer).filter(JobOffer.id == job_id).first()
    if not job:
        return JSONResponse({"error": "Offre non trouvée"}, status_code=404)
    job.status = "matched"
    db.commit()

    profile = db.query(UserProfile).first()
    if not profile:
        return JSONResponse({"error": "Uploadez d'abord votre CV"}, status_code=400)

    profile_data = {
        "first_name": profile.first_name or "", "last_name": profile.last_name or "",
        "email": profile.email or "", "phone": profile.phone or "", "city": profile.city or "",
        "smtp_user": profile.smtp_user or "", "smtp_password": profile.smtp_password or "",
    }
    background_tasks.add_task(_apply_single, job.id, job.platform, job.url, profile.cv_filename, profile.cv_text, profile_data)
    return {"success": True, "message": "Nouvelle tentative lancée"}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(JobOffer).filter(JobOffer.id == job_id).first()
    if job:
        db.delete(job)
        db.commit()
    return {"success": True}


# ==================== PROSPECTION (Candidatures Spontanées) ====================

@app.get("/api/prospect/contacts")
async def get_prospect_contacts(status: str = None, db: Session = Depends(get_db)):
    q = db.query(ProspectContact)
    if status:
        q = q.filter(ProspectContact.status == status)
    contacts = q.order_by(ProspectContact.created_at.desc()).limit(500).all()
    return [_contact_to_dict(c) for c in contacts]


@app.post("/api/prospect/add")
async def add_prospect_contact(
    company: str = Form(""),
    company_domain: str = Form(""),
    name: str = Form(""),
    role: str = Form(""),
    email: str = Form(""),
    linkedin_url: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    """Ajouter manuellement un contact prospect."""
    c = ProspectContact(
        company=company, company_domain=company_domain,
        name=name, role=role, email=email,
        linkedin_url=linkedin_url, notes=notes,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"success": True, "contact": _contact_to_dict(c)}


@app.post("/api/prospect/find")
async def find_prospect_contacts(
    background_tasks: BackgroundTasks,
    companies: str = Form(""),
    db: Session = Depends(get_db),
):
    """Chercher des contacts RH/recruteurs sur LinkedIn pour une liste d'entreprises."""
    company_list = [c.strip() for c in companies.split(",") if c.strip()]
    if not company_list:
        return JSONResponse({"error": "Entrez au moins une entreprise"}, status_code=400)
    background_tasks.add_task(_find_contacts_bg, company_list)
    return {"success": True, "message": f"Recherche de contacts pour {len(company_list)} entreprise(s)..."}


async def _find_contacts_bg(company_list: list[str]):
    from scrapers.contact_finder import find_contacts_for_company
    for company in company_list:
        try:
            contacts = await find_contacts_for_company(company, limit=5)
            db = next(get_db())
            try:
                for c in contacts:
                    exists = db.query(ProspectContact).filter(
                        ProspectContact.linkedin_url == c["linkedin_url"]
                    ).first()
                    if not exists:
                        db.add(ProspectContact(
                            company=c["company"],
                            name=c["name"],
                            role=c["role"],
                            linkedin_url=c["linkedin_url"],
                        ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[Prospection] Erreur find contacts {company}: {e}")


@app.post("/api/prospect/generate/{contact_id}")
async def generate_prospect_message(contact_id: int, db: Session = Depends(get_db)):
    """Générer un message personnalisé (email + DM LinkedIn) pour un contact."""
    contact = db.query(ProspectContact).filter(ProspectContact.id == contact_id).first()
    if not contact:
        return JSONResponse({"error": "Contact non trouvé"}, status_code=404)
    profile = db.query(UserProfile).first()
    if not profile:
        return JSONResponse({"error": "Uploadez votre CV d'abord"}, status_code=400)

    loop = asyncio.get_event_loop()
    full_name = f"{profile.first_name or ''} {profile.last_name or ''}".strip()
    result = await loop.run_in_executor(
        None, generate_outreach_email,
        profile.cv_text or "",
        full_name,
        contact.company,
        contact.name,
        contact.role,
    )
    contact.message_subject = result.get("subject", "")
    contact.message_body = result.get("body", "")
    db.commit()
    return {"success": True, "subject": result.get("subject", ""), "body": result.get("body", ""), "linkedin_dm": result.get("linkedin_dm", "")}


@app.post("/api/prospect/send/{contact_id}")
async def send_prospect_message(
    contact_id: int,
    background_tasks: BackgroundTasks,
    channel: str = Form("email"),
    subject: str = Form(""),
    body: str = Form(""),
    db: Session = Depends(get_db),
):
    """Envoyer une candidature spontanée par email ou LinkedIn DM."""
    contact = db.query(ProspectContact).filter(ProspectContact.id == contact_id).first()
    if not contact:
        return JSONResponse({"error": "Contact non trouvé"}, status_code=404)
    profile = db.query(UserProfile).first()
    if not profile:
        return JSONResponse({"error": "Uploadez votre CV d'abord"}, status_code=400)

    if subject:
        contact.message_subject = subject
    if body:
        contact.message_body = body
    contact.channel = channel
    db.commit()

    background_tasks.add_task(_send_prospect_bg, contact_id, channel, profile.id)
    return {"success": True, "message": "Envoi en cours..."}


async def _send_prospect_bg(contact_id: int, channel: str, profile_id: int):
    db = next(get_db())
    try:
        contact = db.query(ProspectContact).filter(ProspectContact.id == contact_id).first()
        profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
        if not contact or not profile:
            return

        loop = asyncio.get_event_loop()
        cv_path = str(UPLOAD_DIR / profile.cv_filename) if profile.cv_filename else ""
        full_name = f"{profile.first_name or ''} {profile.last_name or ''}".strip()

        if channel == "email":
            if not contact.email:
                contact.status = "error"
                contact.notes = (contact.notes or "") + "\nErreur: pas d'email configuré"
                db.commit()
                return
            result = await loop.run_in_executor(
                None, send_application_email,
                profile.smtp_user, profile.smtp_password,
                contact.email, contact.message_subject, contact.message_body,
                cv_path, full_name
            )
            if result["success"]:
                contact.status = "sent"
                contact.sent_at = datetime.utcnow()
            else:
                contact.notes = (contact.notes or "") + f"\n{result['message']}"

        elif channel == "linkedin":
            if not contact.linkedin_url:
                contact.status = "error"
                contact.notes = (contact.notes or "") + "\nErreur: pas d'URL LinkedIn"
                db.commit()
                return
            result = await _send_linkedin_dm(contact.linkedin_url, contact.message_body, profile)
            if result["success"]:
                contact.status = "sent"
                contact.sent_at = datetime.utcnow()
            else:
                contact.notes = (contact.notes or "") + f"\n{result['message']}"

        db.commit()
    except Exception as e:
        try:
            contact.notes = (contact.notes or "") + f"\nException: {str(e)[:100]}"
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def _send_linkedin_dm(linkedin_url: str, message: str, profile) -> dict:
    """Envoyer un DM LinkedIn à un contact."""
    from scrapers.linkedin import LinkedInScraper, _load_cookies
    cookies = _load_cookies()
    if not cookies:
        return {"success": False, "message": "LinkedIn: pas de session. Connectez-vous dans Paramètres."}

    scraper = SCRAPERS.get("linkedin")
    try:
        page = await scraper._get_shared_page()
    except Exception as e:
        return {"success": False, "message": f"Erreur navigateur: {str(e)[:100]}"}

    try:
        from playwright.async_api import async_playwright
        await page.goto(linkedin_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)

        # Click "Se connecter" or "Message" button
        msg_btn = await page.query_selector("button[aria-label*='Message'], a[aria-label*='Message']")
        if not msg_btn:
            msg_btn = await page.query_selector("button:has-text('Message'), a:has-text('Message')")
        if not msg_btn:
            # Try Connect + note
            connect_btn = await page.query_selector("button[aria-label*='Se connecter'], button[aria-label*='Connect']")
            if connect_btn:
                await connect_btn.click()
                await page.wait_for_timeout(1000)
                note_btn = await page.query_selector("button[aria-label*='note'], button:has-text('note'), button:has-text('Ajouter')")
                if note_btn:
                    await note_btn.click()
                    await page.wait_for_timeout(500)
                    textarea = await page.query_selector("textarea")
                    if textarea:
                        await textarea.fill(message[:300])
                        send_btn = await page.query_selector("button[aria-label*='Envoyer'], button:has-text('Envoyer')")
                        if send_btn:
                            await send_btn.click()
                            await page.wait_for_timeout(1000)
                            return {"success": True, "message": "Invitation avec note envoyée"}
            return {"success": False, "message": "LinkedIn: impossible d'envoyer le message"}

        await msg_btn.click()
        await page.wait_for_timeout(1000)
        textarea = await page.query_selector("div[contenteditable='true'], textarea[placeholder]")
        if textarea:
            await textarea.fill(message[:1900])
            await page.wait_for_timeout(300)
            send_btn = await page.query_selector("button[type='submit'], button[aria-label*='Envoyer'], button:has-text('Envoyer')")
            if send_btn:
                await send_btn.click()
                await page.wait_for_timeout(1000)
                return {"success": True, "message": "DM LinkedIn envoyé"}
        return {"success": False, "message": "LinkedIn: champ message introuvable"}
    except Exception as e:
        return {"success": False, "message": f"Erreur LinkedIn DM: {str(e)[:100]}"}
    finally:
        try:
            await page.close()
        except Exception:
            pass


@app.post("/api/prospect/status/{contact_id}")
async def update_prospect_status(
    contact_id: int,
    status: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    contact = db.query(ProspectContact).filter(ProspectContact.id == contact_id).first()
    if not contact:
        return JSONResponse({"error": "Contact non trouvé"}, status_code=404)
    if status:
        contact.status = status
        if status == "replied":
            contact.replied_at = datetime.utcnow()
    if notes:
        contact.notes = notes
    db.commit()
    return {"success": True}


@app.delete("/api/prospect/contacts/{contact_id}")
async def delete_prospect_contact(contact_id: int, db: Session = Depends(get_db)):
    c = db.query(ProspectContact).filter(ProspectContact.id == contact_id).first()
    if c:
        db.delete(c)
        db.commit()
    return {"success": True}


@app.get("/api/prospect/stats")
async def get_prospect_stats(db: Session = Depends(get_db)):
    total = db.query(ProspectContact).count()
    sent = db.query(ProspectContact).filter(ProspectContact.status == "sent").count()
    replied = db.query(ProspectContact).filter(ProspectContact.status == "replied").count()
    interview = db.query(ProspectContact).filter(ProspectContact.status == "interview").count()
    return {"total": total, "sent": sent, "replied": replied, "interview": interview}


def _contact_to_dict(c: ProspectContact) -> dict:
    return {
        "id": c.id, "company": c.company, "company_domain": c.company_domain,
        "name": c.name, "role": c.role, "email": c.email,
        "linkedin_url": c.linkedin_url, "status": c.status, "channel": c.channel,
        "message_subject": c.message_subject, "message_body": c.message_body,
        "sent_at": c.sent_at.isoformat() if c.sent_at else None,
        "replied_at": c.replied_at.isoformat() if c.replied_at else None,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
