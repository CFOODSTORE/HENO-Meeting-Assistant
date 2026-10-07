from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .ai import ChatGPTProvider, OllamaProvider
from .archive import QAArchive
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


@dataclass
class QAItem:
    asked_at: str
    question: str
    answer: str


class MeetingController:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.auth = ChatGPTAuthManager(settings)
        self.chatgpt = ChatGPTProvider(settings, self.auth)
        self.ollama = OllamaProvider(settings)
        self.documents = DocumentStore()
        self.archive = QAArchive()
        self.transcript: list[TranscriptItem] = []
        self.qa_history: list[QAItem] = []
        self.audio: AudioCaptureManager | None = None
        self.whisper: LocalWhisperTranscriber | None = None
        self.running = False
        self.last_question = ""
        self.meeting_id = ""
        self.meeting_title = ""
        self.on_transcript: Callable[[TranscriptItem], None] | None = None
        self.on_question: Callable[[str], None] | None = None
        self.on_answer: Callable[[str], None] | None = None
        self.on_answer_delta: Callable[[str], None] | None = None
        self.on_qa_archived: Callable[[QAItem], None] | None = None
        self.on_status: Callable[[str], None] | None = None
        self.on_error: Callable[[str], None] | None = None

    def start(self) -> None:
        if self.running:
            return
        self.transcript.clear()
        self.qa_history.clear()
        self.last_question = ""
        self.meeting_id = str(uuid.uuid4())
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

    def _language_instruction(self) -> str:
        if self.settings.language == "fr":
            return "Réponds en français."
        if self.settings.language == "en":
            return "Answer in English."
        return "Réponds dans la même langue que la question : français si la question est en français, English if the question is in English."

    def _answer_question(self, question: str) -> None:
        recent = self.transcript[-10:]
        recent_text = "\n".join(f"[{x.time}] {x.source}: {x.text}" for x in recent)
        context = self.documents.retrieve(question, limit=4)
        docs = "\n\n".join(f"SOURCE {c.source}:\n{c.text}" for c in context)
        prompt = f"""Tu es HENO, un copilote de réunion professionnel bilingue français/anglais.

Une question vient d'être détectée pendant une réunion. Propose une réponse que l'utilisateur peut prononcer immédiatement.
{self._language_instruction()}
La réponse doit être institutionnelle, concise, claire et naturelle. Ne fabrique aucun chiffre ni fait.
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
            asked_at = datetime.now(timezone.utc).isoformat()
            qa = QAItem(asked_at=asked_at, question=question, answer=answer)
            self.qa_history.append(qa)
            self.archive.append(
                meeting_id=self.meeting_id or str(uuid.uuid4()),
                meeting_title=self.meeting_title,
                question=question,
                answer=answer,
                language=self.settings.language,
                asked_at=asked_at,
            )
            if self.on_qa_archived:
                self.on_qa_archived(qa)
            if self.on_answer:
                self.on_answer(answer)
        except Exception as exc:
            if self.on_error:
                self.on_error(str(exc))

    def build_summary(self) -> str:
        transcript = "\n".join(f"[{x.time}] {x.source}: {x.text}" for x in self.transcript)
        if len(transcript) > 50000:
            transcript = transcript[-50000:]
        qa_text = "\n\n".join(
            f"QUESTION: {item.question}\nSUGGESTION HENO: {item.answer}" for item in self.qa_history
        ) or "Aucune question archivée."

        if self.settings.language == "en":
            language_rule = "Write the report in English."
        elif self.settings.language == "fr":
            language_rule = "Rédige le compte rendu en français."
        else:
            language_rule = "Utilise la langue dominante de la réunion. Si la réunion est réellement bilingue, rédige en français avec les formulations anglaises importantes conservées entre guillemets."

        prompt = f"""À partir de la transcription et de l'archive questions/réponses ci-dessous, rédige un compte rendu professionnel structuré.
{language_rule}
N'invente aucune information. Distingue explicitement les faits, les hypothèses et les suggestions HENO.

Structure obligatoire :
1. Objet et contexte de la réunion
2. Thématiques discutées
3. Points clés par thématique
4. Hypothèses / suppositions émises pendant la discussion
5. Questions posées pendant la réunion
6. Réponses ou éléments de réponse proposés par HENO (préciser qu'il s'agit de suggestions, pas nécessairement de décisions)
7. Décisions effectivement prises
8. Actions à réaliser, avec responsable et échéance si mentionnés
9. Questions ouvertes / points à vérifier
10. Prochaine étape

TRANSCRIPTION:
{transcript}

ARCHIVE QUESTIONS / RÉPONSES HENO:
{qa_text}"""
        return self._provider_generate(prompt)
