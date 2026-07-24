# Zasady pracy w projekcie Photo Face Finder

- Komunikacja i dokumentacja użytkownika są po polsku.
- Nie zapisuj sekretów, obrazów twarzy ani deskryptorów biometrycznych w repozytorium lub logach.
- Klucz OpenAI pochodzi wyłącznie ze zmiennej środowiskowej `OPENAI_API_KEY`.
- Nazwa modelu, timeouty, ponowienia i progi pochodzą z konfiguracji.
- Kod API OpenAI pozostaje oddzielony od logiki skanowania i kopiowania.
- Testy domyślnie używają dostawcy mock i nigdy nie wywołują płatnego API.
- Po większej sesji aktualizuj `PLANS.md`, `PROJECT_CONTEXT.md` i `HANDOFF.md`.
- Nie twórz commita bez wyraźnej zgody użytkownika.
