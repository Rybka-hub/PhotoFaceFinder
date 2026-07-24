# Architektura

```text
GUI PySide6
  ├─ wybór wzorców → YuNet → wybór twarzy
  ├─ ustawienia skanu
  └─ QThread → ScanService
                 ├─ ImageLoader + YuNet
                 ├─ LocalOpenCVProvider → SFace
                 ├─ OpenAIProvider → Responses API
                 └─ FileCopier → zachowana struktura katalogów
```

## Przepływ

1. Użytkownik dodaje 1–10 zdjęć wzorcowych.
2. YuNet wykrywa wszystkie twarze; przy wielu twarzach użytkownik wskazuje właściwą.
3. Skaner rekursywnie znajduje obsługiwane zdjęcia.
4. Każda twarz jest kadrowana i przekazywana do wybranego dostawcy dopasowania.
5. Jedno dopasowanie wystarcza do zakwalifikowania całego zdjęcia.
6. Pewne lub ręcznie zaznaczone wyniki są kopiowane bez modyfikowania oryginału.

## Granice modułów

- `settings.py` — konfiguracja i zmienne środowiskowe.
- `imaging.py` — odczyt obrazów, orientacja EXIF, YuNet i SFace.
- `providers/` — wymienne sposoby dopasowania.
- `scanner.py` — orkiestracja skanu bez zależności od GUI.
- `copier.py` — bezpieczne kopiowanie.
- `app.py` — wyłącznie interfejs i obsługa wątków.

Plik `.env` jest odczytywany z katalogu obok EXE. Istniejąca zmienna środowiskowa
Windows ma pierwszeństwo i nie jest nadpisywana.
