from platforms._mock import MockConnectorMixin
from platforms.base import CampaignCandidate


class UpfluenceConnector(MockConnectorMixin):
    name = "upfluence"
    seed = [
        CampaignCandidate(
            platform="upfluence",
            external_id="upfluence-3001",
            title="YouTube Tech Accessory Review",
            brand="PulseDock",
            description="Long-form product review for USB-C ecosystem.",
            campaign_url="https://upfluence.example/campaigns/3001",
            budget=1800,
            niche="tech",
            target_platform="youtube",
        )
    ]
