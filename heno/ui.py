from __future__ import annotations

import html
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from docx import Document

from .config import Settings
from .meeting import MeetingController, TranscriptItem


class Bridge(QObject):
    transcript = Signal(object)
    question = Signal(str)
    answer = Signal(str)
    answer_delta = Signal(str)
    status = Signal(str)
    error = Signal(str)
    connected = Signal(str)
    summary = Signal(str)
    auth_finished = Signal()
    summary_finished = Signal()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        self.controller = MeetingController(self.settings)
        self.bridge = Bridge()
        self._wire_backend()
        self.setWindowTitle("HENO — Meeting Assistant")
        self.resize(1250, 760)
        self.setMinimumSize(980, 640)
        self.current_answer = ""
        self.current_summary = ""
        self._build_ui()
        self._apply_style()
        self._refresh_auth_state()

    def _wire_backend(self) -> None:
        self.controller.on_transcript = lambda item: self.bridge.transcript.emit(item)
        self.controller.on_question = lambda q: self.bridge.question.emit(q)
        self.controller.on_answer = lambda a: self.bridge.answer.emit(a)
        self.controller.on_answer_delta = lambda d: self.bridge.answer_delta.emit(d)
        self.controller.on_status = lambda s: self.bridge.status.emit(s)
        self.controller.on_error = lambda e: self.bridge.error.emit(e)
        self.bridge.transcript.connect(self._append_transcript)
        self.bridge.question.connect(self._show_question)
        self.bridge.answer.connect(self._finish_answer)
        self.bridge.answer_delta.connect(self._append_answer_delta)
        self.bridge.status.connect(self._set_status)
        self.bridge.error.connect(self._show_error)
        self.bridge.connected.connect(self._connected)
        self.bridge.summary.connect(self._summary_ready)
        self.bridge.auth_finished.connect(lambda: self.auth_button.setEnabled(True))
        self.bridge.summary_finished.connect(lambda: self.summary_button.setEnabled(True))

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(250)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(22, 26, 22, 26)
        sl.setSpacing(12)

        logo = QLabel("HENO")
        logo.setObjectName("logo")
        sub = QLabel("MEETING ASSISTANT")
        sub.setObjectName("subtitle")
        sl.addWidget(logo)
        sl.addWidget(sub)
        sl.addSpacing(20)

        self.auth_button = QPushButton("Continuer avec ChatGPT")
        self.auth_button.clicked.connect(self.connect_chatgpt)
        sl.addWidget(self.auth_button)
        self.auth_label = QLabel("Non connecté")
        self.auth_label.setWordWrap(True)
        self.auth_label.setObjectName("muted")
        sl.addWidget(self.auth_label)

        sl.addSpacing(10)
        sl.addWidget(QLabel("Transcription locale"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium"])
        self.model_combo.setCurrentText(self.settings.whisper_model)
        self.model_combo.currentTextChanged.connect(self._save_settings)
        sl.addWidget(self.model_combo)

        self.mic_check = QCheckBox("Microphone")
        self.mic_check.setChecked(self.settings.use_microphone)
        self.mic_check.stateChanged.connect(self._save_settings)
        self.system_check = QCheckBox("Son de l'ordinateur")
        self.system_check.setChecked(self.settings.use_system_audio)
        self.system_check.stateChanged.connect(self._save_settings)
        sl.addWidget(self.mic_check)
        sl.addWidget(self.system_check)

        self.docs_button = QPushButton("Ajouter des documents")
        self.docs_button.clicked.connect(self.add_documents)
        sl.addWidget(self.docs_button)
        self.docs_label = QLabel("0 document")
        self.docs_label.setObjectName("muted")
        sl.addWidget(self.docs_label)
        sl.addStretch(1)

        self.meeting_title = QLineEdit()
        self.meeting_title.setPlaceholderText("Titre de la réunion")
        sl.addWidget(self.meeting_title)
        self.summary_button = QPushButton("Générer le compte rendu")
        self.summary_button.clicked.connect(self.generate_summary)
        sl.addWidget(self.summary_button)
        self.export_button = QPushButton("Exporter Word")
        self.export_button.clicked.connect(self.export_word)
        sl.addWidget(self.export_button)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(16)

        top = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("statusDot")
        self.status_label = QLabel("Prêt")
        self.status_label.setObjectName("muted")
        top.addWidget(self.status_dot)
        top.addWidget(self.status_label)
        top.addStretch(1)
        self.start_button = QPushButton("Démarrer la réunion")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.toggle_meeting)
        top.addWidget(self.start_button)
        cl.addLayout(top)

        columns = QHBoxLayout()
        columns.setSpacing(16)

        left_card = QFrame()
        left_card.setObjectName("card")
        left_layout = QVBoxLayout(left_card)
        left_title = QLabel("Transcription en direct")
        left_title.setObjectName("sectionTitle")
        left_layout.addWidget(left_title)
        self.transcript_view = QTextEdit()
        self.transcript_view.setReadOnly(True)
        left_layout.addWidget(self.transcript_view)

        right_card = QFrame()
        right_card.setObjectName("card")
        right_layout = QVBoxLayout(right_card)
        right_title = QLabel("HENO — Réponse suggérée")
        right_title.setObjectName("sectionTitle")
        right_layout.addWidget(right_title)
        qlabel = QLabel("QUESTION DÉTECTÉE")
        qlabel.setObjectName("eyebrow")
        right_layout.addWidget(qlabel)
        self.question_view = QTextEdit()
        self.question_view.setReadOnly(True)
        self.question_view.setMaximumHeight(150)
        right_layout.addWidget(self.question_view)
        alabel = QLabel("RÉPONSE")
        alabel.setObjectName("eyebrow")
        right_layout.addWidget(alabel)
        self.answer_view = QTextEdit()
        self.answer_view.setReadOnly(True)
        right_layout.addWidget(self.answer_view)
        self.copy_button = QPushButton("Copier la réponse")
        self.copy_button.clicked.connect(self.copy_answer)
        right_layout.addWidget(self.copy_button)

        columns.addWidget(left_card, 3)
        columns.addWidget(right_card, 2)
        cl.addLayout(columns, 1)

        outer.addWidget(sidebar)
        outer.addWidget(content, 1)
        self.setCentralWidget(root)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #0b1220; color: #e8eef7; font-family: 'Segoe UI'; font-size: 14px; }
            #sidebar { background: #101a2d; border-right: 1px solid #23304a; }
            #logo { font-size: 32px; font-weight: 800; color: #5eead4; letter-spacing: 2px; }
            #subtitle { color: #8fa1bb; font-size: 11px; letter-spacing: 2px; }
            #muted { color: #8fa1bb; }
            #statusDot { color: #5eead4; font-size: 16px; }
            #card { background: #111c31; border: 1px solid #22314d; border-radius: 14px; }
            #sectionTitle { font-size: 18px; font-weight: 700; }
            #eyebrow { font-size: 11px; font-weight: 700; color: #5eead4; letter-spacing: 1px; margin-top: 6px; }
            QTextEdit, QLineEdit, QComboBox { background: #0c1526; border: 1px solid #2b3c5d; border-radius: 9px; padding: 8px; color: #edf4ff; }
            QPushButton { background: #1a2a45; border: 1px solid #304768; border-radius: 9px; padding: 10px 12px; color: #edf4ff; }
            QPushButton:hover { background: #223755; }
            QPushButton#primary { background: #14b8a6; color: #06120f; border: none; font-weight: 700; padding: 11px 16px; }
            QPushButton#primary:hover { background: #2dd4bf; }
            QCheckBox { spacing: 8px; }
        """)

    def _save_settings(self) -> None:
        if not hasattr(self, "model_combo"):
            return
        self.settings.whisper_model = self.model_combo.currentText()
        self.settings.use_microphone = self.mic_check.isChecked()
        self.settings.use_system_audio = self.system_check.isChecked()
        self.settings.save()

    def _refresh_auth_state(self) -> None:
        if self.controller.auth.is_connected:
            self.auth_label.setText(f"Connecté : {self.settings.chatgpt_email or 'ChatGPT'}")
            self.auth_button.setText("Reconnecter ChatGPT")
        else:
            self.auth_label.setText("Non connecté — HENO utilisera Ollama si disponible")
            self.auth_button.setText("Continuer avec ChatGPT")

    def connect_chatgpt(self) -> None:
        self.auth_button.setEnabled(False)
        self.auth_label.setText("Ouverture de la connexion ChatGPT…")

        def task():
            try:
                result = self.controller.auth.connect()
                try:
                    self.controller.chatgpt.ensure_model()
                except Exception:
                    pass
                self.bridge.connected.emit(result.get("email") or "ChatGPT")
            except Exception as exc:
                self.bridge.error.emit(str(exc))
            finally:
                self.bridge.auth_finished.emit()

        threading.Thread(target=task, daemon=True).start()

    def _connected(self, email: str) -> None:
        self.auth_label.setText(f"Connecté : {email}")
        self.auth_button.setText("Reconnecter ChatGPT")
        self._set_status("ChatGPT connecté")

    def toggle_meeting(self) -> None:
        self._save_settings()
        if not self.controller.running:
            try:
                self.transcript_view.clear()
                self.question_view.clear()
                self.answer_view.clear()
                self.current_answer = ""
                self.controller.start()
                self.start_button.setText("Arrêter la réunion")
            except Exception as exc:
                self._show_error(str(exc))
        else:
            self.controller.stop()
            self.start_button.setText("Démarrer la réunion")

    def add_documents(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Ajouter des documents de contexte",
            "",
            "Documents (*.pdf *.docx *.xlsx *.xlsm *.txt *.md *.csv)",
        )
        if files:
            self.controller.documents.add_files(files)
            count = len(self.controller.documents.files)
            self.docs_label.setText(f"{count} document{'s' if count > 1 else ''}")
            self._set_status("Documents de contexte chargés")

    def _append_transcript(self, item: TranscriptItem) -> None:
        color = "#5eead4" if item.source == "Moi" else "#93c5fd"
        self.transcript_view.append(
            f"<span style='color:#7185a6'>{html.escape(item.time)}</span> "
            f"<b style='color:{color}'>{html.escape(item.source)}</b> : {html.escape(item.text)}"
        )

    def _show_question(self, question: str) -> None:
        self.question_view.setPlainText(question)
        self.answer_view.clear()
        self.current_answer = ""
        self._set_status("Question détectée — HENO prépare une réponse")

    def _append_answer_delta(self, delta: str) -> None:
        self.current_answer += delta
        self.answer_view.setPlainText(self.current_answer)
        cursor = self.answer_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.answer_view.setTextCursor(cursor)

    def _finish_answer(self, answer: str) -> None:
        self.current_answer = answer
        self.answer_view.setPlainText(answer)
        self._set_status("Réponse prête")

    def copy_answer(self) -> None:
        QApplication.clipboard().setText(self.answer_view.toPlainText())
        self._set_status("Réponse copiée")

    def generate_summary(self) -> None:
        if not self.controller.transcript:
            self._show_error("Aucune transcription disponible.")
            return
        self.summary_button.setEnabled(False)
        self._set_status("Génération du compte rendu…")

        def task():
            try:
                summary = self.controller.build_summary()
                self.bridge.summary.emit(summary)
            except Exception as exc:
                self.bridge.error.emit(str(exc))
            finally:
                self.bridge.summary_finished.emit()

        threading.Thread(target=task, daemon=True).start()

    def _summary_ready(self, summary: str) -> None:
        self.current_summary = summary
        self._set_status("Compte rendu prêt")
        box = QMessageBox(self)
        box.setWindowTitle("Compte rendu HENO")
        box.setText("Le compte rendu a été généré. Utilisez « Exporter Word » pour le sauvegarder.")
        box.setDetailedText(summary)
        box.exec()

    def export_word(self) -> None:
        if not self.controller.transcript and not self.current_summary:
            self._show_error("Rien à exporter pour le moment.")
            return
        suggested = (self.meeting_title.text().strip() or "Compte-rendu-HENO").replace("/", "-") + ".docx"
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le compte rendu", suggested, "Word (*.docx)")
        if not path:
            return
        doc = Document()
        doc.add_heading(self.meeting_title.text().strip() or "Compte rendu de réunion", level=0)
        doc.add_paragraph("Généré avec HENO — Meeting Assistant")
        if self.current_summary:
            doc.add_heading("Synthèse", level=1)
            for line in self.current_summary.splitlines():
                if line.strip():
                    doc.add_paragraph(line.strip())
        doc.add_heading("Transcription", level=1)
        for item in self.controller.transcript:
            p = doc.add_paragraph()
            p.add_run(f"[{item.time}] {item.source}: ").bold = True
            p.add_run(item.text)
        doc.save(path)
        self._set_status(f"Exporté : {Path(path).name}")

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _show_error(self, message: str) -> None:
        self._set_status("Erreur")
        QMessageBox.critical(self, "HENO", message)

    def closeEvent(self, event):
        if self.controller.running:
            self.controller.stop()
        super().closeEvent(event)
