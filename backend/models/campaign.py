from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(512))
    brand: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    campaign_url: Mapped[str] = mapped_column(String(1024), unique=True)
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    niche: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    target_platform: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
