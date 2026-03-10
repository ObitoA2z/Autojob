from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CreatorProfileBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    niche: str = Field(min_length=1, max_length=128)
    bio: str = Field(default="", max_length=5000)
    audience_size: int = Field(default=0, ge=0)
    platforms: str = Field(default="tiktok,instagram", max_length=256)
    min_budget: int = Field(default=0, ge=0)
    auto_apply: bool = False


class CreatorProfileCreate(CreatorProfileBase):
    pass


class CreatorProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    niche: str | None = Field(default=None, min_length=1, max_length=128)
    bio: str | None = Field(default=None, max_length=5000)
    audience_size: int | None = Field(default=None, ge=0)
    platforms: str | None = Field(default=None, max_length=256)
    min_budget: int | None = Field(default=None, ge=0)
    auto_apply: bool | None = None


class CreatorProfileOut(CreatorProfileBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Backward compatibility alias.
CreatorProfileIn = CreatorProfileCreate
