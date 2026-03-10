from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class CampaignCandidate:
    platform: str
    external_id: str
    title: str
    brand: str
    description: str
    campaign_url: str
    budget: float | None = None
    niche: str | None = None
    target_platform: str | None = None


class PlatformConnector(Protocol):
    name: str

    async def login(self) -> None: ...

    async def scan_campaigns(self) -> list[CampaignCandidate]: ...

    async def auto_apply(self, campaign: CampaignCandidate, message: str) -> dict: ...
