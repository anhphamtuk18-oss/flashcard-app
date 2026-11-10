"""Ứng dụng học từ vựng Lexi, giao diện được thiết kế trong mainWindow.ui."""

from __future__ import annotations

import json
import difflib
import queue
import random
import re
import sys
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)


APP_DIR = Path(__file__).resolve().parent
UI_FILE = APP_DIR / "mainWindow.ui"
DATA_FILE = APP_DIR / "data" / "flashcards.json"
VOSK_MODEL_NAME = "vosk-model-small-en-us-0.15"
VOSK_MODEL_DIR = APP_DIR / "models" / VOSK_MODEL_NAME
VOSK_MODEL_URL = f"https://alphacephei.com/vosk/models/{VOSK_MODEL_NAME}.zip"


class TextToSpeechWorker(QtCore.QThread):
    failed = QtCore.pyqtSignal(str)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text

    def run(self):
        try:
            import pyttsx3

            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            for voice in voices:
                description = f"{voice.id} {voice.name} {voice.languages}".lower()
                if "en" in description or "english" in description:
                    engine.setProperty("voice", voice.id)
                    break
            engine.setProperty("rate", 145)
            engine.say(self.text)
            engine.runAndWait()
            engine.stop()
        except Exception as exc:
            self.failed.emit(str(exc))


class ModelDownloadWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int)
    completed = QtCore.pyqtSignal()
    failed = QtCore.pyqtSignal(str)

    def run(self):
        models_dir = VOSK_MODEL_DIR.parent
        archive_path = models_dir / f"{VOSK_MODEL_NAME}.zip.part"
        try:
            models_dir.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(
                VOSK_MODEL_URL, headers={"User-Agent": "Lexi-Flashcard/1.0"}
            )
            with urllib.request.urlopen(request, timeout=40) as response, archive_path.open("wb") as archive:
                total_size = int(response.headers.get("Content-Length", "0"))
                downloaded = 0
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    archive.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        self.progress.emit(min(100, int(downloaded * 100 / total_size)))

            root = models_dir.resolve()
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    destination = (models_dir / member.filename).resolve()
                    if destination != root and root not in destination.parents:
                        raise ValueError("Tệp model tải về có đường dẫn không hợp lệ.")
                archive.extractall(models_dir)

            if not VOSK_MODEL_DIR.is_dir():
                raise RuntimeError("Không tìm thấy thư mục model sau khi giải nén.")
            self.completed.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            try:
                archive_path.unlink(missing_ok=True)
            except OSError:
                pass


class PronunciationWorker(QtCore.QThread):
    status = QtCore.pyqtSignal(str)
    result_ready = QtCore.pyqtSignal(str)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, model_dir, parent=None):
        super().__init__(parent)
        self.model_dir = model_dir

    def run(self):
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model

            self.status.emit("Đang nạp nhận dạng tiếng Anh...")
            model = Model(str(self.model_dir))
            input_device = sd.query_devices(kind="input")
            sample_rate = int(input_device["default_samplerate"])
            recognizer = KaldiRecognizer(model, sample_rate)
            audio_queue = queue.Queue()

            def audio_callback(indata, _frames, _time_info, _status):
                audio_queue.put(bytes(indata))

            self.status.emit("Đang nghe trong 5 giây — hãy đọc từ trên thẻ.")
            started_at = time.monotonic()
            with sd.RawInputStream(
                samplerate=sample_rate,
                blocksize=8000,
                dtype="int16",
                channels=1,
                callback=audio_callback,
            ):
                while time.monotonic() - started_at < 5:
                    try:
                        audio = audio_queue.get(timeout=0.25)
                    except queue.Empty:
                        continue
                    recognizer.AcceptWaveform(audio)

            recognized = json.loads(recognizer.FinalResult()).get("text", "").strip()
            self.result_ready.emit(recognized)
        except Exception as exc:
            self.failed.emit(str(exc))


def new_id() -> str:
    return uuid.uuid4().hex


