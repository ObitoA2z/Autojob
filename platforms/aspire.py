from platforms._mock import MockConnectorMixin
from platforms.base import CampaignCandidate


class AspireConnector(MockConnectorMixin):
    name = "aspire"
    seed = [
        CampaignCandidate(
            platform="aspire",
            external_id="aspire-5001",
            title="Instagram Healthy Snack Story",
            brand="NutriSnap",
            description="Story set with swipe-up and discount code mention.",
            campaign_url="https://aspire.example/campaigns/5001",
            budget=600,
            niche="food",
            target_platform="instagram",
        )
    ]
