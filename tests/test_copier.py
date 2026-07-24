from __future__ import annotations

import os
from pathlib import Path

import pytest

from photo_face_finder.copier import (
    PathValidationError,
    copy_preserving_structure,
    enumerate_images,
    validate_scan_paths,
)
from photo_face_finder.domain import CopyStatus


def test_enumerate_images_recursively_and_with_polish_path(tmp_path: Path) -> None:
    source = tmp_path / "ŹRÓDŁO"
    nested = source / "Wakacje Łódź"
    nested.mkdir(parents=True)
    (source / "a.JPG").write_bytes(b"a")
    (nested / "żółw.webp").write_bytes(b"b")
    (nested / "notatki.txt").write_text("x", encoding="utf-8")

    found = enumerate_images(source, frozenset({".jpg", ".webp"}))

    assert {path.name for path in found} == {"a.JPG", "żółw.webp"}


def test_validate_rejects_destination_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(PathValidationError):
        validate_scan_paths(source, source / "wyniki")


def test_copy_preserves_structure_metadata_and_skips_existing(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    destination = tmp_path / "destination"
    source_file = source_root / "album" / "photo.jpg"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"original")
    timestamp = 1_700_000_000
    os.utime(source_file, (timestamp, timestamp))

    first = copy_preserving_structure(source_file, Path("album/photo.jpg"), destination)
    second = copy_preserving_structure(source_file, Path("album/photo.jpg"), destination)

    assert first.status == CopyStatus.COPIED
    assert first.destination.read_bytes() == b"original"
    assert int(first.destination.stat().st_mtime) == timestamp
    assert second.status == CopyStatus.SKIPPED_EXISTS