class DeckDialog(QDialog):
    """Tạo một chủ đề cùng các từ vựng ban đầu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tạo chủ đề từ vựng")
        self.setMinimumWidth(520)
        self.setStyleSheet("QDialog { background: #F8F9FC; } QLabel { color: #344158; }")

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ví dụ: Tiếng Anh giao tiếp")
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Mô tả ngắn cho bộ thẻ")
        self.description_edit.setMaximumHeight(90)
        self.words_edit = QPlainTextEdit()
        self.words_edit.setPlaceholderText(
            "apple | quả táo | I eat an apple.\n"
            "book | quyển sách | This is my book.\n"
            "Có thể bỏ phần ví dụ: từ | nghĩa"
        )
        self.words_edit.setMinimumHeight(150)

        form = QFormLayout()
        form.addRow("Tên bộ thẻ", self.name_edit)
        form.addRow("Mô tả", self.description_edit)
        form.addRow("Các từ trong chủ đề", self.words_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Tạo chủ đề")
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _accept_if_valid(self):
        if not self.name_edit.text().strip():
            QMessageBox.information(self, "Thiếu tên", "Hãy nhập tên cho chủ đề.")
            return

        cards = []
        for line_number, line in enumerate(self.words_edit.toPlainText().splitlines(), start=1):
            if not line.strip():
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) not in (2, 3) or not parts[0] or not parts[1]:
                QMessageBox.information(
                    self,
                    "Dòng từ vựng chưa đúng",
                    f"Dòng {line_number} cần theo dạng: từ | nghĩa | ví dụ (ví dụ có thể bỏ trống).",
                )
                return
            cards.append({
                "id": new_id(),
                "front": parts[0],
                "back": parts[1],
                "example": parts[2] if len(parts) == 3 else "",
                "known": False,
            })

        if not cards:
            QMessageBox.information(
                self,
                "Chưa có từ vựng",
                "Hãy nhập ít nhất một dòng từ vựng cho chủ đề.",
            )
            return
        self.accept()

    def values(self):
        name = self.name_edit.text().strip()
        description = self.description_edit.toPlainText().strip()
        cards = []
        for line in self.words_edit.toPlainText().splitlines():
            if not line.strip():
                continue
            parts = [part.strip() for part in line.split("|")]
            cards.append({
                "id": new_id(),
                "front": parts[0],
                "back": parts[1],
                "example": parts[2] if len(parts) == 3 else "",
                "known": False,
            })
        return name, description, cards


class FlashcardDialog(QDialog):
    """Hộp thoại nhập hoặc chỉnh sửa một thẻ từ."""

    def __init__(self, parent=None, card=None):
        super().__init__(parent)
        self.setWindowTitle("Chỉnh sửa thẻ" if card else "Thêm thẻ mới")
        self.setMinimumWidth(430)
        self.setStyleSheet("QDialog { background: #F8F9FC; } QLabel { color: #344158; }")

        card = card or {}
        self.front_edit = QLineEdit(card.get("front", ""))
        self.front_edit.setPlaceholderText("Từ hoặc cụm từ cần học")
        self.back_edit = QLineEdit(card.get("back", ""))
        self.back_edit.setPlaceholderText("Nghĩa của từ")
        self.example_edit = QPlainTextEdit(card.get("example", ""))
        self.example_edit.setPlaceholderText("Một câu ví dụ (không bắt buộc)")
        self.example_edit.setMaximumHeight(100)

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Từ vựng", self.front_edit)
        form.addRow("Nghĩa", self.back_edit)
        form.addRow("Ví dụ", self.example_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Lưu thẻ")
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _accept_if_valid(self):
        if not self.front_edit.text().strip() or not self.back_edit.text().strip():
            QMessageBox.information(self, "Thiếu thông tin", "Hãy nhập cả từ vựng và nghĩa của từ.")
            return
        self.accept()

    def values(self):
        return {
            "front": self.front_edit.text().strip(),
            "back": self.back_edit.text().strip(),
            "example": self.example_edit.toPlainText().strip(),
        }


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi(str(UI_FILE), self)

        self.data = self._load_data()
        if not DATA_FILE.exists():
            self._save_data()
        self.current_deck_id = None
        self.card_index = 0
        self.quiz_card = None
        self.quiz_number = 0
        self.quiz_locked = True
        self._tts_worker = None
        self._model_worker = None
        self._pronunciation_worker = None
        self._pronunciation_target = ""
        self.quiz_buttons = [
            self.quizOption1,
            self.quizOption2,
            self.quizOption3,
            self.quizOption4,
        ]
        self.quiz_button_styles = [button.styleSheet() for button in self.quiz_buttons]

        self._configure_table()
        self._connect_signals()
        self._populate_deck_list()
        self._show_page(0)

    def _default_data(self):
        cards = [
            ("apple", "quả táo", "I eat an apple every day."),
            ("beautiful", "xinh đẹp", "The garden looks beautiful in spring."),
            ("borrow", "mượn", "Can I borrow your pen for a minute?"),
            ("careful", "cẩn thận", "Be careful when you cross the street."),
            ("discover", "khám phá, phát hiện", "We hope to discover new places."),
            ("friendly", "thân thiện", "Our new neighbors are very friendly."),
            ("improve", "cải thiện", "Reading helps me improve my English."),
            ("journey", "chuyến đi, hành trình", "The journey took three hours."),
        ]
        return {
            "version": 1,
            "decks": [
                {
                    "id": new_id(),
                    "name": "Tiếng Anh cơ bản",
                    "description": "Từ vựng thông dụng mỗi ngày.",
                    "cards": [
                        {"id": new_id(), "front": f, "back": b, "example": e, "known": False}
                        for f, b, e in cards
                    ],
                }
            ],
        }

    def _load_data(self):
        if DATA_FILE.exists():
            try:
                loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                decks = loaded.get("decks", [])
                if isinstance(decks, list):
                    cleaned_decks = []
                    for deck in decks:
                        if not isinstance(deck, dict) or not str(deck.get("name", "")).strip():
                            continue
                        cards = []
                        for card in deck.get("cards", []):
                            if not isinstance(card, dict):
                                continue
                            front, back = str(card.get("front", "")).strip(), str(card.get("back", "")).strip()
                            if front and back:
                                cards.append({
                                    "id": str(card.get("id") or new_id()),
                                    "front": front,
                                    "back": back,
                                    "example": str(card.get("example", "")),
                                    "known": bool(card.get("known", False)),
                                })
                        cleaned_decks.append({
                            "id": str(deck.get("id") or new_id()),
                            "name": str(deck["name"]).strip(),
                            "description": str(deck.get("description", "")).strip(),
                            "cards": cards,
                        })
                    return {"version": 1, "decks": cleaned_decks}
            except (OSError, json.JSONDecodeError, TypeError, AttributeError):
                pass
        return self._default_data()

    def _save_data(self):
        try:
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary_file = DATA_FILE.with_suffix(".tmp")
            temporary_file.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary_file.replace(DATA_FILE)
        except OSError as exc:
            QMessageBox.warning(self, "Không thể lưu dữ liệu", f"Không ghi được tệp dữ liệu:\n{exc}")

    def _connect_signals(self):
        self.btnNewDeck.clicked.connect(self._create_deck)
        self.btnAddCard.clicked.connect(self._create_card)
        self.btnHeaderQuiz.clicked.connect(self._open_quiz)
        self.navStudy.clicked.connect(lambda: self._show_page(0))
        self.navManage.clicked.connect(lambda: self._show_page(1))
        self.navQuiz.clicked.connect(self._open_quiz)
        self.deckList.currentItemChanged.connect(self._deck_selection_changed)
        self.deckSearch.textChanged.connect(self._populate_deck_list)
        self.btnPrevious.clicked.connect(lambda: self._move_card(-1))
        self.btnNext.clicked.connect(lambda: self._move_card(1))
        self.btnFlip.clicked.connect(self._flip_card)
        self.btnSpeakTarget.clicked.connect(self._speak_current_card)
        self.btnRecordPronunciation.clicked.connect(self._start_pronunciation)
        self.btnKnown.clicked.connect(lambda: self._set_known(True))
        self.btnUnknown.clicked.connect(lambda: self._set_known(False))
        self.cardSearch.textChanged.connect(self._refresh_card_table)
        self.cardsTable.itemSelectionChanged.connect(self._update_table_actions)
        self.btnEditCard.clicked.connect(self._edit_selected_card)
        self.btnDeleteCard.clicked.connect(self._delete_selected_card)
        self.btnNextQuestion.clicked.connect(self._new_quiz_question)
        for button in self.quiz_buttons:
            button.clicked.connect(lambda checked=False, selected=button: self._answer_quiz(selected))

    def _configure_table(self):
        self.cardsTable.setHorizontalHeaderLabels(["Từ vựng", "Nghĩa", "Ví dụ", "Trạng thái"])
        header = self.cardsTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.cardsTable.verticalHeader().setVisible(False)
        self.cardsTable.setShowGrid(False)

    def _deck(self):
        return next(
            (deck for deck in self.data["decks"] if deck["id"] == self.current_deck_id),
            None,
        )

    def _populate_deck_list(self, *_):
        query = self.deckSearch.text().strip().casefold()
        previous_id = self.current_deck_id
        self.deckList.blockSignals(True)
        self.deckList.clear()
        selected_row = -1
        for deck in self.data["decks"]:
            if query and query not in deck["name"].casefold():
                continue
            item = QtWidgets.QListWidgetItem(f"▣  {deck['name']}")
            item.setData(Qt.UserRole, deck["id"])
            item.setToolTip(deck.get("description", ""))
            self.deckList.addItem(item)
            if deck["id"] == previous_id:
                selected_row = self.deckList.count() - 1
        if self.deckList.count() and selected_row < 0:
            selected_row = 0
        if selected_row >= 0:
            self.deckList.setCurrentRow(selected_row)
            self.current_deck_id = self.deckList.currentItem().data(Qt.UserRole)
        else:
            self.current_deck_id = None
        self.deckList.blockSignals(False)
        self._refresh_deck_view()

    def _deck_selection_changed(self, item, _previous):
        self.current_deck_id = item.data(Qt.UserRole) if item else None
        self.card_index = 0
        self._reset_pronunciation_feedback()
        self._refresh_deck_view()

    def _refresh_deck_view(self):
        deck = self._deck()
        has_deck = deck is not None
        self.btnAddCard.setEnabled(has_deck)
        self.btnHeaderQuiz.setEnabled(has_deck)
        if not deck:
            self.pageTitle.setText("Chưa chọn bộ thẻ")
            self.deckDescription.setText("Tạo bộ thẻ mới hoặc xóa nội dung tìm kiếm để tiếp tục.")
            self.metricWordsValue.setText("0")
            self.metricKnownValue.setText("0")
            self.metricProgressValue.setText("0%")
            self._show_card(None)
        else:
            self.pageTitle.setText(deck["name"])
            self.deckDescription.setText(deck.get("description") or "Bộ thẻ từ vựng của bạn")
            cards = deck["cards"]
            known_count = sum(1 for card in cards if card["known"])
            progress = round(known_count / len(cards) * 100) if cards else 0
            self.metricWordsValue.setText(str(len(cards)))
            self.metricKnownValue.setText(str(known_count))
            self.metricProgressValue.setText(f"{progress}%")
            self.card_index = min(self.card_index, max(0, len(cards) - 1))
            self._show_card(cards[self.card_index] if cards else None)
        self._refresh_card_table()

    def _show_card(self, card):
        enabled = card is not None
        for button in (
            self.btnPrevious, self.btnNext, self.btnFlip, self.btnKnown,
            self.btnUnknown, self.btnSpeakTarget, self.btnRecordPronunciation,
        ):
            button.setEnabled(enabled)
        if not enabled:
            self.cardPosition.setText("CHƯA CÓ THẺ")
            self.cardTerm.setText("Tạo thẻ đầu tiên")
            self.cardHint.setText("Nhấn “Thêm thẻ mới” để bắt đầu")
            self.cardTranslation.setText("")
            self.exampleText.setText("")
            self.cardFaceStack.setCurrentIndex(0)
            self.btnFlip.setText("↻  Lật thẻ")
            return
        deck = self._deck()
        self.cardPosition.setText(f"THẺ {self.card_index + 1} / {len(deck['cards'])}")
        self.cardTerm.setText(card["front"])
        self.cardTranslation.setText(card["back"])
        self.exampleText.setText(card.get("example") or "Chưa có câu ví dụ")
        self.cardHint.setText("Từ vựng · Nhấn “Lật thẻ” để xem nghĩa")
        self.cardFaceStack.setCurrentIndex(0)
        self.btnFlip.setText("↻  Lật thẻ")
        self.btnKnown.setText("✓  Đã nhớ từ này" if not card["known"] else "✓  Đã đánh dấu ghi nhớ")

    def _move_card(self, offset):
        deck = self._deck()
        if not deck or not deck["cards"]:
            return
        self.card_index = (self.card_index + offset) % len(deck["cards"])
        self._reset_pronunciation_feedback()
        self._show_card(deck["cards"][self.card_index])

    def _reset_pronunciation_feedback(self):
        self.pronunciationScore.setValue(0)
        self.pronunciationScore.setFormat("-- / 100")
        self.speechResult.setStyleSheet("color: #8793A8; font-size: 9pt;")
        self.speechResult.setText(
            "Nghe mẫu rồi đọc từ vào micro. Điểm là mức khớp của phần nhận dạng giọng nói."
        )

    def _flip_card(self):
        if not self._deck() or not self._deck()["cards"]:
            return
        next_face = 1 - self.cardFaceStack.currentIndex()
        self.cardFaceStack.setCurrentIndex(next_face)
        self.btnFlip.setText("↻  Xem mặt trước" if next_face else "↻  Lật thẻ")

    def _speak_current_card(self):
        deck = self._deck()
        if not deck or not deck["cards"]:
            return
        if self._pronunciation_worker and self._pronunciation_worker.isRunning():
            return
        if self._model_worker and self._model_worker.isRunning():
            return
        if self._tts_worker and self._tts_worker.isRunning():
            return

        word = deck["cards"][self.card_index]["front"]
        self.speechResult.setStyleSheet("color: #8793A8; font-size: 9pt;")
        self.speechResult.setText(f"Đang phát âm mẫu: {word}")
        self.btnSpeakTarget.setEnabled(False)
        self._tts_worker = TextToSpeechWorker(word, self)
        self._tts_worker.failed.connect(self._tts_failed)
        self._tts_worker.finished.connect(self._tts_finished)
        self._tts_worker.start()

    def _tts_failed(self, message):
        self.speechResult.setStyleSheet("color: #B24F4F; font-size: 9pt;")
        self.speechResult.setText(f"Không phát được âm thanh: {message}")

    def _tts_finished(self):
        self.btnSpeakTarget.setEnabled(bool(self._deck() and self._deck()["cards"]))
        if self.speechResult.text().startswith("Đang phát âm mẫu:"):
            self.speechResult.setText("Đã phát âm mẫu. Nhấn “Nói và chấm điểm” để thử đọc.")

    def _start_pronunciation(self):
        deck = self._deck()
        if not deck or not deck["cards"]:
            return
        if self._tts_worker and self._tts_worker.isRunning():
            self.speechResult.setText("Đợi phát âm mẫu xong rồi bắt đầu ghi âm nhé.")
            return
        if self._pronunciation_worker and self._pronunciation_worker.isRunning():
            return
        if self._model_worker and self._model_worker.isRunning():
            return

        self._pronunciation_target = deck["cards"][self.card_index]["front"]
        if not VOSK_MODEL_DIR.is_dir():
            answer = QMessageBox.question(
                self,
                "Cài nhận dạng giọng nói",
                "Lần đầu cần tải model tiếng Anh khoảng 40 MB. Tải và cài model ngay?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return
            self._set_study_controls_enabled(False)
            self.pronunciationScore.setValue(0)
            self.pronunciationScore.setFormat("Tải %p%")
            self.speechResult.setText("Đang tải model nhận dạng tiếng Anh...")
            self._model_worker = ModelDownloadWorker(self)
            self._model_worker.progress.connect(self._model_download_progress)
            self._model_worker.completed.connect(self._model_downloaded)
            self._model_worker.failed.connect(self._model_download_failed)
            self._model_worker.start()
            return

        self._begin_pronunciation_recording()

    def _model_download_progress(self, value):
        self.pronunciationScore.setValue(value)
        self.pronunciationScore.setFormat("Tải %p%")

    def _model_downloaded(self):
        self.speechResult.setText("Đã cài model. Chuẩn bị micro...")
        self._begin_pronunciation_recording()

    def _model_download_failed(self, message):
        self.pronunciationScore.setValue(0)
        self.pronunciationScore.setFormat("-- / 100")
        self.speechResult.setStyleSheet("color: #B24F4F; font-size: 9pt;")
        self.speechResult.setText(f"Không tải được model: {message}")
        self._set_study_controls_enabled(True)

    def _begin_pronunciation_recording(self):
        self.pronunciationScore.setValue(0)
        self.pronunciationScore.setFormat("Đang nghe")
        self.speechResult.setStyleSheet("color: #5269DD; font-size: 9pt;")
        self.speechResult.setText("Đang chuẩn bị micro...")
        self._set_study_controls_enabled(False)
        self._pronunciation_worker = PronunciationWorker(VOSK_MODEL_DIR, self)
        self._pronunciation_worker.status.connect(self.speechResult.setText)
        self._pronunciation_worker.result_ready.connect(self._score_pronunciation)
        self._pronunciation_worker.failed.connect(self._pronunciation_failed)
        self._pronunciation_worker.finished.connect(self._pronunciation_finished)
        self._pronunciation_worker.start()

    def _score_pronunciation(self, recognized_text):
        normalize = lambda value: " ".join(re.findall(r"[a-z0-9']+", value.casefold()))
        target = normalize(self._pronunciation_target)
        recognized = normalize(recognized_text)
        if not recognized or not target:
            self.pronunciationScore.setValue(0)
            self.pronunciationScore.setFormat("-- / 100")
            self.speechResult.setStyleSheet("color: #B27635; font-size: 9pt;")
            self.speechResult.setText("Chưa nhận ra lời đọc. Hãy thử nói to, chậm và rõ hơn.")
            return

        score = round(difflib.SequenceMatcher(None, target, recognized).ratio() * 100)
        self.pronunciationScore.setValue(score)
        self.pronunciationScore.setFormat(f"{score} / 100")
        if score >= 90:
            comment = "Rất tốt!"
            color = "#16865B"
        elif score >= 70:
            comment = "Khá tốt, thử đọc rõ hơn một lần nữa."
            color = "#A87524"
        else:
            comment = "Chưa khớp, hãy nghe mẫu rồi thử lại."
            color = "#B24F4F"
        self.speechResult.setStyleSheet(f"color: {color}; font-size: 9pt;")
        self.speechResult.setText(f"Nhận dạng: “{recognized_text}” · {comment}")

    def _pronunciation_failed(self, message):
        self.pronunciationScore.setValue(0)
        self.pronunciationScore.setFormat("-- / 100")
        self.speechResult.setStyleSheet("color: #B24F4F; font-size: 9pt;")
        self.speechResult.setText(f"Không dùng được micro hoặc bộ nhận dạng: {message}")

    def _pronunciation_finished(self):
        self.pronunciationScore.setFormat(
            f"{self.pronunciationScore.value()} / 100"
            if self.pronunciationScore.value() > 0
            else "-- / 100"
        )
        deck = self._deck()
        current_card = deck["cards"][self.card_index] if deck and deck["cards"] else None
        self._show_card(current_card)

    def _set_study_controls_enabled(self, enabled):
        deck = self._deck()
        has_card = bool(enabled and deck and deck["cards"])
        for button in (
            self.btnPrevious, self.btnNext, self.btnFlip, self.btnKnown,
            self.btnUnknown, self.btnSpeakTarget, self.btnRecordPronunciation,
        ):
            button.setEnabled(has_card)

    def _set_known(self, known):
        deck = self._deck()
        if not deck or not deck["cards"]:
            return
        deck["cards"][self.card_index]["known"] = known
        self._save_data()
        self._refresh_deck_view()
        self._move_card(1)
        message = "Đã ghi nhớ từ này." if known else "Đã chuyển từ này vào nhóm cần ôn lại."
        self.statusbar.showMessage(message, 2500)

    def _show_page(self, page_index):
        self.mainStack.setCurrentIndex(page_index)
        self.navStudy.setChecked(page_index == 0)
        self.navManage.setChecked(page_index == 1)
        self.navQuiz.setChecked(page_index == 2)
        if page_index == 1:
            self._refresh_card_table()

    def _open_quiz(self):
        self._show_page(2)
        self.quiz_number = 0
        self._new_quiz_question()

    def _new_quiz_question(self):
        deck = self._deck()
        cards = deck["cards"] if deck else []
        unique_answers = list(dict.fromkeys(card["back"] for card in cards))
        self.quiz_locked = True
        self.btnNextQuestion.setEnabled(False)
        for button in self.quiz_buttons:
            button.setEnabled(False)
            button.setStyleSheet("")
        if len(unique_answers) < 2:
            self.quiz_card = None
            self.quizPrompt.setText("Chưa đủ thẻ để kiểm tra")
            self.quizFeedback.setText("Thêm ít nhất 2 thẻ có nghĩa khác nhau vào bộ thẻ này.")
            self.quizProgress.setText("KIỂM TRA NGẪU NHIÊN")
            self.btnNextQuestion.setText("Câu tiếp theo  →")
            return

        self.quiz_number += 1
        self.quiz_card = random.choice(cards)
        correct_answer = self.quiz_card["back"]
        wrong_answers = [answer for answer in unique_answers if answer != correct_answer]
        choices = [correct_answer] + random.sample(wrong_answers, min(3, len(wrong_answers)))
        random.shuffle(choices)
        self.quizProgress.setText(f"CÂU HỎI NGẪU NHIÊN  ·  {self.quiz_number}")
        self.quizPrompt.setText(f"Từ “{self.quiz_card['front']}” có nghĩa là gì?")
        self.quizFeedback.setText("Chọn một đáp án bên dưới.")
        self.quizFeedback.setStyleSheet("color: #8996AA;")
        self.btnNextQuestion.setText("Câu tiếp theo  →")
        self.quiz_locked = False
        for index, button in enumerate(self.quiz_buttons):
            button.setStyleSheet(self.quiz_button_styles[index])
            if index < len(choices):
                button.setText(choices[index])
                button.setProperty("correctAnswer", choices[index] == correct_answer)
                button.setEnabled(True)
            else:
                button.setText("")
                button.setProperty("correctAnswer", False)

    def _answer_quiz(self, button):
        if self.quiz_locked or not self.quiz_card:
            return
        self.quiz_locked = True
        correct = bool(button.property("correctAnswer"))
        for option in self.quiz_buttons:
            option.setEnabled(False)
            if option.property("correctAnswer"):
                option.setStyleSheet("QPushButton { background: #E8F8F1; border: 1px solid #8BD5B6; color: #16764F; text-align: left; padding: 12px 15px; border-radius: 9px; }")
        if correct:
            self.quizFeedback.setText("Chính xác! Làm tốt lắm.")
            self.quizFeedback.setStyleSheet("color: #16865B; font-weight: 600;")
        else:
            self.quizFeedback.setText(f"Chưa đúng. Đáp án là: {self.quiz_card['back']}")
            self.quizFeedback.setStyleSheet("color: #C65959; font-weight: 600;")
            button.setStyleSheet("QPushButton { background: #FFF0F0; border: 1px solid #F0AAAA; color: #A34343; text-align: left; padding: 12px 15px; border-radius: 9px; }")
        self.btnNextQuestion.setEnabled(True)

    def _create_deck(self):
        dialog = DeckDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        name, description, cards = dialog.values()
        if not description:
            description = f"{len(cards)} từ vựng"
        deck = {"id": new_id(), "name": name, "description": description, "cards": cards}
        self.data["decks"].append(deck)
        self.current_deck_id = deck["id"]
        self.deckSearch.clear()
        self._save_data()
        self._populate_deck_list()
        self.statusbar.showMessage(f"Đã tạo chủ đề “{name}” với {len(cards)} từ vựng.", 3000)

    def _create_card(self):
        deck = self._deck()
        if not deck:
            return
        dialog = FlashcardDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        card = dialog.values()
        card.update({"id": new_id(), "known": False})
        deck["cards"].append(card)
        self.card_index = len(deck["cards"]) - 1
        self._reset_pronunciation_feedback()
        self._save_data()
        self._refresh_deck_view()
        self.statusbar.showMessage("Đã thêm thẻ mới.", 2500)

    def _refresh_card_table(self, *_):
        deck = self._deck()
        cards = deck["cards"] if deck else []
        query = self.cardSearch.text().strip().casefold()
        filtered = [
            card for card in cards
            if not query or query in card["front"].casefold()
            or query in card["back"].casefold()
            or query in card.get("example", "").casefold()
        ]
        self.cardsTable.setRowCount(len(filtered))
        for row, card in enumerate(filtered):
            values = [card["front"], card["back"], card.get("example", ""), "Đã nhớ" if card["known"] else "Cần ôn"]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, card["id"])
                if column == 3 and card["known"]:
                    item.setForeground(QtGui.QColor("#16865B"))
                self.cardsTable.setItem(row, column, item)
        self.btnEditCard.setEnabled(False)
        self.btnDeleteCard.setEnabled(False)

    def _selected_card(self):
        row = self.cardsTable.currentRow()
        if row < 0:
            return None
        first_cell = self.cardsTable.item(row, 0)
        if not first_cell:
            return None
        card_id = first_cell.data(Qt.UserRole)
        deck = self._deck()
        return next((card for card in deck["cards"] if card["id"] == card_id), None) if deck else None

    def _update_table_actions(self):
        selected = self._selected_card() is not None
        self.btnEditCard.setEnabled(selected)
        self.btnDeleteCard.setEnabled(selected)

    def _edit_selected_card(self):
        card = self._selected_card()
        if not card:
            return
        dialog = FlashcardDialog(self, card)
        if dialog.exec_() != QDialog.Accepted:
            return
        card.update(dialog.values())
        self._reset_pronunciation_feedback()
        self._save_data()
        self._refresh_deck_view()
        self.statusbar.showMessage("Đã cập nhật thẻ.", 2500)

    def _delete_selected_card(self):
        card = self._selected_card()
        deck = self._deck()
        if not card or not deck:
            return
        answer = QMessageBox.question(
            self,
            "Xóa thẻ",
            f"Bạn có chắc muốn xóa thẻ “{card['front']}” không?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        deck["cards"] = [item for item in deck["cards"] if item["id"] != card["id"]]
        self.card_index = min(self.card_index, max(0, len(deck["cards"]) - 1))
        self._reset_pronunciation_feedback()
        self._save_data()
        self._refresh_deck_view()
        self.statusbar.showMessage("Đã xóa thẻ.", 2500)

    def closeEvent(self, event):
        workers = (self._tts_worker, self._model_worker, self._pronunciation_worker)
        if any(worker and worker.isRunning() for worker in workers):
            QMessageBox.information(
                self,
                "Đang xử lý âm thanh",
                "Đợi phát âm, tải model hoặc chấm điểm xong rồi hãy đóng ứng dụng.",
            )
            event.ignore()
            return
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Lexi Flashcard")
    window = MainWindow()
    window.resize(1240, 820)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
