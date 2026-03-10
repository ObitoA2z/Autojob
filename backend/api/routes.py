from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.celery_app import apply_campaign_task, celery_app, scan_campaigns_task
from backend.database.session import get_db
from backend.models.application import Application
from backend.models.campaign import Campaign
from backend.models.creator_profile import CreatorProfile
from backend.schemas.application import ApplicationOut, StatsOut
from backend.schemas.campaign import CampaignOut
from backend.schemas.profile import CreatorProfileCreate, CreatorProfileOut, CreatorProfileUpdate
from backend.services.auto_apply import auto_apply
from backend.services.metrics import compute_stats
from backend.services.scanner import scan_campaigns

router = APIRouter(prefix="/api", tags=["autoinfluence"])


@router.get("/health")
def healthcheck() -> dict:
    return {"ok": True}


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)) -> dict:
    return compute_stats(db)


@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(
    min_budget: float = Query(default=0.0, ge=0.0),
    niche: str | None = Query(default=None),
    target_platform: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Campaign]:
    query = db.query(Campaign)
    if status:
        query = query.filter(Campaign.status == status)
    if min_budget > 0:
        query = query.filter((Campaign.budget.is_(None)) | (Campaign.budget >= min_budget))
    if niche:
        query = query.filter(Campaign.niche.ilike(f"%{niche}%"))
    if target_platform:
        query = query.filter(Campaign.target_platform.ilike(f"%{target_platform}%"))
    return query.order_by(Campaign.created_at.desc()).limit(200).all()


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(db: Session = Depends(get_db)) -> list[Application]:
    return db.query(Application).order_by(Application.created_at.desc()).limit(200).all()


@router.patch("/applications/{application_id}/status", response_model=ApplicationOut)
def update_application_status(
    application_id: int,
    status: str = Query(..., pattern="^(pending|sent|failed|replied)$"),
    db: Session = Depends(get_db),
) -> Application:
    app = db.query(Application).filter(Application.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.status = status
    db.commit()
    db.refresh(app)
    return app


@router.get("/profile", response_model=CreatorProfileOut | None)
def get_profile(db: Session = Depends(get_db)):
    return db.query(CreatorProfile).first()


@router.post("/profile", response_model=CreatorProfileOut, status_code=201)
def create_profile(payload: CreatorProfileCreate, db: Session = Depends(get_db)) -> CreatorProfile:
    existing = db.query(CreatorProfile).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Creator profile already exists")
    profile = CreatorProfile(**payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.patch("/profile", response_model=CreatorProfileOut)
def update_profile(payload: CreatorProfileUpdate, db: Session = Depends(get_db)) -> CreatorProfile:
    profile = db.query(CreatorProfile).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Creator profile not found")
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in updates.items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/profile", response_model=CreatorProfileOut)
def upsert_profile(payload: CreatorProfileCreate, db: Session = Depends(get_db)) -> CreatorProfile:
    profile = db.query(CreatorProfile).first()
    if profile is None:
        profile = CreatorProfile(**payload.model_dump())
        db.add(profile)
    else:
        for key, value in payload.model_dump().items():
            setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/scan")
async def trigger_scan(db: Session = Depends(get_db)) -> dict:
    return await scan_campaigns(db)


@router.post("/scan/async")
def trigger_scan_async() -> dict:
    task = scan_campaigns_task.delay()
    return {"task_id": task.id, "status": "queued"}


@router.post("/apply/{campaign_id}")
async def trigger_apply(campaign_id: int, db: Session = Depends(get_db)) -> dict:
    result = await auto_apply(db, campaign_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/apply/{campaign_id}/async")
def trigger_apply_async(campaign_id: int) -> dict:
    task = apply_campaign_task.delay(campaign_id)
    return {"task_id": task.id, "status": "queued"}


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    result = AsyncResult(task_id, app=celery_app)
    response: dict = {"task_id": task_id, "state": result.state}
    if result.ready():
        response["result"] = result.result
    return response
