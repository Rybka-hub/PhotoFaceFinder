from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Any

import cv2
from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from photo_face_finder.copier import PathValidationError, validate_scan_paths
from photo_face_finder.domain import (
    CopyStatus,
    EngineKind,
    MatchStatus,
    PhotoResult,
    ReferenceFace,
    ScanRequest,
    ScanSummary,
    WorkflowMode,
)
from photo_face_finder.imaging import (
    FaceModels,
    ImageReadError,
    create_thumbnail_bytes,
    load_oriented_bgr,
)
from photo_face_finder.scanner import ScanService, copy_selected_results
from photo_face_finder.settings import Settings

LOGGER = logging.getLogger("photo_face_finder")


STATUS_LABELS = {
    MatchStatus.CONFIDENT: "Pewne",
    MatchStatus.BORDERLINE: "Graniczne",
    MatchStatus.NO_MATCH: "Brak dopasowania",
    MatchStatus.ERROR: "Błąd",
    MatchStatus.API_ERROR: "Błąd API",
    MatchStatus.CANCELLED: "Anulowano",
}

STATUS_COLORS = {
    MatchStatus.CONFIDENT: QColor("#1f9d68"),
    MatchStatus.BORDERLINE: QColor("#d99119"),
    MatchStatus.NO_MATCH: QColor("#7b879f"),
    MatchStatus.ERROR: QColor("#d94a5a"),
    MatchStatus.API_ERROR: QColor("#d94a5a"),
    MatchStatus.CANCELLED: QColor("#7b879f"),
}


def _pixmap_from_bgr(image: Any) -> QPixmap:
    height, width = image.shape[:2]
    qimage = QImage(
        image.data,
        width,
        height,
        int(image.strides[0]),
        QImage.Format.Format_BGR888,
    ).copy()
    return QPixmap.fromImage(qimage)


def _message(parent: QWidget, title: str, text: str, critical: bool = False) -> None:
    if critical:
        QMessageBox.critical(parent, title, text)
    else:
        QMessageBox.information(parent, title, text)


