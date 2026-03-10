from datetime import datetime

from pydantic import BaseModel


class CampaignOut(BaseModel):
    id: int
    platform: str
    title: str
    brand: str
    description: str
    campaign_url: str
    budget: float | None
    niche: str | None
    target_platform: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignFilter(BaseModel):
    min_budget: int = 0
    niche: str | None = None
    target_platform: str | None = None
