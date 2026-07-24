from __future__ import annotations

from pathlib import Path

import pytest

import photo_face_finder.app as app_module
from photo_face_finder.app import MainWindow
from photo_face_finder.domain import EngineKind
from photo_face_finder.settings import Settings


class FakeFaceModels:
    def __init__(self, _settings: Settings) -> None:
        pass


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_name="Test",
        version="0",
        max_references=10,
        supported_extensions=frozenset({".jpg"}),
        borderline_threshold=0.363,
        confident_threshold=0.45,
        detection_score_threshold=0.9,
        detection_nms_threshold=0.3,
        detection_top_k=5000,
        openai_model="test",
        openai_timeout_seconds=1,
        openai_max_retries=0,
        openai_max_reference_faces=10,
        yunet_model_path=tmp_path / "yunet.onnx",
        sface_model_path=tmp_path / "sface.onnx",
    )


def test_engine_switch_shows_consent(
    qtbot: object, settings: Settings, monkeypatch: object
) -> None:
    monkeypatch.setattr(Settings, "validate_models", lambda _self: None)  # type: ignore[attr-defined]
    monkeypatch.setattr(app_module, "FaceModels", FakeFaceModels)  # type: ignore[attr-defined]
    window = MainWindow(settings)
    qtbot.addWidget(window)  # type: ignore[attr-defined]

    assert window.engine_combo.currentData() == EngineKind.LOCAL
    assert window.consent_checkbox.isHidden()

    window.engine_combo.setCurrentIndex(1)

    assert window.engine_combo.currentData() == EngineKind.OPENAI
    assert not window.consent_checkbox.isHidden()
