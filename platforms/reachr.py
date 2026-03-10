from platforms._mock import MockConnectorMixin
from platforms.base import CampaignCandidate


class ReachrConnector(MockConnectorMixin):
    name = "reachr"
    seed = [
        CampaignCandidate(
            platform="reachr",
            external_id="reachr-1001",
            title="TikTok Fitness Challenge",
            brand="FitHydra",
            description="UGC campaign for 30-second workout clips.",
            campaign_url="https://reachr.example/campaigns/1001",
            budget=1200,
            niche="fitness",
            target_platform="tiktok",
        )
    ]
