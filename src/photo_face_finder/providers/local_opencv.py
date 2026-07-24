from __future__ import annotations

from collections.abc import Sequence

from photo_face_finder.domain import (
    FaceSample,
    MatchStatus,
    ProviderDecision,
    ReferenceFace,
    UsageMetrics,
)
from photo_face_finder.imaging import FaceModels


class LocalOpenCVProvider:
    def __init__(
        self,
        models: FaceModels,
        references: Sequence[ReferenceFace],
        borderline_threshold: float,
        confident_threshold: float,
    ) -> None:
        if not references:
            raise ValueError("Wymagane jest przynajmniej jedno zdjęcie wzorcowe.")
        self._models = models
        self._references = tuple(references)
        self._borderline_threshold = borderline_threshold
        self._confident_threshold = confident_threshold
        self._usage = UsageMetrics()

    @property
    def usage(self) -> UsageMetrics:
        return self._usage

    def match(self, candidates: Sequence[FaceSample]) -> ProviderDecision:
        best_score = -1.0
        best_index = -1

        for candidate_index, candidate in enumerate(candidates):
            if candidate.feature is None:
                continue
            for reference in self._references:
                score = self._models.cosine_similarity(candidate.feature, reference.feature)
                if score > best_score:
                    best_score = score
                    best_index = candidate_index

        if best_index < 0:
            return ProviderDecision(
                MatchStatus.ERROR,
                message="Nie udało się porównać wykrytych twarzy.",
            )
        if best_score >= self._confident_threshold:
            return ProviderDecision(
                MatchStatus.CONFIDENT,
                score=best_score,
                matched_face_indices=(best_index,),
            )
        if best_score >= self._borderline_threshold:
            return ProviderDecision(
                MatchStatus.BORDERLINE,
                score=best_score,
                matched_face_indices=(best_index,),
                message="Wynik wymaga ręcznej weryfikacji.",
            )
        return ProviderDecision(MatchStatus.NO_MATCH, score=best_score)
