from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path

APP_NAME = "HENO Meeting Assistant"
APP_DIR = Path(os.getenv("APPDATA") or (Path.home() / ".config")) / "HENO-Meeting-Assistant"
APP_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = APP_DIR / "config.json"


@dataclass
class Settings:
    whisper_model: str = "base"
    language: str = "fr"
    use_microphone: bool = True
    use_system_audio: bool = True
    audio_chunk_seconds: int = 5
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    chatgpt_client_id: str = ""
    chatgpt_email: str = ""
    chatgpt_subject: str = ""
    chatgpt_model: str = ""
    ext_agent_host_id: str = ""

    @classmethod
    def load(cls) -> "Settings":
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                settings = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                settings = cls()
        else:
            settings = cls()
        if not settings.ext_agent_host_id:
            settings.ext_agent_host_id = f"urn:uuid:{uuid.uuid4()}"
            settings.save()
        return settings

    def save(self) -> None:
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CONFIG_PATH)


def app_path(*parts: str) -> Path:
    path = APP_DIR.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
