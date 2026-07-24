from __future__ import annotations

import os
from pathlib import Path

from photo_face_finder.settings import load_environment_file


def test_load_environment_file_reads_key(tmp_path: Path, monkeypatch: object) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=test-from-file\nOPENAI_MODEL=test-model\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)  # type: ignore[attr-defined]
    monkeypatch.delenv("OPENAI_MODEL", raising=False)  # type: ignore[attr-defined]

    loaded = load_environment_file((env_file,))

    assert loaded == env_file
    assert os.environ["OPENAI_API_KEY"] == "test-from-file"
    assert os.environ["OPENAI_MODEL"] == "test-model"


def test_windows_environment_has_priority(tmp_path: Path, monkeypatch: object) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "from-windows")  # type: ignore[attr-defined]

    load_environment_file((env_file,))

    assert os.environ["OPENAI_API_KEY"] == "from-windows"
