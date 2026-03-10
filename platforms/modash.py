from platforms._mock import MockConnectorMixin
from platforms.base import CampaignCandidate


class ModashConnector(MockConnectorMixin):
    name = "modash"
    seed = [
        CampaignCandidate(
            platform="modash",
            external_id="modash-2001",
            title="Instagram Home Decor Reel",
            brand="NordLeaf",
            description="Need creators to showcase before/after room styling.",
            campaign_url="https://modash.example/campaigns/2001",
            budget=900,
            niche="lifestyle",
            target_platform="instagram",
        )
    ]
