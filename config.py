import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = BASE_DIR / "autojob.db"

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Search config defaults
DEFAULT_SEARCH_KEYWORDS = ""
DEFAULT_LOCATION = "France"
MAX_APPLICATIONS_PER_RUN = 50
HEADLESS_BROWSER = True
