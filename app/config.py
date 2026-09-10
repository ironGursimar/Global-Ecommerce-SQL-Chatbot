import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

_db_path = Path(os.getenv("DB_PATH", "ecommerce.db"))
DB_PATH = str(_db_path if _db_path.is_absolute() else BASE_DIR / _db_path)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
MAX_QUESTION_LENGTH = int(os.getenv("MAX_QUESTION_LENGTH", "1000"))
EXPOSE_SQL = os.getenv("EXPOSE_SQL", "false").lower() in {"1", "true", "yes"}
APP_ENV = os.getenv("APP_ENV", "production").lower()
