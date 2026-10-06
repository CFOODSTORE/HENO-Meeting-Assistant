from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.signal import resample_poly
import soundcard as sc


@dataclass
class AudioChunk:
    source: str
    samples: np.ndarray
    sample_rate: int = 16000


class AudioCaptureManager:
    def __init__(self, chunk_seconds: int = 5, use_microphone: bool = True, use_system_audio: bool = True):
        self.chunk_seconds = chunk_seconds
        self.use_microphone = use_microphone
        self.use_system_audio = use_system_audio
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.on_chunk: Callable[[AudioChunk], None] | None = None
        self.on_status: Callable[[str], None] | None = None

    def start(self) -> None:
        self._stop.clear()
        if self.use_microphone:
            self._start_thread("Moi", self._capture_microphone)
        if self.use_system_audio:
            self._start_thread("Réunion", self._capture_loopback)
        if not self._threads:
            raise RuntimeError("Activez au moins une source audio.")

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads.clear()

    def _start_thread(self, name: str, target: Callable[[], None]) -> None:
        thread = threading.Thread(target=target, name=f"heno-audio-{name}", daemon=True)
        self._threads.append(thread)
        thread.start()

    @staticmethod
    def _to_mono_16k(audio: np.ndarray, source_rate: int) -> np.ndarray:
        arr = np.asarray(audio, dtype=np.float32)
        if arr.ndim > 1:
            arr = np.mean(arr, axis=1)
        if source_rate != 16000:
            arr = resample_poly(arr, 16000, source_rate).astype(np.float32)
        max_abs = float(np.max(np.abs(arr))) if arr.size else 0.0
        if max_abs > 1.0:
            arr = arr / max_abs
        return arr

    def _emit(self, source: str, audio: np.ndarray, source_rate: int) -> None:
        samples = self._to_mono_16k(audio, source_rate)
        if samples.size == 0:
            return
        rms = float(np.sqrt(np.mean(np.square(samples))))
        if rms < 0.004:
            return
        if self.on_chunk:
            self.on_chunk(AudioChunk(source=source, samples=samples))

    def _capture_microphone(self) -> None:
        samplerate = 48000
        frames = samplerate * self.chunk_seconds
        try:
            mic = sc.default_microphone()
            if mic is None:
                raise RuntimeError("Aucun microphone par défaut détecté.")
            if self.on_status:
                self.on_status(f"Microphone : {mic.name}")
            with mic.recorder(samplerate=samplerate) as recorder:
                while not self._stop.is_set():
                    audio = recorder.record(numframes=frames)
                    self._emit("Moi", audio, samplerate)
        except Exception as exc:
            if self.on_status:
                self.on_status(f"Erreur microphone : {exc}")

    def _capture_loopback(self) -> None:
        samplerate = 48000
        frames = samplerate * self.chunk_seconds
        try:
            speaker = sc.default_speaker()
            if speaker is None:
                raise RuntimeError("Aucune sortie audio par défaut détectée.")
            loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)
            if self.on_status:
                self.on_status(f"Son système : {speaker.name}")
            with loopback.recorder(samplerate=samplerate) as recorder:
                while not self._stop.is_set():
                    audio = recorder.record(numframes=frames)
                    self._emit("Réunion", audio, samplerate)
        except Exception as exc:
            if self.on_status:
                self.on_status(f"Erreur son système : {exc}")
