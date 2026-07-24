from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from photo_face_finder.domain import CopyStatus


class PathValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CopyOutcome:
    status: CopyStatus
    destination: Path
    message: str = ""


def validate_scan_paths(source: Path, destination: Path) -> tuple[Path, Path]:
    source_resolved = source.resolve()
    destination_resolved = destination.resolve()

    if not source_resolved.is_dir():
        raise PathValidationError("Folder źródłowy nie istnieje lub nie jest folderem.")
    if source_resolved == destination_resolved:
        raise PathValidationError("Folder docelowy nie może być folderem źródłowym.")
    if destination_resolved.is_relative_to(source_resolved):
        raise PathValidationError("Folder docelowy nie może znajdować się wewnątrz źródła.")
    return source_resolved, destination_resolved


def enumerate_images(source: Path, extensions: frozenset[str]) -> list[Path]:
    return sorted(
        (
            path
            for path in source.rglob("*")
            if path.is_file() and path.suffix.casefold() in extensions
        ),
        key=lambda path: str(path).casefold(),
    )


def copy_preserving_structure(
    source_file: Path,
    relative_path: Path,
    destination_root: Path,
) -> CopyOutcome:
    destination = destination_root / relative_path
    if destination.exists():
        return CopyOutcome(
            CopyStatus.SKIPPED_EXISTS,
            destination,
            "Plik docelowy już istnieje — pominięto.",
        )

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.copying")
        try:
            shutil.copy2(source_file, temporary)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return CopyOutcome(CopyStatus.COPIED, destination, "Skopiowano.")
    except OSError as exc:
        return CopyOutcome(CopyStatus.ERROR, destination, f"Błąd kopiowania: {exc}")
