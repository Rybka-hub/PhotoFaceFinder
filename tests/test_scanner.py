from __future__ import annotations

from pathlib import Path

import numpy as np

import photo_face_finder.scanner as scanner_module
from photo_face_finder.domain import (
    EngineKind,
    FaceSample,
    MatchStatus,
    ProviderDecision,
    ReferenceFace,
    ScanRequest,
    WorkflowMode,
)
from photo_face_finder.providers.mock import MockProvider
from photo_face_finder.scanner import ScanService
from photo_face_finder.settings import Settings


def _settings(tmp_path: Path) -> Settings:
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


class FakeModels:
    def __init__(self, _settings: Settings) -> None:
        pass

    def detect(self, _image: np.ndarray) -> list[int]:
        return [0, 1, 2, 3, 4]

    def sample(self, _image: np.ndarray, face: int) -> FaceSample:
        return FaceSample(
            np.zeros((4, 4, 3), dtype=np.uint8),
            np.asarray([float(face)], dtype=np.float32),
        )


def test_scanner_classifies_group_photo_when_provider_matches(
    tmp_path: Path, monkeypatch: object
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    photo = source / "grupa.jpg"
    photo.write_bytes(b"not-a-real-image")

    monkeypatch.setattr(scanner_module, "FaceModels", FakeModels)  # type: ignore[attr-defined]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        scanner_module,
        "load_oriented_bgr",
        lambda _path: np.zeros((20, 20, 3), dtype=np.uint8),
    )
    provider = MockProvider([ProviderDecision(MatchStatus.CONFIDENT)])
    service = ScanService(_settings(tmp_path), provider_factory=lambda _models: provider)
    reference = ReferenceFace(
        Path("ref.jpg"),
        0,
        np.zeros((4, 4, 3), dtype=np.uint8),
        np.zeros(1, dtype=np.float32),
    )

    summary = service.scan(
        ScanRequest(
            source,
            destination,
            EngineKind.LOCAL,
            WorkflowMode.REVIEW,
        ),
        [reference],
    )

    assert summary.total_files == 1
    assert summary.results[0].face_count == 5
    assert summary.results[0].status == MatchStatus.CONFIDENT
    assert summary.results[0].selected is True
