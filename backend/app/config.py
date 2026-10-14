"""Environment-driven settings. Read once per call so tests can override env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_token: str
    secret_key: str
    llm_provider: str  # ollama | openai | none
    llm_model: str
    llm_base_url: str
    llm_api_key: str
    publisher: str  # mock | live
    slack_webhook_url: str
    slack_signing_secret: str
    public_url: str
    frontend_url: str
    banned_words: tuple[str, ...]
    trending_feed: str
    scheduler_enabled: bool
    oauth_client_ids: dict[str, str]
    oauth_client_secrets: dict[str, str]

    @property
    def db_path(self) -> Path:
        return self.data_dir / "postpilot.db"

    @property
    def checkpoint_path(self) -> Path:
        return self.data_dir / "checkpoints.db"


def get_settings() -> Settings:
    banned = os.getenv("BANNED_WORDS", "guaranteed,100% free,click here,act now")
    return Settings(
        data_dir=Path(os.getenv("POSTPILOT_DATA_DIR", ROOT / "data")),
        api_token=os.getenv("POSTPILOT_TOKEN", "pp-demo-token"),
        secret_key=os.getenv("POSTPILOT_SECRET_KEY", "dev-only-change-me"),
        llm_provider=os.getenv("LLM_PROVIDER", "ollama"),
        llm_model=os.getenv("LLM_MODEL", "qwen2.5:3b"),
        llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        publisher=os.getenv("PUBLISHER", "mock"),
        slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL", ""),
        slack_signing_secret=os.getenv("SLACK_SIGNING_SECRET", ""),
        public_url=os.getenv("PUBLIC_URL", "http://localhost:8050"),
        frontend_url=os.getenv("FRONTEND_URL", "http://localhost:5190"),
        banned_words=tuple(w.strip().lower() for w in banned.split(",") if w.strip()),
        trending_feed=os.getenv("TRENDING_FEED", "https://hnrss.org/frontpage"),
        scheduler_enabled=os.getenv("SCHEDULER_ENABLED", "1") == "1",
        oauth_client_ids={"x": os.getenv("X_CLIENT_ID", ""), "linkedin": os.getenv("LINKEDIN_CLIENT_ID", "")},
        oauth_client_secrets={"x": os.getenv("X_CLIENT_SECRET", ""), "linkedin": os.getenv("LINKEDIN_CLIENT_SECRET", "")},
    )
