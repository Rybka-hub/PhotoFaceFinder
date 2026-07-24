from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray


class EngineKind(StrEnum):
    LOCAL = "local"
    OPENAI = "openai"


class WorkflowMode(StrEnum):
    REVIEW = "review"
    AUTOMATIC = "automatic"


class MatchStatus(StrEnum):
    CONFIDENT = "confident"
    BORDERLINE = "borderline"
    NO_MATCH = "no_match"
    ERROR = "error"
    API_ERROR = "api_error"
    CANCELLED = "cancelled"


class CopyStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    COPIED = "copied"
    SKIPPED_EXISTS = "skipped_exists"
    ERROR = "error"


@dataclass(slots=True)
class DetectedFace:
    """Twarz wykryta przez YuNet wraz z wierszem potrzebnym do wyrównania."""

    raw: NDArray[np.float32]
    x: int
    y: int
    width: int
    height: int
    confidence: float


@dataclass(slots=True)
class FaceSample:
    crop: NDArray[np.uint8] = field(repr=False)
    feature: NDArray[np.float32] | None = field(default=None, repr=False)


@dataclass(slots=True)
class ReferenceFace:
    source_path: Path
    face_index: int
    crop: NDArray[np.uint8] = field(repr=False)
    feature: NDArray[np.float32] = field(repr=False)


@dataclass(slots=True)
class ScanRequest:
    source: Path
    destination: Path
    engine: EngineKind
    workflow: WorkflowMode
    consent_confirmed: bool = False


@dataclass(slots=True)
class ProviderDecision:
    status: MatchStatus
    score: float | None = None
    matched_face_indices: tuple[int, ...] = ()
    message: str = ""


@dataclass(slots=True)
class PhotoResult:
    source_path: Path
    relative_path: Path
    status: MatchStatus
    face_count: int = 0
    score: float | None = None
    message: str = ""
    selected: bool = False
    copy_status: CopyStatus = CopyStatus.NOT_REQUESTED
    copied_to: Path | None = None


@dataclass(slots=True)
class UsageMetrics:
    api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_seconds: float = 0.0
    estimated_cost: float | None = None

    def add(self, other: UsageMetrics) -> None:
        self.api_calls += other.api_calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.elapsed_seconds += other.elapsed_seconds
        if self.estimated_cost is not None and other.estimated_cost is not None:
            self.estimated_cost += other.estimated_cost


@dataclass(slots=True)
class ScanSummary:
    total_files: int
    processed_files: int
    results: list[PhotoResult]
    usage: UsageMetrics = field(default_factory=UsageMetrics)
    cancelled: bool = False

    @property
    def confident_count(self) -> int:
        return sum(result.status == MatchStatus.CONFIDENT for result in self.results)

    @property
    def borderline_count(self) -> int:
        return sum(result.status == MatchStatus.BORDERLINE for result in self.results)

    @property
    def error_count(self) -> int:
        return sum(
            result.status in {MatchStatus.ERROR, MatchStatus.API_ERROR} for result in self.results
        )


def safe_usage_value(usage: Any, name: str) -> int:
    value = getattr(usage, name, 0) if usage is not None else 0
    return int(value or 0)
