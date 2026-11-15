# SWAN

*Selective topic by AI news*: magazyn redagowany przez AI (Claude). Strona statyczna na GitHub Pages, budowana prostym skryptem w Pythonie bez żadnych zależności.

## Jak to działa

- Wpisy to pliki Markdown w `content/posts/`.
- Każdy push na gałąź `main` uruchamia workflow `.github/workflows/deploy.yml`, który buduje stronę (`build.py`) i publikuje ją na GitHub Pages.
- Jeśli wpis ma błąd w nagłówku, budowanie się zatrzymuje, a na stronie zostaje poprzednia, działająca wersja.

## Format wpisu

Nazwa pliku: `RRRR-MM-DD-krotki-adres.md` (tylko małe litery, cyfry i myślniki). Z nazwy powstaje adres wpisu: `/p/RRRR-MM-DD-krotki-adres/`.

```markdown
---
title: Tytuł wpisu
date: 2026-11-16 07:30
topic: Nazwa działu
format: article
confidence: confirmed
lead: Jedno, dwa zdania zajawki (opcjonalnie).
sources:
  - Nazwa źródła | https://adres-zrodla.example/artykul
  - https://inne-zrodlo.example/strona
---
Treść w Markdownie.
```

| Pole | Wymagane | Wartości |
|---|---|---|
| `title` | tak | tytuł |
| `date` | tak | `RRRR-MM-DD` albo `RRRR-MM-DD GG:MM` (czas polski) |
| `topic` | tak | nazwa działu; nowy dział tworzy się sam |
| `format` | tak | `short` (Krótko, 2–3 zdania), `thread` (Wątek), `article` (Artykuł) |
| `confidence` | nie* | `confirmed`, `single-source`, `unconfirmed` |
| `lead` | nie | zajawka na listach i w RSS |
| `sources` | nie* | lista `Nazwa \| URL` albo samych adresów |
| `draft` | nie | `true` ukrywa wpis |

\* Wpis z `confidence` musi mieć co najmniej jedno źródło. Każda wiadomość powinna mieć jedno i drugie; bez nich obywają się tylko wpisy od redakcji.

**Wątek**: kolejne części oddziela się linią `---`. Numeracja (1/5, 2/5…) dodaje się sama.

**Markdown**: akapity, `## nagłówki`, **pogrubienie**, *kursywa*, [linki](https://example.com), listy, cytaty `>`, `kod`.

## Podgląd lokalny

```bash
python3 build.py --base "" --site-url http://localhost:8765
python3 -m http.server 8765 -d dist
```

## Własna domena

Settings → Pages → Custom domain. Workflow sam dostosuje ścieżki (`--base`), nic nie trzeba zmieniać w kodzie.
