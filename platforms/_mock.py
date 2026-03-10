from __future__ import annotations

from dataclasses import asdict

from platforms.base import CampaignCandidate


class MockConnectorMixin:
    seed: list[CampaignCandidate]

    async def login(self) -> None:
        # Hook for OpenClaw login flow.
        return None

    async def scan_campaigns(self) -> list[CampaignCandidate]:
        return list(self.seed)

    async def auto_apply(self, campaign: CampaignCandidate, message: str) -> dict:
        # This default implementation is intentionally deterministic.
        return {
            "success": True,
            "platform": campaign.platform,
            "external_id": campaign.external_id,
            "message": "Application submitted through connector mock flow",
            "payload": {"message": message, "campaign": asdict(campaign)},
        }
