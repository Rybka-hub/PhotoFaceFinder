from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence

from photo_face_finder.domain import (
    FaceSample,
    MatchStatus,
    ProviderDecision,
    UsageMetrics,
)


class MockProvider:
    """Deterministyczny dostawca używany wyłącznie w testach."""

    def __init__(self, decisions: Iterable[ProviderDecision] | None = None) -> None:
        self._decisions = deque(decisions or ())
        self._usage = UsageMetrics()

    @property
    def usage(self) -> UsageMetrics:
        return self._usage

    def match(self, candidates: Sequence[FaceSample]) -> ProviderDecision:
        if self._decisions:
            return self._decisions.popleft()
        return ProviderDecision(
            MatchStatus.NO_MATCH if candidates else MatchStatus.ERROR,
            score=0.0 if candidates else None,
        )
