from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config import DB_PATH

DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class JobOffer(Base):
    __tablename__ = "job_offers"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50), index=True)
    title = Column(String(500))
    company = Column(String(300))
    location = Column(String(300))
    description = Column(Text)
    url = Column(String(1000), unique=True)
    salary = Column(String(200), nullable=True)
    job_type = Column(String(100), nullable=True)  # CDI, CDD, Stage, etc.
    posted_date = Column(String(100), nullable=True)
    match_score = Column(Float, nullable=True)
    status = Column(String(50), default="new")  # new, matched, applied, rejected, error
    applied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    cover_letter = Column(Text, nullable=True)


class UserProfile(Base):
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True)
    cv_filename = Column(String(500))
    cv_text = Column(Text)
    keywords = Column(Text, default="")
    location = Column(String(300), default="France")
    min_match_score = Column(Float, default=0.5)
    auto_apply = Column(Boolean, default=False)
    platforms = Column(Text, default="indeed,hellowork,wttj,apec,linkedin")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApplicationLog(Base):
    __tablename__ = "application_logs"

    id = Column(Integer, primary_key=True, index=True)
    job_offer_id = Column(Integer)
    platform = Column(String(50))
    status = Column(String(50))  # success, failed, pending
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
