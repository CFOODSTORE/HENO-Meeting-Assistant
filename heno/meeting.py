from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .ai import ChatGPTProvider, OllamaProvider
from .audio import AudioCaptureManager
from .auth_chatgpt import ChatGPTAuthManager
from .config import Settings
from .documents import DocumentStore
from .question import looks_like_question
from .transcriber import LocalWhisperTranscriber


@dataclass
class TranscriptItem:
    time: str
    source: str
    text: str


class MeetingController:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.auth = ChatGPTAuthManager(settings)
        self.chatgpt = ChatGPTProvider(settings, self.auth)
        self.ollama = OllamaProvider(settings)
        self.documents = DocumentStore()
        self.transcript: list[TranscriptItem] = []
        self.audio: AudioCaptureManager | None = None
        self.whisper: LocalWhisperTranscriber | None = None
        self.running = False
        self.last_question = ""
        self.on_transcript: Callable[[TranscriptItem], None] | None = None
        self.on_question: Callable[[str], None] | None = None
        self.on_answer: Callable[[str], None] | None = None
        self.on_answer_delta: Callable[[str], None] | None = None
        self.on_status: Callable[[str], None] | None = None
        self.on_error: Callable[[str], None] | None = None

    def start(self) -> None:
        if self.running:
            return
        self.transcript.clear()
        self.last_question = ""
        self.whisper = LocalWhisperTranscriber(self.settings.whisper_model, self.settings.language)
        self.whisper.on_text = self._on_text
        self.whisper.on_status = self._status
        self.whisper.start()

        self.audio = AudioCaptureManager(
            chunk_seconds=self.settings.audio_chunk_seconds,
            use_microphone=self.settings.use_microphone,
            use_system_audio=self.settings.use_system_audio,
        )
        self.audio.on_chunk = self.whisper.submit
        self.audio.on_status = self._status
        self.audio.start()
        self.running = True
        self._status("Réunion en cours")

    def stop(self) -> None:
        if self.audio:
            self.audio.stop()
        if self.whisper:
            self.whisper.stop()
        self.running = False
        self._status("Réunion arrêtée")

    def _status(self, message: str) -> None:
        if self.on_status:
            self.on_status(message)

    def _on_text(self, source: str, text: str) -> None:
        item = TranscriptItem(time=datetime.now().strftime("%H:%M:%S"), source=source, text=text)
        self.transcript.append(item)
        if self.on_transcript:
            self.on_transcript(item)
        if looks_like_question(text):
            normalized = re.sub(r"\W+", " ", text.lower()).strip()
            if normalized and normalized != self.last_question:
                self.last_question = normalized
                if self.on_question:
                    self.on_question(text)
                threading.Thread(target=self._answer_question, args=(text,), daemon=True).start()

    def _provider_generate(self, prompt: str, on_delta=None) -> str:
        if self.auth.is_connected:
            return self.chatgpt.generate(prompt, on_delta=on_delta)
        return self.ollama.generate(prompt, on_delta=on_delta)

    def _answer_question(self, question: str) -> None:
        recent = self.transcript[-10:]
        recent_text = "\n".join(f"[{x.time}] {x.source}: {x.text}" for x in recent)
        context = self.documents.retrieve(question, limit=4)
        docs = "\n\n".join(f"SOURCE {c.source}:\n{c.text}" for c in context)
        prompt = f"""Tu es HENO, un copilote de réunion professionnel.

Une question vient d'être détectée pendant une réunion. Propose une réponse que l'utilisateur peut prononcer immédiatement.
Réponds en français, de manière institutionnelle, concise, claire et naturelle. Ne fabrique aucun chiffre ni fait.
Si les documents fournis ne permettent pas de confirmer un détail, dis-le explicitement dans la suggestion.

QUESTION DÉTECTÉE:
{question}

CONTEXTE RÉCENT:
{recent_text}

EXTRAITS DE DOCUMENTS (peuvent être vides):
{docs or 'Aucun extrait pertinent.'}

Retourne uniquement la réponse suggérée, sans titre ni commentaire."""
        try:
            answer = self._provider_generate(prompt, on_delta=self.on_answer_delta)
            if self.on_answer:
                self.on_answer(answer)
        except Exception as exc:
            if self.on_error:
                self.on_error(str(exc))

    def build_summary(self) -> str:
        transcript = "\n".join(f"[{x.time}] {x.source}: {x.text}" for x in self.transcript)
        if len(transcript) > 50000:
            transcript = transcript[-50000:]
        prompt = f"""À partir de la transcription suivante, rédige un compte rendu de réunion professionnel en français.
Structure : Objet, principaux points discutés, décisions prises, actions à réaliser (avec responsable et échéance si mentionnés), questions ouvertes et prochaine étape.
N'invente aucune information.

TRANSCRIPTION:
{transcript}"""
        return self._provider_generate(prompt)
