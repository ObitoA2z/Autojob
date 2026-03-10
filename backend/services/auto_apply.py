from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ai import generate_application_message
from automation.browser import BrowserAutomation
from backend.models.application import Application
from backend.models.campaign import Campaign
from backend.models.creator_profile import CreatorProfile
from backend.services.connector_registry import get_connectors
from platforms.base import CampaignCandidate


async def auto_apply(db: Session, campaign_id: int) -> dict:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return {"success": False, "message": "Campaign not found"}

    profile = db.query(CreatorProfile).first()
    if not profile:
        return {
            "success": False,
            "message": "Creator profile is missing. Create it with POST /api/profile first.",
        }

    if campaign.budget is not None and campaign.budget < profile.min_budget:
        return {"success": False, "message": "Campaign budget below threshold"}

    if profile.niche and campaign.niche and profile.niche.lower() not in campaign.niche.lower():
        return {"success": False, "message": "Niche mismatch"}

    if campaign.target_platform and campaign.target_platform.lower() not in profile.platforms.lower():
        return {"success": False, "message": "Target platform mismatch"}

    message = generate_application_message(
        creator_name=profile.full_name,
        niche=profile.niche,
        audience_size=profile.audience_size,
        campaign_title=campaign.title,
        brand=campaign.brand,
        campaign_description=campaign.description,
    )

    connector = None
    for item in get_connectors(campaign.platform):
        connector = item
        break

    if connector is None:
        return {"success": False, "message": f"Connector not found for {campaign.platform}"}

    candidate = CampaignCandidate(
        platform=campaign.platform,
        external_id=campaign.external_id,
        title=campaign.title,
        brand=campaign.brand,
        description=campaign.description,
        campaign_url=campaign.campaign_url,
        budget=campaign.budget,
        niche=campaign.niche,
        target_platform=campaign.target_platform,
    )

    try:
        await connector.login()
        connector_result = await connector.auto_apply(campaign=candidate, message=message)
    except Exception as exc:
        connector_result = {"success": False, "message": f"Connector apply failure: {exc}"}

    if not connector_result.get("success"):
        connector_result = await BrowserAutomation().submit_application(campaign.campaign_url, message)

    app_row = Application(
        campaign_id=campaign.id,
        platform=campaign.platform,
        status="sent" if connector_result.get("success") else "failed",
        generated_message=message,
        response_message=connector_result.get("message", ""),
        submitted_at=datetime.utcnow() if connector_result.get("success") else None,
    )
    db.add(app_row)
    campaign.status = "applied" if connector_result.get("success") else "error"
    db.commit()
    db.refresh(app_row)

    return {
        "success": bool(connector_result.get("success")),
        "application_id": app_row.id,
        "message": connector_result.get("message", ""),
    }
