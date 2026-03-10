from __future__ import annotations

from openai import OpenAI

from backend.core.config import settings


def generate_application_message(
    creator_name: str,
    niche: str,
    audience_size: int,
    campaign_title: str,
    brand: str,
    campaign_description: str,
) -> str:
    prompt = (
        "Write a short influencer application message in French. "
        "Keep it under 120 words, specific to the campaign, and professional.\n\n"
        f"Creator: {creator_name}\n"
        f"Niche: {niche}\n"
        f"Audience size: {audience_size}\n"
        f"Campaign: {campaign_title}\n"
        f"Brand: {brand}\n"
        f"Description: {campaign_description}\n"
    )

    if not settings.openai_api_key:
        return (
            f"Bonjour {brand}, je suis {creator_name}, createur specialise en {niche}. "
            f"Ma communaute de {audience_size} abonnes est tres engagee sur ce type de contenu. "
            f"Je serais ravi de collaborer sur '{campaign_title}' et de proposer une activation performante."
        )

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=settings.openai_model,
        input=prompt,
    )
    return response.output_text.strip()
