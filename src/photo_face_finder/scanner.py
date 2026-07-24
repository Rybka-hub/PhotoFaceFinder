from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from photo_face_finder.copier import (
    copy_preserving_structure,
    enumerate_images,
    validate_scan_paths,
)
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
from photo_face_finder.imaging import FaceModels, ImageReadError, load_oriented_bgr
from photo_face_finder.providers.base import FaceMatchProvider
from photo_face_finder.providers.local_opencv import LocalOpenCVProvider
from photo_face_finder.providers.openai_provider import OpenAIFaceMatchProvider
from photo_face_finder.settings import Settings

ProgressCallback = Callable[[int, int, Path], None]
ResultCallback = Callable[[PhotoResult], None]
ProviderFactory = Callable[[FaceModels], FaceMatchProvider]


class ScanService:
    def __init__(
        self,
        settings: Settings,
        provider_factory: ProviderFactory | None = None,
    ) -> None:
        self._settings = settings
        self._provider_factory = provider_factory

    def _create_provider(
        self,
        models: FaceModels,
        request: ScanRequest,
        references: Sequence[ReferenceFace],
    ) -> FaceMatchProvider:
        if self._provider_factory is not None:
            return self._provider_factory(models)
        if request.engine == EngineKind.LOCAL:
            return LocalOpenCVProvider(
                models,
                references,
                self._settings.borderline_threshold,
                self._settings.confident_threshold,
            )
        if not request.consent_confirmed:
            raise ValueError("Tryb OpenAI wymaga potwierdzenia zgody osoby wzorcowej.")
        api_key = self._settings.openai_api_key
        if not api_key:
            raise ValueError("Brak zmiennej środowiskowej OPENAI_API_KEY.")
        return OpenAIFaceMatchProvider(self._settings, references, api_key)

    def _process_file(
        self,
        path: Path,
        source_root: Path,
        destination_root: Path,
        models: FaceModels,
        provider: FaceMatchProvider,
        request: ScanRequest,
    ) -> PhotoResult:
        relative_path = path.relative_to(source_root)
        try:
            image = load_oriented_bgr(path)
            detected = models.detect(image)
            if not detected:
                return PhotoResult(
                    path,
                    relative_path,
                    MatchStatus.NO_MATCH,
                    face_count=0,
                    message="Nie wykryto twarzy.",
                )
            samples = [models.sample(image, face) for face in detected]
            decision = provider.match(samples)
            result = PhotoResult(
                path,
                relative_path,
                decision.status,
                face_count=len(detected),
                score=decision.score,
                message=decision.message,
                selected=decision.status == MatchStatus.CONFIDENT,
            )

            if (
                request.workflow == WorkflowMode.AUTOMATIC
                and result.status == MatchStatus.CONFIDENT
            ):
                outcome = copy_preserving_structure(path, relative_path, destination_root)
                result.copy_status = outcome.status
                result.copied_to = outcome.destination
                if outcome.message:
                    result.message = " ".join(
                        value for value in (result.message, outcome.message) if value
                    )
            return result
        except (ImageReadError, OSError, ValueError) as exc:
            return PhotoResult(
                path,
                relative_path,
                MatchStatus.ERROR,
                message=str(exc),
            )
        except Exception as exc:
            return PhotoResult(
                path,
                relative_path,
                MatchStatus.ERROR,
                message=f"{type(exc).__name__}: {exc}",
            )

    def scan(
        self,
        request: ScanRequest,
        references: Sequence[ReferenceFace],
        progress: ProgressCallback | None = None,
        on_result: ResultCallback | None = None,
        cancel_event: threading.Event | None = None,
        only_paths: Sequence[Path] | None = None,
    ) -> ScanSummary:
        if not 1 <= len(references) <= self._settings.max_references:
            raise ValueError(
                f"Liczba wzorców musi mieścić się w zakresie 1–{self._settings.max_references}."
            )
        source_root, destination_root = validate_scan_paths(request.source, request.destination)
        models = FaceModels(self._settings)
        provider = self._create_provider(models, request, references)
        if only_paths is None:
            files = enumerate_images(source_root, self._settings.supported_extensions)
        else:
            files = []
            for path in only_paths:
                resolved = path.resolve()
                if (
                    resolved.is_file()
                    and resolved.is_relative_to(source_root)
                    and resolved.suffix.casefold() in self._settings.supported_extensions
                ):
                    files.append(resolved)
        results: list[PhotoResult] = []
        cancellation = cancel_event or threading.Event()

        for index, path in enumerate(files, start=1):
            if cancellation.is_set():
                return ScanSummary(
                    len(files),
                    len(results),
                    results,
                    provider.usage,
                    cancelled=True,
                )
            if progress:
                progress(index - 1, len(files), path)
            result = self._process_file(
                path,
                source_root,
                destination_root,
                models,
                provider,
                request,
            )
            results.append(result)
            if on_result:
                on_result(result)
            if progress:
                progress(index, len(files), path)

        return ScanSummary(len(files), len(results), results, provider.usage)


def copy_selected_results(
    results: Sequence[PhotoResult],
    destination_root: Path,
    cancel_event: threading.Event | None = None,
    progress: Callable[[int, int, PhotoResult], None] | None = None,
) -> list[PhotoResult]:
    selected = [
        result
        for result in results
        if result.selected
        and result.status in {MatchStatus.CONFIDENT, MatchStatus.BORDERLINE}
        and result.copy_status != CopyStatus.COPIED
    ]
    cancellation = cancel_event or threading.Event()
    for index, result in enumerate(selected, start=1):
        if cancellation.is_set():
            break
        outcome = copy_preserving_structure(
            result.source_path,
            result.relative_path,
            destination_root,
        )
        result.copy_status = outcome.status
        result.copied_to = outcome.destination
        result.message = " ".join(value for value in (result.message, outcome.message) if value)
        if progress:
            progress(index, len(selected), result)
    return selected
