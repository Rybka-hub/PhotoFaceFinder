from __future__ import annotations

from pathlib import Path

import numpy as np

from photo_face_finder.domain import FaceSample, MatchStatus, ReferenceFace
from photo_face_finder.providers.local_opencv import LocalOpenCVProvider


class FakeModels:
    def cosine_similarity(self, first: np.ndarray, second: np.ndarray) -> float:
        return float(np.dot(first, second))


def _reference(feature: list[float]) -> ReferenceFace:
    return ReferenceFace(
        Path("reference.jpg"),
        0,
        np.zeros((8, 8, 3), dtype=np.uint8),
        np.asarray(feature, dtype=np.float32),
    )


def _candidate(feature: list[float]) -> FaceSample:
    return FaceSample(
        np.zeros((8, 8, 3), dtype=np.uint8),
        np.asarray(feature, dtype=np.float32),
    )


def test_any_of_five_faces_can_make_photo_confident() -> None:
    provider = LocalOpenCVProvider(
        FakeModels(),  # type: ignore[arg-type]
        [_reference([1.0, 0.0])],
        borderline_threshold=0.363,
        confident_threshold=0.45,
    )
    candidates = [_candidate([0.0, 1.0]) for _ in range(4)]
    candidates.append(_candidate([0.9, 0.1]))

    decision = provider.match(candidates)

    assert decision.status == MatchStatus.CONFIDENT
    assert decision.matched_face_indices == (4,)


def test_borderline_and_no_match_thresholds() -> None:
    provider = LocalOpenCVProvider(
        FakeModels(),  # type: ignore[arg-type]
        [_reference([1.0, 0.0])],
        borderline_threshold=0.363,
        confident_threshold=0.45,
    )

    assert provider.match([_candidate([0.40, 0.0])]).status == MatchStatus.BORDERLINE
    assert provider.match([_candidate([0.20, 0.0])]).status == MatchStatus.NO_MATCH
