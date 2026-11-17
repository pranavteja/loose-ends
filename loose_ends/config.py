"""Configuration for a local Loose Ends installation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # Keeping dotenv optional makes import errors easier to diagnose.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only before dependencies install
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    audio_dir: Path
    database_path: Path
    groq_api_key: str | None
    transcription_model: str
    extraction_model: str
    timezone: str
    host: str
    port: int
    max_audio_bytes: int

    @classmethod
    def from_env(cls) -> "Settings":
        if load_dotenv is not None:
            load_dotenv(PROJECT_ROOT / ".env")
        data_dir = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
        return cls(
            data_dir=data_dir,
            audio_dir=data_dir / "audio",
            database_path=Path(os.getenv("DATABASE_PATH", data_dir / "loose_ends.sqlite3")),
            groq_api_key=os.getenv("GROQ_API_KEY") or None,
            transcription_model=os.getenv("TRANSCRIPTION_MODEL", "whisper-large-v3-turbo"),
            extraction_model=os.getenv("EXTRACTION_MODEL", "openai/gpt-oss-20b"),
            timezone=os.getenv("APP_TIMEZONE", "Asia/Kolkata"),
            host=os.getenv("APP_HOST", "127.0.0.1"),
            port=int(os.getenv("APP_PORT", "7861")),
            # Groq's free-tier speech-to-text attachment limit is 25 MB.
            max_audio_bytes=int(os.getenv("MAX_AUDIO_BYTES", str(25 * 1024 * 1024))),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
