import asyncio

from celery import Celery

from backend.core.config import settings
from backend.database.session import SessionLocal
from backend.services.auto_apply import auto_apply
from backend.services.scanner import scan_campaigns

celery_app = Celery("autoinfluence", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task(name="tasks.scan_campaigns")
def scan_campaigns_task() -> dict:
    db = SessionLocal()
    try:
        return asyncio.run(scan_campaigns(db))
    finally:
        db.close()


@celery_app.task(name="tasks.apply_campaign")
def apply_campaign_task(campaign_id: int) -> dict:
    db = SessionLocal()
    try:
        return asyncio.run(auto_apply(db, campaign_id))
    finally:
        db.close()
