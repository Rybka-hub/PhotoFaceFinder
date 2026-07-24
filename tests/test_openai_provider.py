from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

import photo_face_finder.providers.openai_provider as provider_module
from photo_face_finder.domain import FaceSample, MatchStatus, ReferenceFace
from photo_face_finder.providers.openai_provider import OpenAIFaceMatchProvider
from photo_face_finder.settings import Settings


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text='{"verdict":"match","matching_candidate_indices":[2]}',
            usage=SimpleNamespace(input_tokens=100, output_tokens=5),
        )


class FakeOpenAI:
    last: FakeOpenAI | None = None

    def __init__(self, **_kwargs: object) -> None:
        self.responses = FakeResponses()
        FakeOpenAI.last = self


def _settings(root: Path) -> Settings:
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
        openai_model="test-model",
        openai_timeout_seconds=1,
        openai_max_retries=0,
        openai_max_reference_faces=10,
        yunet_model_path=root / "yunet.onnx",
        sface_model_path=root / "sface.onnx",
    )


def test_openai_provider_uses_crops_and_structured_output(
    tmp_path: Path, monkeypatch: object
) -> None:
    prompt = tmp_path / "src/photo_face_finder/prompts/face_match.txt"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("Porównaj twarze.", encoding="utf-8")
    monkeypatch.setattr(provider_module, "OpenAI", FakeOpenAI)  # type: ignore[attr-defined]
    monkeypatch.setattr(provider_module, "resource_path", lambda _path: prompt)  # type: ignore[attr-defined]

    crop = np.zeros((32, 32, 3), dtype=np.uint8)
    reference = ReferenceFace(Path("ref.jpg"), 0, crop, np.zeros(2, dtype=np.float32))
    provider = OpenAIFaceMatchProvider(_settings(tmp_path), [reference], "test-key")

    decision = provider.match([FaceSample(crop), FaceSample(crop)])

    assert decision.status == MatchStatus.CONFIDENT
    assert decision.matched_face_indices == (1,)
    assert provider.usage.api_calls == 1
    assert provider.usage.input_tokens == 100
    assert FakeOpenAI.last is not None
    call = FakeOpenAI.last.responses.calls[0]
    assert call["model"] == "test-model"
    assert "json_schema" in str(call["text"])
    assert "data:image/jpeg;base64," in str(call["input"])
