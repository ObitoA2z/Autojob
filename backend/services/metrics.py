from sqlalchemy.orm import Session

from backend.models.application import Application
from backend.models.campaign import Campaign


def compute_stats(db: Session) -> dict:
    total_campaigns = db.query(Campaign).count()
    sent_apps = db.query(Application).filter(Application.status.in_(["sent", "replied"])).count()
    replied = db.query(Application).filter(Application.status == "replied").count()
    response_rate = (replied / sent_apps * 100.0) if sent_apps else 0.0
    return {
        "campaigns_found": total_campaigns,
        "applications_sent": sent_apps,
        "response_rate": round(response_rate, 2),
    }
