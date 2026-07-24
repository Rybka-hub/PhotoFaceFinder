from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from photo_face_finder.domain import FaceSample, ProviderDecision, UsageMetrics


class FaceMatchProvider(Protocol):
    @property
    def usage(self) -> UsageMetrics: ...

    def match(self, candidates: Sequence[FaceSample]) -> ProviderDecision: ...
