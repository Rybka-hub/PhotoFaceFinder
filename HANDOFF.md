# Przekazanie pracy

## Aktualny cel

Pierwsza wersja Photo Face Finder została ukończona. Następna sesja może dotyczyć
testów na prywatnym zestawie zdjęć użytkownika albo kolejnych funkcji.

## Wykonano

- Zbudowano GUI PySide6 z wyborem 1–10 wzorców i wskazywaniem twarzy na zdjęciu grupowym.
- Zaimplementowano rekursywny skan, wszystkie twarze na zdjęciu, progi pewne/graniczne
  oraz kopiowanie z zachowaniem struktury i metadanych.
- Dodano lokalny YuNet/SFace i eksperymentalny Responses API OpenAI.
- Dodano mock, timeout, ponowienia, zgodę, anulowanie, filtrowanie i ponawianie błędów API.
- Dodano automatyczne wczytywanie `OPENAI_API_KEY` z pliku `.env` obok EXE.
- Zablokowano dokładne wersje zależności i dołączono modele ONNX.
- Zbudowano i uruchomiono samodzielny `dist/PhotoFaceFinder.exe`.

## Co nie działa lub wymaga danych użytkownika

- Nie wykonano płatnego wywołania OpenAI, ponieważ nie używano prawdziwego klucza.
- Dokładność na prywatnym archiwum należy ocenić na zdjęciach użytkownika; testy automatyczne
  nie przechowują prawdziwych danych biometrycznych.

## Ważne pliki

- `dist/PhotoFaceFinder.exe` — gotowa aplikacja.
- `src/photo_face_finder/app.py` — GUI.
- `src/photo_face_finder/scanner.py` — przebieg skanowania.
- `src/photo_face_finder/providers/` — OpenCV, OpenAI i mock.
- `config/defaults.toml` — progi i ustawienia.

## Weryfikacja

- `pytest`: 8 testów zaliczonych.
- `ruff check src tests`: zaliczone.
- `mypy src`: zaliczone.
- YuNet: załadowany i uruchomiony na obrazie testowym.
- SFace: deskryptor 128 elementów, samopodobieństwo 1,0.
- EXE: uruchomiony w teście dymnym i pozostawał aktywny.

## Artefakt

- Rozmiar: 148 839 636 bajtów.
- SHA-256: `405D74DCD8FCF46063BCB62E1FE7B0ED75B5D4E50035DF30D105CC55FA69C8E8`.

## Ostatnie komendy

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm PhotoFaceFinder.spec
```
