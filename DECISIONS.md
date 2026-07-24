# Decyzje techniczne

## 2026-07-24 — PySide6 i PyInstaller

Wybrano PySide6 ze względu na dojrzałe komponenty, miniatury, tabele i bezpieczną komunikację między wątkami. PyInstaller tworzy pojedynczy plik bez konsoli.

## 2026-07-24 — OpenCV YuNet i SFace

YuNet wykrywa wszystkie twarze, a SFace tworzy deskryptory i oblicza podobieństwo cosinusowe. Rozwiązanie jest lokalne, działa na CPU i jest prostsze do spakowania na Windows niż dlib.

Obrazy większe niż 1920 pikseli na dłuższym boku są zmniejszane wyłącznie na czas detekcji, po czym współrzędne twarzy są mapowane na oryginalną rozdzielczość.

## 2026-07-24 — Wyniki graniczne

Oficjalny próg SFace 0,363 rozpoczyna zakres graniczny. Wynik co najmniej 0,45 jest pewny i może być kopiowany automatycznie.

## 2026-07-24 — Brak trwałych profili

Kadry, cechy i zdjęcia wzorcowe żyją wyłącznie w pamięci procesu. Zmniejsza to ryzyko prywatności i odpowiada modelowi jednej osoby na skan.

## 2026-07-24 — OpenAI jako tryb eksperymentalny

OpenAI porównuje ponumerowane kadry twarzy bez ustalania nazwiska. Dostawca jest odseparowany, posiada timeout i ograniczone ponowienia, a błędy nie zatrzymują całego skanu.

## 2026-07-24 — Klucz API z pliku `.env`

Wersja EXE odczytuje `.env` znajdujący się obok pliku wykonywalnego. Wartość
`OPENAI_API_KEY` już ustawiona w Windows ma pierwszeństwo, dzięki czemu `.env`
nie zmienia konfiguracji administratora.
