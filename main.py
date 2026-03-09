import asyncio
import os
import shutil
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
from database import init_db, get_db, JobOffer, UserProfile, ApplicationLog
from ai.matcher import analyze_match, generate_cover_letter
from scrapers.indeed import IndeedScraper
from scrapers.hellowork import HelloWorkScraper
from scrapers.linkedin import LinkedInScraper
from scrapers.wttj import WTTJScraper
from scrapers.apec import ApecScraper

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
    }


@app.post("/api/profile/update")
async def update_profile(
    keywords: str = Form(""),
    location: str = Form("France"),
    min_match_score: float = Form(0.5),
    auto_apply: bool = Form(False),
    platforms: str = Form("indeed,hellowork,wttj,apec,linkedin"),
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
    profile.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True}


@app.post("/api/search")
async def search_jobs(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if running_tasks["scraping"]:
        return {"error": "Une recherche est déjà en cours"}

    profile = db.query(UserProfile).first()
    if not profile:
        return JSONResponse({"error": "Uploadez d'abord votre CV"}, status_code=400)

    background_tasks.add_task(
        _run_search, profile.keywords, profile.location, profile.platforms, profile.cv_text
    )
    return {"success": True, "message": "Recherche lancée en arrière-plan"}


async def _run_search(keywords: str, location: str, platforms_str: str, cv_text: str):
    running_tasks["scraping"] = True
    platforms = [p.strip() for p in platforms_str.split(",") if p.strip()]

    try:
        for platform_name in platforms:
            scraper = SCRAPERS.get(platform_name)
            if not scraper:
                continue

            try:
                jobs = await scraper.search(keywords, location, max_results=20)
            except Exception:
                continue

            db = next(get_db())
            try:
                for job in jobs:
                    # Check if already exists
                    existing = db.query(JobOffer).filter(JobOffer.url == job.url).first()
                    if existing:
                        continue

                    # Analyze match with AI
                    match_result = analyze_match(cv_text, job.title, job.description)

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

    background_tasks.add_task(_apply_single, job.id, job.platform, job.url, profile)
    return {"success": True, "message": "Candidature en cours..."}


async def _apply_single(job_id: int, platform: str, job_url: str, profile):
    db = next(get_db())
    try:
        job = db.query(JobOffer).filter(JobOffer.id == job_id).first()
        cv_path = str(UPLOAD_DIR / profile.cv_filename)

        # Generate cover letter
        cover_letter = generate_cover_letter(
            profile.cv_text, job.title, job.company, job.description
        )
        job.cover_letter = cover_letter

        scraper = SCRAPERS.get(platform)
        if not scraper:
            job.status = "error"
            db.commit()
            return

        result = await scraper.apply(job_url, cv_path, cover_letter)

        if result["success"]:
            job.status = "applied"
            job.applied_at = datetime.utcnow()
        else:
            job.status = "error"

        log = ApplicationLog(
            job_offer_id=job_id,
            platform=platform,
            status="success" if result["success"] else "failed",
            message=result["message"],
        )
        db.add(log)
        db.commit()
    except Exception as e:
        try:
            job = db.query(JobOffer).filter(JobOffer.id == job_id).first()
            if job:
                job.status = "error"
            log = ApplicationLog(
                job_offer_id=job_id, platform=platform, status="failed", message=str(e)
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

    background_tasks.add_task(_apply_batch, [j.id for j in jobs], profile)
    return {"success": True, "message": f"Candidature lancée pour {len(jobs)} offres"}


async def _apply_batch(job_ids: list[int], profile):
    running_tasks["applying"] = True
    try:
        for job_id in job_ids:
            db = next(get_db())
            try:
                job = db.query(JobOffer).filter(JobOffer.id == job_id).first()
                if not job:
                    continue
                await _apply_single(job.id, job.platform, job.url, profile)
            finally:
                db.close()
            await asyncio.sleep(5)  # Delay between applications
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


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(JobOffer).filter(JobOffer.id == job_id).first()
    if job:
        db.delete(job)
        db.commit()
    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
