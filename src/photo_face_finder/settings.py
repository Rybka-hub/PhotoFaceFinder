from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def application_root() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root)
    return Path(__file__).resolve().parents[2]


def resource_path(relative: str | Path) -> Path:
    return application_root() / Path(relative)


def env_file_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / ".env")
    candidates.extend(
        [
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        ]
    )
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def load_environment_file(candidates: tuple[Path, ...] | None = None) -> Path | None:
    """Wczytaj pierwszy dostępny .env, nie nadpisując zmiennych Windows."""
    for candidate in candidates or env_file_candidates():
        if candidate.is_file():
            load_dotenv(candidate, override=False, encoding="utf-8-sig")
            return candidate
    return None


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    version: str
    max_references: int
    supported_extensions: frozenset[str]
    borderline_threshold: float
    confident_threshold: float
    detection_score_threshold: float
    detection_nms_threshold: float
    detection_top_k: int
    openai_model: str
    openai_timeout_seconds: float
    openai_max_retries: int
    openai_max_reference_faces: int
    yunet_model_path: Path
    sface_model_path: Path
    detection_max_dimension: int = 1920

    @classmethod
    def load(cls, config_path: Path | None = None) -> Settings:
        load_environment_file()
        path = config_path or resource_path("config/defaults.toml")
        with path.open("rb") as handle:
            data = tomllib.load(handle)

        application = data["application"]
        matching = data["matching"]
        detection = data["detection"]
        openai = data["openai"]
        models = data["models"]

        return cls(
            app_name=str(application["name"]),
            version=str(application["version"]),
            max_references=int(application["max_references"]),
            supported_extensions=frozenset(
                str(extension).casefold() for extension in application["supported_extensions"]
            ),
            borderline_threshold=float(matching["borderline_threshold"]),
            confident_threshold=float(matching["confident_threshold"]),
            detection_score_threshold=float(detection["score_threshold"]),
            detection_nms_threshold=float(detection["nms_threshold"]),
            detection_top_k=int(detection["top_k"]),
            openai_model=os.getenv("OPENAI_MODEL", str(openai["model"])),
            openai_timeout_seconds=float(openai["timeout_seconds"]),
            openai_max_retries=int(openai["max_retries"]),
            openai_max_reference_faces=int(openai["max_reference_faces"]),
            yunet_model_path=resource_path(str(models["yunet"])),
            sface_model_path=resource_path(str(models["sface"])),
            detection_max_dimension=int(detection.get("max_dimension", 1920)),
        )

    @property
    def openai_api_key(self) -> str | None:
        value = os.getenv("OPENAI_API_KEY")
        return value.strip() if value and value.strip() else None

    def validate_models(self) -> None:
        missing = [
            path.name
            for path in (self.yunet_model_path, self.sface_model_path)
            if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError("Brakuje modeli rozpoznawania twarzy: " + ", ".join(missing))
