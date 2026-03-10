from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class CreatorProfile(Base):
    __tablename__ = "creator_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    niche: Mapped[str] = mapped_column(String(128))
    bio: Mapped[str] = mapped_column(Text)
    audience_size: Mapped[int] = mapped_column(Integer, default=0)
    platforms: Mapped[str] = mapped_column(String(256), default="tiktok,instagram")
    min_budget: Mapped[int] = mapped_column(Integer, default=0)
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
