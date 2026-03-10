from datetime import datetime

from pydantic import BaseModel


class ApplicationOut(BaseModel):
    id: int
    campaign_id: int
    platform: str
    status: str
    generated_message: str | None
    response_message: str | None
    submitted_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class StatsOut(BaseModel):
    campaigns_found: int
    applications_sent: int
    response_rate: float
