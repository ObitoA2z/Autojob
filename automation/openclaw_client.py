from __future__ import annotations

import logging

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)


class OpenClawClient:
    def __init__(self) -> None:
        self.enabled = settings.openclaw_enabled
        self.base_url = settings.openclaw_base_url.rstrip("/")

    async def run_action(self, action: str, payload: dict) -> dict:
        if not self.enabled:
            return {"success": False, "message": "OpenClaw disabled"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/actions/{action}",
                    json=payload,
                )
            if resp.status_code >= 400:
                return {"success": False, "message": f"OpenClaw HTTP {resp.status_code}"}
            return {"success": True, "data": resp.json()}
        except Exception as exc:
            logger.warning("OpenClaw call failed: %s", exc)
            return {"success": False, "message": str(exc)}
