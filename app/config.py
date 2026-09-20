"""College Growth OS configuration — everything optional, demo-mode by default."""
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLMs (first available wins; fallback = offline bilingual brain)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    github_token: str = ""          # GitHub Models — free inference with a PAT
    llm_model: str = ""

    # Embeddings
    embedding_provider: str = "local"   # "openai" | "local"
    openai_embed_model: str = "text-embedding-3-small"

    # WhatsApp Cloud API (empty = mock mode: logged, never sent)
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""

    # Meta lead-ads webhook
    meta_verify_token: str = "change-me"
    meta_app_secret: str = ""        # if set, X-Hub-Signature-256 is verified on POST webhook

    # Security
    secret_key: str = "change-me-in-production"
    admin_password: str = "seatsetu-admin"   # CHANGE IN PRODUCTION (.env: ADMIN_PASSWORD=...)
    database_url: str = "sqlite:///data/cgos.db"

    class Config:
        env_file = ".env"
        extra = "ignore"


SETTINGS = Settings()
import os as _os

BASE_DIR = Path(__file__).resolve().parent.parent
# Vercel's filesystem is read-only except /tmp — keep the SQLite demo DB there
if _os.getenv("VERCEL") and not SETTINGS.database_url:
    SETTINGS.database_url = "sqlite:////tmp/seatsetu.db"
DATA_DIR = Path("/tmp/seatsetu") if _os.getenv("VERCEL") else BASE_DIR / "data"
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    DATA_DIR = Path("/tmp")  # last-resort writable dir
