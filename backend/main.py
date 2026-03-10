from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import router
from backend.core.config import settings
from backend.database.base import Base
from backend.database.session import engine
from backend import models  # noqa: F401 - ensure model metadata is registered


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app


app = create_app()
Base.metadata.create_all(bind=engine)
