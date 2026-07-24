# Photo Face Finder

Desktopowa aplikacja dla Windows 10/11 x64, która wyszukuje zdjęcia zawierające wskazaną osobę i kopiuje wybrane trafienia do innego folderu.

## Wymagania deweloperskie

- Windows 10/11 x64
- Python 3.12
- PowerShell
- połączenie z internetem tylko podczas instalacji zależności i opcjonalnego używania OpenAI

Gotowy plik `PhotoFaceFinder.exe` nie wymaga instalacji Pythona.

## Najprostsze uruchomienie

Otwórz dwukrotnie:

```text
dist\PhotoFaceFinder.exe
```

Pierwsze uruchomienie może potrwać kilka sekund, ponieważ pojedynczy EXE rozpakowuje
komponenty do katalogu tymczasowego Windows.

## Struktura

- `src/` — kod aplikacji;
- `config/` — ustawienia bez sekretów;
- `resources/models/` — modele OpenCV;
- `tests/` — testy automatyczne;
- `scripts/` — skrypty budowania;
- `dist/` — gotowy EXE (ignorowany przez Git).

## Utworzenie środowiska

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt
```

Folderu `.venv` nie wolno kopiować na inny komputer.

## Uruchomienie

```powershell
$env:PYTHONPATH = "src"
python src\main.py
```

## Konfiguracja OpenAI przez `.env`

Otwórz plik `dist\.env` znajdujący się obok EXE i wklej klucz:

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.6-luna
```

Nie dodawaj spacji ani cudzysłowów. Zamknij i uruchom ponownie aplikację.
Plik `.env` jest ignorowany przez Git i nie jest wbudowany do EXE.

Jeśli `OPENAI_API_KEY` jest ustawiony również jako zmienna Windows, wartość systemowa
ma pierwszeństwo przed plikiem `.env`.

## Testy

```powershell
$env:PYTHONPATH = "src"
pytest
```

Testy nie korzystają z prawdziwego API OpenAI.

## Budowanie EXE

```powershell
.\scripts\build.ps1
```

Wynik: `dist\PhotoFaceFinder.exe`.

## Przeniesienie na inny komputer

Do zwykłego używania skopiuj wyłącznie `PhotoFaceFinder.exe`. Do dalszego rozwoju skopiuj repozytorium bez `.venv`, utwórz nowe środowisko wirtualne i ponownie zainstaluj biblioteki z `requirements.lock.txt`.

## Prywatność

W trybie lokalnym zdjęcia nie opuszczają komputera. W trybie OpenAI wysyłane są wyłącznie kadry wykrytych twarzy; wymagana jest zgoda osoby wzorcowej. Wzorce i deskryptory nie są trwale zapisywane.

## Ograniczenia

Rozpoznawanie twarzy nie jest nieomylne. Ujęcia niewyraźne, zasłonięte, bardzo małe
lub przedstawiające dzieci mogą wymagać ręcznej weryfikacji. Oryginalne zdjęcia
nigdy nie są usuwane ani modyfikowane.
