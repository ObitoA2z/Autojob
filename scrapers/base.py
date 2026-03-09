from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ScrapedJob:
    title: str
    company: str
    location: str
    description: str
    url: str
    platform: str
    salary: str = ""
    job_type: str = ""
    posted_date: str = ""


class BaseScraper(ABC):
    """Base class for all job platform scrapers."""

    platform_name: str = ""

    @abstractmethod
    async def search(self, keywords: str, location: str, max_results: int = 25) -> list[ScrapedJob]:
        """Search for jobs on the platform."""
        pass

    @abstractmethod
    async def apply(self, job_url: str, cv_path: str, cover_letter: str = "") -> dict:
        """Apply to a job. Returns {'success': bool, 'message': str}."""
        pass
