from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.campaign import Campaign
from backend.models.scan_run import ScanRun
from backend.services.connector_registry import get_connectors


async def scan_campaigns(db: Session) -> dict:
    run = ScanRun(status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    inserted = 0
    failures: list[str] = []
    connectors = get_connectors(settings.enabled_platforms)

    for connector in connectors:
        try:
            await connector.login()
            campaigns = await connector.scan_campaigns()
        except Exception as exc:
            failures.append(f"{connector.name}: {exc}")
            continue

        for campaign in campaigns:
            exists = db.query(Campaign).filter(Campaign.campaign_url == campaign.campaign_url).first()
            if exists:
                continue
            db.add(
                Campaign(
                    platform=campaign.platform,
                    external_id=campaign.external_id,
                    title=campaign.title,
                    brand=campaign.brand,
                    description=campaign.description,
                    campaign_url=campaign.campaign_url,
                    budget=campaign.budget,
                    niche=campaign.niche,
                    target_platform=campaign.target_platform,
                    status="new",
                )
            )
            inserted += 1

    run.status = "completed"
    if failures:
        run.summary = f"Inserted {inserted} campaigns; failures={'; '.join(failures)}"
    else:
        run.summary = f"Inserted {inserted} campaigns"
    run.completed_at = datetime.utcnow()
    db.commit()
    return {"run_id": run.id, "inserted": inserted, "failures": failures}
