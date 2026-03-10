import asyncio

from backend.database.session import SessionLocal
from backend.services.scanner import scan_campaigns


async def main() -> None:
    db = SessionLocal()
    try:
        result = await scan_campaigns(db)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
