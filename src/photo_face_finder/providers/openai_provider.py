from __future__ import annotations

import base64
import json
import math
import time
from collections.abc import Sequence
from io import BytesIO

import cv2
from openai import OpenAI
from PIL import Image, ImageDraw, ImageOps

from photo_face_finder.domain import (
    FaceSample,
    MatchStatus,
    ProviderDecision,
    ReferenceFace,
    UsageMetrics,
    safe_usage_value,
)
from photo_face_finder.settings import Settings, resource_path

_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["match", "uncertain", "no_match"],
        },
        "matching_candidate_indices": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
        },
    },
    "required": ["verdict", "matching_candidate_indices"],
    "additionalProperties": False,
}


def _sheet_data_url(
    samples: Sequence[FaceSample],
    start_index: int = 1,
    tile_size: int = 224,
) -> str:
    columns = min(5, max(1, len(samples)))
    rows = max(1, math.ceil(len(samples) / columns))
    label_height = 28
    sheet = Image.new(
        "RGB",
        (columns * tile_size, rows * (tile_size + label_height)),
        "white",
    )
    draw = ImageDraw.Draw(sheet)

    for offset, sample in enumerate(samples):
        row, column = divmod(offset, columns)
        rgb = cv2.cvtColor(sample.crop, cv2.COLOR_BGR2RGB)
        tile = ImageOps.fit(
            Image.fromarray(rgb),
            (tile_size, tile_size),
            method=Image.Resampling.LANCZOS,
        )
        x = column * tile_size
        y = row * (tile_size + label_height)
        sheet.paste(tile, (x, y + label_height))
        draw.rectangle((x, y, x + tile_size, y + label_height), fill="#172033")
        draw.text((x + 10, y + 7), f"Twarz {start_index + offset}", fill="white")

    with BytesIO() as buffer:
        sheet.save(buffer, format="JPEG", quality=90, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


class OpenAIFaceMatchProvider:
    _CANDIDATES_PER_CALL = 20

    def __init__(
        self,
        settings: Settings,
        references: Sequence[ReferenceFace],
        api_key: str,
    ) -> None:
        if not references:
            raise ValueError("Wymagane jest przynajmniej jedno zdjęcie wzorcowe.")
        if not api_key:
            raise ValueError("Brak zmiennej OPENAI_API_KEY.")

        selected = tuple(references[: settings.openai_max_reference_faces])
        self._reference_samples = tuple(
            FaceSample(crop=reference.crop, feature=None) for reference in selected
        )
        self._settings = settings
        self._client = OpenAI(
            api_key=api_key,
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )
        self._usage = UsageMetrics()
        self._prompt = resource_path("src/photo_face_finder/prompts/face_match.txt").read_text(
            encoding="utf-8"
        )
        self._reference_sheet = _sheet_data_url(self._reference_samples)

    @property
    def usage(self) -> UsageMetrics:
        return self._usage

    def _call(
        self,
        candidates: Sequence[FaceSample],
        candidate_start_index: int,
    ) -> ProviderDecision:
        candidate_sheet = _sheet_data_url(candidates, candidate_start_index)
        started = time.perf_counter()
        self._usage.api_calls += 1
        try:
            response = self._client.responses.create(
                model=self._settings.openai_model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": self._prompt},
                            {"type": "input_text", "text": "Arkusz wzorcowy:"},
                            {
                                "type": "input_image",
                                "image_url": self._reference_sheet,
                                "detail": "high",
                            },
                            {"type": "input_text", "text": "Arkusz kandydatów:"},
                            {
                                "type": "input_image",
                                "image_url": candidate_sheet,
                                "detail": "high",
                            },
                        ],
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "face_match_result",
                        "strict": True,
                        "schema": _SCHEMA,
                    }
                },
            )
            self._usage.elapsed_seconds += time.perf_counter() - started
            self._usage.input_tokens += safe_usage_value(response.usage, "input_tokens")
            self._usage.output_tokens += safe_usage_value(response.usage, "output_tokens")
            payload = json.loads(response.output_text)
            verdict = payload["verdict"]
            indices = tuple(int(index) - 1 for index in payload["matching_candidate_indices"])
            if verdict == "match":
                return ProviderDecision(
                    MatchStatus.CONFIDENT,
                    matched_face_indices=indices,
                    message="Dopasowanie przez OpenAI.",
                )
            if verdict == "uncertain":
                return ProviderDecision(
                    MatchStatus.BORDERLINE,
                    message="OpenAI oznaczyło wynik jako niepewny.",
                )
            return ProviderDecision(MatchStatus.NO_MATCH)
        except Exception as exc:  # SDK udostępnia wiele klas zależnych od wersji
            self._usage.elapsed_seconds += time.perf_counter() - started
            return ProviderDecision(
                MatchStatus.API_ERROR,
                message=f"OpenAI: {type(exc).__name__}: {exc}",
            )

    def match(self, candidates: Sequence[FaceSample]) -> ProviderDecision:
        if not candidates:
            return ProviderDecision(MatchStatus.NO_MATCH)

        saw_uncertain = False
        errors: list[str] = []
        for start in range(0, len(candidates), self._CANDIDATES_PER_CALL):
            batch = candidates[start : start + self._CANDIDATES_PER_CALL]
            decision = self._call(batch, start + 1)
            if decision.status == MatchStatus.CONFIDENT:
                return decision
            if decision.status == MatchStatus.BORDERLINE:
                saw_uncertain = True
            elif decision.status == MatchStatus.API_ERROR:
                errors.append(decision.message)

        if saw_uncertain:
            return ProviderDecision(
                MatchStatus.BORDERLINE,
                message="Co najmniej jedna grupa twarzy wymaga ręcznej weryfikacji.",
            )
        if errors:
            return ProviderDecision(MatchStatus.API_ERROR, message=" | ".join(errors))
        return ProviderDecision(MatchStatus.NO_MATCH)
