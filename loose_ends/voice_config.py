"""LiveKit and model settings shared by the local web server and voice agent."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .config import PROJECT_ROOT

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - makes the setup error clearer before installation
    load_dotenv = None


@dataclass(frozen=True)
class VoiceSettings:
    livekit_url: str | None
    livekit_api_key: str | None
    livekit_api_secret: str | None
    agent_name: str
    stt_model: str
    stt_language: str
    llm_model: str
    tts_model: str
    tts_voice: str

    @classmethod
    def from_env(cls) -> "VoiceSettings":
        if load_dotenv is not None:
            load_dotenv(PROJECT_ROOT / ".env")
        return cls(
            livekit_url=os.getenv("LIVEKIT_URL") or None,
            livekit_api_key=os.getenv("LIVEKIT_API_KEY") or None,
            livekit_api_secret=os.getenv("LIVEKIT_API_SECRET") or None,
            agent_name=os.getenv("VOICE_AGENT_NAME", "loose-ends-voice"),
            stt_model=os.getenv("VOICE_STT_MODEL", "whisper-large-v3-turbo"),
            stt_language=os.getenv("VOICE_STT_LANGUAGE", "en"),
            llm_model=os.getenv("VOICE_LLM_MODEL", "openai/gpt-oss-20b"),
            tts_model=os.getenv("VOICE_TTS_MODEL", "cartesia/sonic-3"),
            tts_voice=os.getenv(
                "VOICE_TTS_VOICE", "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
            ),
        )

    def missing_livekit_values(self) -> list[str]:
        values = {
            "LIVEKIT_URL": self.livekit_url,
            "LIVEKIT_API_KEY": self.livekit_api_key,
            "LIVEKIT_API_SECRET": self.livekit_api_secret,
        }
        return [name for name, value in values.items() if not value]
