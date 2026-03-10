from __future__ import annotations

import asyncio
import logging

from backend.core.config import settings
from backend.database.session import SessionLocal
from backend.services.scanner import scan_campaigns

logger = logging.getLogger(__name__)


async def run_scheduler(interval_seconds: int = 1800) -> None:
    while True:
        db = SessionLocal()
        try:
            result = await scan_campaigns(db)
            logger.info("Scanner run: %s", result)
        except Exception as exc:
            logger.exception("Scheduler run failed: %s", exc)
        finally:
            db.close()
        await asyncio.sleep(interval_seconds)


def run() -> None:
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    run()
