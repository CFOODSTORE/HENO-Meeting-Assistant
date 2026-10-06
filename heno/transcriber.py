from __future__ import annotations

import queue
import threading
from typing import Callable

from faster_whisper import WhisperModel

from .audio import AudioChunk


class LocalWhisperTranscriber:
    def __init__(self, model_size: str = "base", language: str = "fr"):
        self.model_size = model_size
        self.language = language
        self.model: WhisperModel | None = None
        self.queue: queue.Queue[AudioChunk] = queue.Queue(maxsize=10)
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.on_text: Callable[[str, str], None] | None = None
        self.on_status: Callable[[str], None] | None = None

    def start(self) -> None:
        self.stop_event.clear()
        self.worker = threading.Thread(target=self._run, daemon=True, name="heno-whisper")
        self.worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=3)

    def submit(self, chunk: AudioChunk) -> None:
        try:
            self.queue.put_nowait(chunk)
        except queue.Full:
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(chunk)
            except queue.Empty:
                pass

    def _ensure_model(self) -> None:
        if self.model is None:
            if self.on_status:
                self.on_status(f"Chargement Whisper '{self.model_size}'… (le premier lancement télécharge le modèle)")
            self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            if self.on_status:
                self.on_status("Whisper prêt")

    def _run(self) -> None:
        try:
            self._ensure_model()
        except Exception as exc:
            if self.on_status:
                self.on_status(f"Erreur Whisper : {exc}")
            return
        while not self.stop_event.is_set():
            try:
                chunk = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                segments, _ = self.model.transcribe(
                    chunk.samples,
                    language=self.language or None,
                    vad_filter=True,
                    beam_size=1,
                    condition_on_previous_text=False,
                    temperature=0.0,
                )
                text = " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
                if text and self.on_text:
                    self.on_text(chunk.source, text)
            except Exception as exc:
                if self.on_status:
                    self.on_status(f"Erreur transcription : {exc}")
