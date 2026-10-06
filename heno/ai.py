from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import requests

from .auth_chatgpt import ChatGPTAuthManager
from .config import Settings

DeltaCallback = Callable[[str], None]


class AIError(RuntimeError):
    pass


@dataclass
class ModelInfo:
    slug: str
    display_name: str


class ChatGPTProvider:
    def __init__(self, settings: Settings, auth: ChatGPTAuthManager):
        self.settings = settings
        self.auth = auth

    def list_models(self) -> list[ModelInfo]:
        token = self.auth.access_token()
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if not response.ok:
            raise AIError(f"Impossible de récupérer les modèles ChatGPT: {response.text[:300]}")
        raw = response.json().get("models", [])
        return [
            ModelInfo(m.get("slug", ""), m.get("display_name") or m.get("slug", ""))
            for m in raw
            if m.get("visibility") == "list" and m.get("slug")
        ]

    def ensure_model(self) -> str:
        models = self.list_models()
        available = {m.slug for m in models}
        if self.settings.chatgpt_model in available:
            return self.settings.chatgpt_model
        if not models:
            raise AIError("Aucun modèle n'est disponible pour ce compte ChatGPT.")
        self.settings.chatgpt_model = models[0].slug
        self.settings.save()
        return models[0].slug

    def generate(self, prompt: str, on_delta: DeltaCallback | None = None) -> str:
        token = self.auth.access_token()
        model = self.settings.chatgpt_model or self.ensure_model()
        payload = {
            "model": model,
            "input": [{"role": "user", "content": prompt}],
            "store": False,
            "stream": True,
        }
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            stream=True,
            timeout=120,
        )
        if not response.ok:
            raise AIError(f"Erreur ChatGPT: {response.text[:500]}")

        text_parts: list[str] = []
        completed = False
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data:"):
                continue
            data = raw_line[5:].strip()
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            etype = event.get("type")
            if etype == "response.output_text.delta":
                delta = event.get("delta", "")
                text_parts.append(delta)
                if on_delta:
                    on_delta(delta)
            elif etype == "response.failed":
                error = ((event.get("response") or {}).get("error") or {})
                code = error.get("code", "unknown_error")
                message = error.get("message") or code
                raise AIError(message)
            elif etype == "response.completed":
                completed = True
        if not completed and not text_parts:
            raise AIError("La réponse ChatGPT s'est terminée sans résultat exploitable.")
        return "".join(text_parts).strip()


class OllamaProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def available_models(self) -> list[str]:
        try:
            response = requests.get(f"{self.settings.ollama_url}/api/tags", timeout=3)
            response.raise_for_status()
            return [m.get("name", "") for m in response.json().get("models", []) if m.get("name")]
        except Exception:
            return []

    def generate(self, prompt: str, on_delta: DeltaCallback | None = None) -> str:
        model = self.settings.ollama_model
        models = self.available_models()
        if not model:
            if not models:
                raise AIError("Ollama n'est pas disponible et aucun modèle local n'est installé.")
            model = models[0]
            self.settings.ollama_model = model
            self.settings.save()
        response = requests.post(
            f"{self.settings.ollama_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": True},
            stream=True,
            timeout=120,
        )
        response.raise_for_status()
        parts: list[str] = []
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            event = json.loads(line)
            delta = event.get("response", "")
            if delta:
                parts.append(delta)
                if on_delta:
                    on_delta(delta)
            if event.get("done"):
                break
        return "".join(parts).strip()
