from __future__ import annotations

import os
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

from photo_face_finder.domain import DetectedFace, FaceSample
from photo_face_finder.settings import Settings


class ImageReadError(RuntimeError):
    pass


def _opencv_model_path(source: Path) -> Path:
    """OpenCV na Windows nie otwiera modeli z niektórych ścieżek Unicode."""
    resolved = source.resolve()
    if str(resolved).isascii():
        return resolved

    candidates = [
        Path(tempfile.gettempdir()) / "PhotoFaceFinder" / "models",
        Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "PhotoFaceFinder" / "models",
    ]
    last_error: OSError | None = None
    for directory in candidates:
        if not str(directory).isascii():
            continue
        try:
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / resolved.name
            if not target.exists() or target.stat().st_size != resolved.stat().st_size:
                shutil.copy2(resolved, target)
            return target
        except OSError as exc:
            last_error = exc
    raise ImageReadError(
        "Nie można przygotować modeli OpenCV w ścieżce zgodnej z Windows."
    ) from last_error


def load_oriented_bgr(path: Path) -> NDArray[np.uint8]:
    try:
        with Image.open(path) as opened:
            oriented = ImageOps.exif_transpose(opened)
            rgb = oriented.convert("RGB")
            array = np.asarray(rgb, dtype=np.uint8)
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise ImageReadError(f"Nie można odczytać obrazu: {exc}") from exc
    return np.ascontiguousarray(array[:, :, ::-1])


def bgr_to_jpeg_bytes(image: NDArray[np.uint8], quality: int = 90) -> bytes:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    with BytesIO() as buffer:
        Image.fromarray(rgb).save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()


def create_thumbnail_bytes(path: Path, size: tuple[int, int] = (160, 120)) -> bytes:
    try:
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail(size, Image.Resampling.LANCZOS)
            with BytesIO() as buffer:
                image.save(buffer, format="PNG")
                return buffer.getvalue()
    except (OSError, ValueError, UnidentifiedImageError):
        return b""


class FaceModels:
    def __init__(self, settings: Settings) -> None:
        settings.validate_models()
        yunet_path = _opencv_model_path(settings.yunet_model_path)
        sface_path = _opencv_model_path(settings.sface_model_path)
        self._max_detection_dimension = settings.detection_max_dimension
        self._detector = cv2.FaceDetectorYN.create(
            str(yunet_path),
            "",
            (320, 320),
            settings.detection_score_threshold,
            settings.detection_nms_threshold,
            settings.detection_top_k,
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(sface_path), "")

    def detect(self, image: NDArray[np.uint8]) -> list[DetectedFace]:
        height, width = image.shape[:2]
        if width < 2 or height < 2:
            return []
        scale = min(1.0, self._max_detection_dimension / max(width, height))
        detection_image = image
        detection_width, detection_height = width, height
        if scale < 1.0:
            detection_width = max(2, int(round(width * scale)))
            detection_height = max(2, int(round(height * scale)))
            detection_image = np.asarray(
                cv2.resize(
                    image,
                    (detection_width, detection_height),
                    interpolation=cv2.INTER_AREA,
                ),
                dtype=np.uint8,
            )
        self._detector.setInputSize((detection_width, detection_height))
        _, rows = self._detector.detect(detection_image)
        if rows is None:
            return []

        detected: list[DetectedFace] = []
        for row in rows:
            row = np.asarray(row, dtype=np.float32).copy()
            if scale < 1.0:
                row[:14] /= scale
            x, y, face_width, face_height = (int(round(float(value))) for value in row[:4])
            detected.append(
                DetectedFace(
                    raw=row,
                    x=max(0, x),
                    y=max(0, y),
                    width=max(1, face_width),
                    height=max(1, face_height),
                    confidence=float(row[-1]),
                )
            )
        return detected

    def crop(self, image: NDArray[np.uint8], face: DetectedFace) -> NDArray[np.uint8]:
        try:
            aligned = self._recognizer.alignCrop(image, face.raw)
            if aligned is not None and aligned.size:
                return np.ascontiguousarray(aligned)
        except cv2.error:
            pass

        height, width = image.shape[:2]
        x1 = max(0, face.x)
        y1 = max(0, face.y)
        x2 = min(width, face.x + face.width)
        y2 = min(height, face.y + face.height)
        if x2 <= x1 or y2 <= y1:
            raise ImageReadError("Wykryta twarz ma nieprawidłowe współrzędne.")
        return np.ascontiguousarray(image[y1:y2, x1:x2])

    def feature(self, aligned_crop: NDArray[np.uint8]) -> NDArray[np.float32]:
        value = self._recognizer.feature(aligned_crop)
        if value is None or not value.size:
            raise ImageReadError("Nie udało się utworzyć deskryptora twarzy.")
        return np.asarray(value, dtype=np.float32).reshape(-1).copy()

    def sample(self, image: NDArray[np.uint8], face: DetectedFace) -> FaceSample:
        crop = self.crop(image, face)
        return FaceSample(crop=crop, feature=self.feature(crop))

    def cosine_similarity(self, first: NDArray[np.float32], second: NDArray[np.float32]) -> float:
        first_row = first.reshape(1, -1)
        second_row = second.reshape(1, -1)
        return float(
            self._recognizer.match(
                first_row,
                second_row,
                cv2.FaceRecognizerSF_FR_COSINE,
            )
        )
