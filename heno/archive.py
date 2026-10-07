from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import app_path


class QAArchive:
    """Persistent local archive for detected questions and HENO suggestions.

    Records are stored as JSON Lines in the user's AppData folder. JSONL keeps
    the archive append-only and resilient if the application closes abruptly.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or app_path("qa_archive.jsonl")
        self._lock = threading.Lock()

    def append(
        self,
        *,
        meeting_id: str,
        meeting_title: str,
        question: str,
        answer: str,
        language: str = "auto",
        asked_at: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "meeting_id": meeting_id,
            "meeting_title": meeting_title or "Réunion sans titre",
            "asked_at": asked_at or datetime.now(timezone.utc).isoformat(),
            "language": language or "auto",
            "question": question.strip(),
            "answer": answer.strip(),
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return record

    def list_records(self, limit: int = 500) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            with self._lock:
                lines = self.path.read_text(encoding="utf-8").splitlines()
            for line in lines[-max(1, limit):]:
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        records.append(item)
                except json.JSONDecodeError:
                    continue
        except OSError:
            return []
        return records

    def meeting_records(self, meeting_id: str) -> list[dict[str, Any]]:
        return [r for r in self.list_records(limit=5000) if r.get("meeting_id") == meeting_id]