class FaceSelectionDialog(QDialog):
    def __init__(self, image: Any, faces: list[Any], models: FaceModels, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Wskaż twarz wzorcową")
        self.setMinimumSize(820, 620)
        self.selected_index: int | None = None

        layout = QVBoxLayout(self)
        title = QLabel(
            "Na zdjęciu wykryto kilka twarzy. Kliknij miniaturę osoby, której zdjęć chcesz szukać."
        )
        title.setWordWrap(True)
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        annotated = image.copy()
        for index, face in enumerate(faces, start=1):
            cv2.rectangle(
                annotated,
                (face.x, face.y),
                (face.x + face.width, face.y + face.height),
                (48, 210, 125),
                max(2, annotated.shape[1] // 500),
            )
            cv2.putText(
                annotated,
                str(index),
                (face.x, max(24, face.y - 8)),
                cv2.FONT_HERSHEY_DUPLEX,
                0.8,
                (48, 210, 125),
                2,
            )
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setPixmap(
            _pixmap_from_bgr(annotated).scaled(
                760,
                390,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        layout.addWidget(preview, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(190)
        container = QWidget()
        grid = QGridLayout(container)
        for index, face in enumerate(faces):
            crop = models.crop(image, face)
            button = QPushButton(f"Twarz {index + 1}")
            button.setIcon(QIcon(_pixmap_from_bgr(crop)))
            button.setIconSize(QSize(120, 120))
            button.setMinimumSize(145, 150)
            button.clicked.connect(lambda _checked=False, value=index: self._select(value))
            grid.addWidget(button, index // 5, index % 5)
        scroll.setWidget(container)
        layout.addWidget(scroll)

        cancel = QPushButton("Anuluj")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel, alignment=Qt.AlignmentFlag.AlignRight)

    def _select(self, index: int) -> None:
        self.selected_index = index
        self.accept()


class ScanWorker(QObject):
    progress = Signal(int, int, str)
    result_ready = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        settings: Settings,
        request: ScanRequest,
        references: list[ReferenceFace],
        only_paths: list[Path] | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._request = request
        self._references = references
        self._only_paths = only_paths
        self._cancel = threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            service = ScanService(self._settings)
            summary = service.scan(
                self._request,
                self._references,
                progress=lambda done, total, path: self.progress.emit(done, total, path.name),
                on_result=self.result_ready.emit,
                cancel_event=self._cancel,
                only_paths=self._only_paths,
            )
            self.finished.emit(summary)
        except Exception as exc:
            LOGGER.exception("Skan nie został uruchomiony")
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    @Slot()
    def cancel(self) -> None:
        self._cancel.set()


class CopyWorker(QObject):
    progress = Signal(int, int, object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, results: list[PhotoResult], destination: Path) -> None:
        super().__init__()
        self._results = results
        self._destination = destination
        self._cancel = threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            updated = copy_selected_results(
                self._results,
                self._destination,
                cancel_event=self._cancel,
                progress=lambda done, total, result: self.progress.emit(done, total, result),
            )
            self.finished.emit(updated)
        except Exception as exc:
            LOGGER.exception("Kopiowanie nie powiodło się")
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    @Slot()
    def cancel(self) -> None:
        self._cancel.set()


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.references: list[ReferenceFace] = []
        self.results: list[PhotoResult] = []
        self._row_by_path: dict[Path, int] = {}
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._copy_thread: QThread | None = None
        self._copy_worker: CopyWorker | None = None
        self._retrying = False
        self._close_when_done = False

        self.settings.validate_models()
        self.reference_models = FaceModels(settings)
        self.setWindowTitle(f"{settings.app_name} {settings.version}")
        self.resize(1240, 820)
        self.setMinimumSize(980, 680)
        self._build_ui()
        self._apply_style()
        self._update_engine_state()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(22, 18, 22, 18)
        root_layout.setSpacing(14)

        heading_row = QHBoxLayout()
        heading_box = QVBoxLayout()
        heading = QLabel("Photo Face Finder")
        heading.setObjectName("heading")
        subtitle = QLabel("Znajdź zdjęcia zawierające wskazaną osobę — lokalnie lub przez OpenAI.")
        subtitle.setObjectName("subtitle")
        heading_box.addWidget(heading)
        heading_box.addWidget(subtitle)
        heading_row.addLayout(heading_box, 1)
        self.api_status = QLabel()
        self.api_status.setObjectName("apiStatus")
        heading_row.addWidget(self.api_status, alignment=Qt.AlignmentFlag.AlignTop)
        root_layout.addLayout(heading_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_setup_panel())
        splitter.addWidget(self._build_results_panel())
        splitter.setSizes([420, 800])
        root_layout.addWidget(splitter, 1)

        footer = QHBoxLayout()
        self.current_file_label = QLabel("Gotowe.")
        self.current_file_label.setObjectName("currentFile")
        footer.addWidget(self.current_file_label, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumWidth(300)
        footer.addWidget(self.progress_bar)
        root_layout.addLayout(footer)

        self.setCentralWidget(root)

    def _build_setup_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setSpacing(12)

        references_group = QGroupBox("1. Zdjęcia wzorcowe")
        references_layout = QVBoxLayout(references_group)
        reference_help = QLabel(
            "Dodaj 1–10 zdjęć tej samej osoby. Przy zdjęciu grupowym wskaż właściwą twarz."
        )
        reference_help.setWordWrap(True)
        reference_help.setObjectName("help")
        references_layout.addWidget(reference_help)
        self.reference_list = QListWidget()
        self.reference_list.setIconSize(QSize(64, 64))
        self.reference_list.setMaximumHeight(180)
        references_layout.addWidget(self.reference_list)
        reference_buttons = QHBoxLayout()
        add_reference = QPushButton("Dodaj zdjęcia")
        add_reference.clicked.connect(self._choose_references)
        remove_reference = QPushButton("Usuń zaznaczone")
        remove_reference.setObjectName("secondary")
        remove_reference.clicked.connect(self._remove_reference)
        reference_buttons.addWidget(add_reference)
        reference_buttons.addWidget(remove_reference)
        references_layout.addLayout(reference_buttons)
        layout.addWidget(references_group)

        folders_group = QGroupBox("2. Foldery")
        folders_layout = QGridLayout(folders_group)
        self.source_edit = self._path_row(folders_layout, 0, "Źródło", self._choose_source)
        self.destination_edit = self._path_row(folders_layout, 1, "Cel", self._choose_destination)
        layout.addWidget(folders_group)

        options_group = QGroupBox("3. Sposób działania")
        options_layout = QGridLayout(options_group)
        options_layout.addWidget(QLabel("Silnik:"), 0, 0)
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Lokalny OpenCV (zalecany)", EngineKind.LOCAL)
        self.engine_combo.addItem("OpenAI (eksperymentalny)", EngineKind.OPENAI)
        self.engine_combo.currentIndexChanged.connect(self._update_engine_state)
        options_layout.addWidget(self.engine_combo, 0, 1)
        options_layout.addWidget(QLabel("Kopiowanie:"), 1, 0)
        self.workflow_combo = QComboBox()
        self.workflow_combo.addItem("Najpierw pokaż wyniki", WorkflowMode.REVIEW)
        self.workflow_combo.addItem("Automatycznie pewne wyniki", WorkflowMode.AUTOMATIC)
        options_layout.addWidget(self.workflow_combo, 1, 1)
        self.consent_checkbox = QCheckBox(
            "Potwierdzam zgodę osoby wzorcowej na przesłanie kadrów twarzy do OpenAI."
        )
        options_layout.addWidget(self.consent_checkbox, 2, 0, 1, 2)
        layout.addWidget(options_group)

        privacy = QLabel(
            "W trybie lokalnym obrazy nie opuszczają komputera. "
            "Wzorce i deskryptory nie są zapisywane po zamknięciu programu."
        )
        privacy.setWordWrap(True)
        privacy.setObjectName("privacy")
        layout.addWidget(privacy)
        layout.addStretch(1)

        action_row = QHBoxLayout()
        self.start_button = QPushButton("Rozpocznij skan")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self._start_scan)
        self.cancel_button = QPushButton("Anuluj")
        self.cancel_button.setObjectName("danger")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_active)
        action_row.addWidget(self.start_button, 1)
        action_row.addWidget(self.cancel_button)
        layout.addLayout(action_row)
        return panel

    def _build_results_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)

        header = QHBoxLayout()
        title = QLabel("Wyniki")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(QLabel("Filtr:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("Wszystkie", "all")
        self.filter_combo.addItem("Pewne", MatchStatus.CONFIDENT)
        self.filter_combo.addItem("Graniczne", MatchStatus.BORDERLINE)
        self.filter_combo.addItem("Bez dopasowania", MatchStatus.NO_MATCH)
        self.filter_combo.addItem("Błędy", "errors")
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)
        header.addWidget(self.filter_combo)
        layout.addLayout(header)

        self.results_table = QTableWidget(0, 7)
        self.results_table.setHorizontalHeaderLabels(
            ["Kopiuj", "Podgląd", "Plik", "Wynik", "Pewność", "Twarze", "Informacja"]
        )
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setIconSize(QSize(84, 64))
        header_view = self.results_table.horizontalHeader()
        header_view.setStretchLastSection(True)
        header_view.resizeSection(0, 58)
        header_view.resizeSection(1, 96)
        header_view.resizeSection(2, 210)
        header_view.resizeSection(3, 120)
        header_view.resizeSection(4, 72)
        header_view.resizeSection(5, 58)
        layout.addWidget(self.results_table, 1)

        self.summary_label = QLabel("Brak wyników.")
        self.summary_label.setObjectName("summary")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        buttons = QHBoxLayout()
        self.retry_button = QPushButton("Ponów błędy API")
        self.retry_button.setObjectName("secondary")
        self.retry_button.clicked.connect(self._retry_api_errors)
        self.retry_button.setEnabled(False)
        self.copy_button = QPushButton("Kopiuj zaznaczone")
        self.copy_button.setObjectName("primary")
        self.copy_button.clicked.connect(self._copy_selected)
        self.copy_button.setEnabled(False)
        buttons.addWidget(self.retry_button)
        buttons.addStretch(1)
        buttons.addWidget(self.copy_button)
        layout.addLayout(buttons)
        return panel

    def _path_row(
        self,
        layout: QGridLayout,
        row: int,
        label: str,
        callback: Any,
    ) -> QLineEdit:
        layout.addWidget(QLabel(f"{label}:"), row, 0)
        edit = QLineEdit()
        edit.setReadOnly(True)
        edit.setPlaceholderText("Nie wybrano folderu")
        layout.addWidget(edit, row, 1)
        button = QPushButton("Wybierz…")
        button.setObjectName("secondary")
        button.clicked.connect(callback)
        layout.addWidget(button, row, 2)
        return edit

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #0f1420; color: #e7ecf5; font-size: 13px; }
            #heading { font-size: 27px; font-weight: 700; color: #ffffff; }
            #subtitle, #help, #currentFile { color: #9aa8bf; }
            #sectionTitle, #dialogTitle { font-size: 18px; font-weight: 650; }
            #panel { background: #151c2b; border: 1px solid #263148; border-radius: 12px; }
            QGroupBox {
                border: 1px solid #2b3851; border-radius: 9px; margin-top: 10px;
                padding-top: 12px; font-weight: 650;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QLineEdit, QComboBox, QListWidget, QTableWidget, QScrollArea {
                background: #0d1320; border: 1px solid #34425d; border-radius: 6px;
                selection-background-color: #376df0;
            }
            QLineEdit, QComboBox { min-height: 32px; padding: 2px 8px; }
            QPushButton {
                background: #27334a; border: 1px solid #3a4966; border-radius: 7px;
                padding: 8px 13px; font-weight: 600;
            }
            QPushButton:hover { background: #32415c; }
            QPushButton:disabled { color: #68748a; background: #1d2534; }
            QPushButton#primary { background: #376df0; border-color: #4b7cff; }
            QPushButton#primary:hover { background: #487cf5; }
            QPushButton#danger { background: #6f2935; border-color: #9b3b4b; }
            QPushButton#secondary { background: #202a3d; }
            #privacy {
                background: #101a2a; color: #a9bddf; border: 1px solid #263d60;
                border-radius: 8px; padding: 10px;
            }
            #apiStatus, #summary {
                background: #101827; border: 1px solid #2c3951; border-radius: 7px;
                padding: 7px 10px;
            }
            QHeaderView::section {
                background: #202a3d; color: #d8e0ed; border: 0; padding: 8px;
            }
            QTableWidget { gridline-color: #263148; }
            QProgressBar {
                background: #1b2435; border: 1px solid #34425d; border-radius: 6px;
                text-align: center; min-height: 20px;
            }
            QProgressBar::chunk { background: #376df0; border-radius: 5px; }
            """
        )

    @Slot()
    def _update_engine_state(self) -> None:
        engine = self.engine_combo.currentData() if hasattr(self, "engine_combo") else None
        is_openai = engine == EngineKind.OPENAI
        if hasattr(self, "consent_checkbox"):
            self.consent_checkbox.setVisible(is_openai)
        key_available = bool(self.settings.openai_api_key)
        if is_openai:
            self.api_status.setText(
                "OpenAI: klucz wykryty" if key_available else "OpenAI: brak OPENAI_API_KEY"
            )
            self.api_status.setStyleSheet("color: #64d69b;" if key_available else "color: #ff8b96;")
        else:
            self.api_status.setText("Tryb lokalny • prywatny")
            self.api_status.setStyleSheet("color: #64d69b;")

    @Slot()
    def _choose_references(self) -> None:
        remaining = self.settings.max_references - len(self.references)
        if remaining <= 0:
            _message(
                self,
                "Limit zdjęć",
                f"Można dodać maksymalnie {self.settings.max_references} wzorców.",
            )
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Wybierz zdjęcia wzorcowe",
            "",
            "Zdjęcia (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)",
        )
        existing = {reference.source_path.resolve() for reference in self.references}
        for raw_path in paths[:remaining]:
            path = Path(raw_path)
            if path.resolve() in existing:
                continue
            try:
                image = load_oriented_bgr(path)
                faces = self.reference_models.detect(image)
                if not faces:
                    _message(
                        self,
                        "Brak twarzy",
                        f"Nie wykryto twarzy w pliku:\n{path.name}",
                    )
                    continue
                face_index = 0
                if len(faces) > 1:
                    dialog = FaceSelectionDialog(image, faces, self.reference_models, self)
                    if dialog.exec() != QDialog.DialogCode.Accepted:
                        continue
                    if dialog.selected_index is None:
                        continue
                    face_index = dialog.selected_index
                crop = self.reference_models.crop(image, faces[face_index])
                feature = self.reference_models.feature(crop)
                reference = ReferenceFace(path, face_index, crop, feature)
                self.references.append(reference)
                item = QListWidgetItem(QIcon(_pixmap_from_bgr(crop)), path.name)
                item.setToolTip(str(path))
                self.reference_list.addItem(item)
                existing.add(path.resolve())
            except (ImageReadError, OSError, ValueError) as exc:
                _message(self, "Błąd zdjęcia wzorcowego", f"{path.name}\n\n{exc}", True)

    @Slot()
    def _remove_reference(self) -> None:
        rows = sorted(
            {self.reference_list.row(item) for item in self.reference_list.selectedItems()},
            reverse=True,
        )
        for row in rows:
            self.reference_list.takeItem(row)
            self.references.pop(row)

    @Slot()
    def _choose_source(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Wybierz folder ze zdjęciami")
        if selected:
            self.source_edit.setText(selected)

    @Slot()
    def _choose_destination(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Wybierz folder docelowy")
        if selected:
            self.destination_edit.setText(selected)

    def _request_from_ui(self) -> ScanRequest:
        if not self.references:
            raise ValueError("Dodaj przynajmniej jedno zdjęcie wzorcowe.")
        if not self.source_edit.text() or not self.destination_edit.text():
            raise ValueError("Wybierz folder źródłowy i docelowy.")
        request = ScanRequest(
            source=Path(self.source_edit.text()),
            destination=Path(self.destination_edit.text()),
            engine=self.engine_combo.currentData(),
            workflow=self.workflow_combo.currentData(),
            consent_confirmed=self.consent_checkbox.isChecked(),
        )
        validate_scan_paths(request.source, request.destination)
        if request.engine == EngineKind.OPENAI:
            if not request.consent_confirmed:
                raise ValueError("Potwierdź zgodę osoby wzorcowej na użycie OpenAI.")
            if not self.settings.openai_api_key:
                raise ValueError(
                    "Brak OPENAI_API_KEY. Ustaw zmienną środowiskową i uruchom aplikację ponownie."
                )
        return request

    @Slot()
    def _start_scan(self) -> None:
        try:
            request = self._request_from_ui()
        except (ValueError, PathValidationError) as exc:
            _message(self, "Nie można rozpocząć", str(exc), True)
            return
        self.results.clear()
        self._row_by_path.clear()
        self.results_table.setRowCount(0)
        self._retrying = False
        self._launch_scan(request, None)

    def _launch_scan(self, request: ScanRequest, only_paths: list[Path] | None) -> None:
        self._set_busy(True)
        self.progress_bar.setValue(0)
        self.current_file_label.setText("Przygotowanie modeli…")
        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker(
            self.settings,
            request,
            list(self.references),
            only_paths,
        )
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.result_ready.connect(self._on_result)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.failed.connect(self._on_operation_failed)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.failed.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.start()

    @Slot(int, int, str)
    def _on_scan_progress(self, done: int, total: int, filename: str) -> None:
        value = 0 if total == 0 else int(done * 100 / total)
        self.progress_bar.setValue(value)
        self.current_file_label.setText(
            f"Skanowanie {done}/{total}: {filename}" if total else "Brak zdjęć."
        )

    @Slot(object)
    def _on_result(self, result: PhotoResult) -> None:
        existing_row = self._row_by_path.get(result.source_path)
        if existing_row is not None:
            existing_index = next(
                (
                    index
                    for index, current in enumerate(self.results)
                    if current.source_path == result.source_path
                ),
                None,
            )
            if existing_index is not None:
                self.results[existing_index] = result
            self._populate_result_row(existing_row, result)
        else:
            self.results.append(result)
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)
            self._row_by_path[result.source_path] = row
            self._populate_result_row(row, result)
        self._apply_filter()

    def _populate_result_row(self, row: int, result: PhotoResult) -> None:
        check = QTableWidgetItem()
        check.setData(Qt.ItemDataRole.UserRole, str(result.source_path))
        if result.status in {MatchStatus.CONFIDENT, MatchStatus.BORDERLINE}:
            check.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            check.setCheckState(
                Qt.CheckState.Checked if result.selected else Qt.CheckState.Unchecked
            )
        else:
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.results_table.setItem(row, 0, check)

        preview = QTableWidgetItem()
        thumbnail = create_thumbnail_bytes(result.source_path)
        if thumbnail:
            preview.setIcon(QIcon(QPixmap.fromImage(QImage.fromData(thumbnail))))
        self.results_table.setItem(row, 1, preview)

        filename = QTableWidgetItem(str(result.relative_path))
        filename.setToolTip(str(result.source_path))
        self.results_table.setItem(row, 2, filename)

        status = QTableWidgetItem(STATUS_LABELS[result.status])
        status.setForeground(STATUS_COLORS[result.status])
        status.setFont(QFont("", -1, QFont.Weight.DemiBold))
        self.results_table.setItem(row, 3, status)
        score = "—" if result.score is None else f"{result.score:.3f}"
        self.results_table.setItem(row, 4, QTableWidgetItem(score))
        self.results_table.setItem(row, 5, QTableWidgetItem(str(result.face_count)))

        copy_text = {
            CopyStatus.COPIED: "Skopiowano.",
            CopyStatus.SKIPPED_EXISTS: "Plik już istniał.",
            CopyStatus.ERROR: "Błąd kopiowania.",
            CopyStatus.NOT_REQUESTED: "",
        }[result.copy_status]
        info = " ".join(value for value in (result.message, copy_text) if value)
        info_item = QTableWidgetItem(info)
        info_item.setToolTip(info)
        self.results_table.setItem(row, 6, info_item)
        self.results_table.setRowHeight(row, 72)

    @Slot(object)
    def _on_scan_finished(self, summary: ScanSummary) -> None:
        self._set_busy(False)
        self.progress_bar.setValue(100 if not summary.cancelled else self.progress_bar.value())
        self.current_file_label.setText(
            "Skan anulowany." if summary.cancelled else "Skan zakończony."
        )
        api_errors = sum(result.status == MatchStatus.API_ERROR for result in self.results)
        self.retry_button.setEnabled(
            api_errors > 0 and self.engine_combo.currentData() == EngineKind.OPENAI
        )
        self.copy_button.setEnabled(
            any(
                result.status in {MatchStatus.CONFIDENT, MatchStatus.BORDERLINE}
                for result in self.results
            )
        )
        copied = sum(result.copy_status == CopyStatus.COPIED for result in self.results)
        skipped = sum(result.copy_status == CopyStatus.SKIPPED_EXISTS for result in self.results)
        usage_text = ""
        if summary.usage.api_calls:
            usage_text = (
                f" • API: {summary.usage.api_calls} wywołań, "
                f"{summary.usage.input_tokens + summary.usage.output_tokens} tokenów, "
                f"{summary.usage.elapsed_seconds:.1f} s"
            )
        self.summary_label.setText(
            f"Pliki: {len(self.results)} • Pewne: "
            f"{sum(r.status == MatchStatus.CONFIDENT for r in self.results)} • "
            f"Graniczne: {sum(r.status == MatchStatus.BORDERLINE for r in self.results)} • "
            f"Błędy: "
            f"{sum(r.status in {MatchStatus.ERROR, MatchStatus.API_ERROR} for r in self.results)}"
            f" • Skopiowane: {copied} • Pominięte: {skipped}{usage_text}"
        )
        self._scan_worker = None
        self._scan_thread = None
        self._retrying = False
        if self._close_when_done:
            self.close()

    @Slot(str)
    def _on_operation_failed(self, message: str) -> None:
        self._set_busy(False)
        self.current_file_label.setText("Operacja nie powiodła się.")
        self._scan_worker = None
        self._scan_thread = None
        self._copy_worker = None
        self._copy_thread = None
        if self._close_when_done:
            self.close()
        _message(self, "Błąd operacji", message, True)

    def _set_busy(self, busy: bool) -> None:
        self.start_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.copy_button.setEnabled(
            not busy
            and any(
                result.status in {MatchStatus.CONFIDENT, MatchStatus.BORDERLINE}
                for result in self.results
            )
        )
        self.retry_button.setEnabled(
            not busy and any(result.status == MatchStatus.API_ERROR for result in self.results)
        )

    @Slot()
    def _cancel_active(self) -> None:
        if self._scan_worker is not None:
            self._scan_worker.cancel()
        if self._copy_worker is not None:
            self._copy_worker.cancel()
        self.current_file_label.setText("Anulowanie po bieżącym pliku…")

    @Slot()
    def _copy_selected(self) -> None:
        for result in self.results:
            row = self._row_by_path.get(result.source_path)
            if row is None:
                continue
            item = self.results_table.item(row, 0)
            result.selected = bool(item and item.checkState() == Qt.CheckState.Checked)
        selected = [
            result
            for result in self.results
            if result.selected
            and result.status in {MatchStatus.CONFIDENT, MatchStatus.BORDERLINE}
            and result.copy_status != CopyStatus.COPIED
        ]
        if not selected:
            _message(self, "Brak wyboru", "Zaznacz przynajmniej jedno zdjęcie do skopiowania.")
            return

        self._set_busy(True)
        self._copy_thread = QThread(self)
        self._copy_worker = CopyWorker(selected, Path(self.destination_edit.text()))
        self._copy_worker.moveToThread(self._copy_thread)
        self._copy_thread.started.connect(self._copy_worker.run)
        self._copy_worker.progress.connect(self._on_copy_progress)
        self._copy_worker.finished.connect(self._on_copy_finished)
        self._copy_worker.failed.connect(self._on_operation_failed)
        self._copy_worker.finished.connect(self._copy_thread.quit)
        self._copy_worker.failed.connect(self._copy_thread.quit)
        self._copy_thread.finished.connect(self._copy_worker.deleteLater)
        self._copy_thread.finished.connect(self._copy_thread.deleteLater)
        self._copy_thread.start()

    @Slot(int, int, object)
    def _on_copy_progress(self, done: int, total: int, result: PhotoResult) -> None:
        self.progress_bar.setValue(0 if total == 0 else int(done * 100 / total))
        self.current_file_label.setText(f"Kopiowanie {done}/{total}: {result.relative_path}")
        row = self._row_by_path.get(result.source_path)
        if row is not None:
            self._populate_result_row(row, result)

    @Slot(object)
    def _on_copy_finished(self, _updated: object) -> None:
        self._set_busy(False)
        self.progress_bar.setValue(100)
        copied = sum(result.copy_status == CopyStatus.COPIED for result in self.results)
        skipped = sum(result.copy_status == CopyStatus.SKIPPED_EXISTS for result in self.results)
        self.current_file_label.setText(
            f"Kopiowanie zakończone. Skopiowano: {copied}, pominięto: {skipped}."
        )
        self._copy_worker = None
        self._copy_thread = None

    @Slot()
    def _retry_api_errors(self) -> None:
        paths = [
            result.source_path for result in self.results if result.status == MatchStatus.API_ERROR
        ]
        if not paths:
            return
        try:
            request = self._request_from_ui()
        except (ValueError, PathValidationError) as exc:
            _message(self, "Nie można ponowić", str(exc), True)
            return
        self._retrying = True
        self._launch_scan(request, paths)

    @Slot()
    def _apply_filter(self) -> None:
        selected = self.filter_combo.currentData()
        for path, row in self._row_by_path.items():
            result = next(
                (current for current in self.results if current.source_path == path), None
            )
            visible = True
            if result is not None and selected != "all":
                if selected == "errors":
                    visible = result.status in {MatchStatus.ERROR, MatchStatus.API_ERROR}
                else:
                    visible = result.status == selected
            self.results_table.setRowHidden(row, not visible)

    def closeEvent(self, event: Any) -> None:
        if self._scan_worker is not None or self._copy_worker is not None:
            answer = QMessageBox.question(
                self,
                "Operacja trwa",
                "Skanowanie lub kopiowanie nadal trwa. Anulować i zamknąć program?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._close_when_done = True
            self._cancel_active()
            event.ignore()
            return
        event.accept()


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def run() -> int:
    _configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Photo Face Finder")
    app.setOrganizationName("Photo Face Finder")
    try:
        settings = Settings.load()
        window = MainWindow(settings)
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Nie można uruchomić Photo Face Finder",
            f"{type(exc).__name__}: {exc}",
        )
        return 1
    window.show()
    return app.exec()
