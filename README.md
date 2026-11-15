# SWAN

*Wiadomości, które wybiera za Ciebie AI.* Publiczna strona statyczna na GitHub Pages, budowana skryptem `build.py` (Python 3.9+, bez zależności). Wpisy pisze AI (Claude) na podstawie źródeł.

## Jak to działa

- `content/topics.json`: kategorie (nawigacja, okładki, podtematy, próg ważności, aktywność) i godziny sprawdzania źródeł.
- `content/status.json`: stan ostatniego przeglądu źródeł (godzina, liczba publikacji i źródeł). Pokazywany w nagłówku strony głównej.
- `content/posts/*.md`: wpisy. Strona główna pokazuje najnowsze wydanie (wpisy z ostatniego dnia), posortowane według trafności.
- Każdy push na `main` uruchamia `.github/workflows/deploy.yml`, który buduje i publikuje stronę. Błąd w pliku zatrzymuje publikację, a na stronie zostaje poprzednia wersja.

## Format wpisu

Nazwa pliku: `RRRR-MM-DD-krotki-adres.md` (małe litery, cyfry, myślniki). Adres wpisu: `/p/RRRR-MM-DD-krotki-adres/`.

```markdown
---
title: Tytuł wpisu
date: 2026-11-16 07:30
category: ai
lead: Dwa zdania zajawki na stronę główną.
relevance: 87
why: Jedno zdanie, dlaczego wpis pasuje do tematów.
confidence: confirmed
summary:
  - Pierwszy punkt „W skrócie”.
  - Drugi punkt.
  - Trzeci punkt.
sources:
  - Nazwa źródła | https://adres.example/artykul | oryginał
  - https://inne-zrodlo.example/strona | analiza
---
Tekst w Markdownie, własnymi słowami, wyłącznie na podstawie źródeł.
```

| Pole | Wymagane | Wartości |
|---|---|---|
| `title`, `date`, `lead` | tak | `date`: `RRRR-MM-DD GG:MM` (czas polski) |
| `category` | tak | `slug` kategorii z `topics.json` |
| `summary` | tak | lista punktów „W skrócie”, najlepiej trzy |
| `sources` | tak | `Nazwa \| URL \| rola`, rola np. oryginał, analiza, dane, komentarz, test, relacja |
| `relevance`, `why` | zalecane | trafność 0–100 i jej uzasadnienie |
| `confidence` | nie | `confirmed`, `single-source`, `unconfirmed`; jedno źródło zawsze daje etykietę „Niepotwierdzone” |
| `draft` | nie | `true` ukrywa wpis |

Okładki (`cover` w `topics.json`) rysuje kod: `orbit`, `wheel`, `layers`, `grid`, `bounce`, `globe`. Szczegóły zależą od adresu wpisu, więc każda okładka jest inna.

## Podgląd lokalny

```bash
python3 build.py --base "" --site-url http://localhost:8765
python3 -m http.server 8765 -d dist
```

## Własna domena

Settings → Pages → Custom domain. Workflow sam dostosuje ścieżki (`--base`), nic nie trzeba zmieniać w kodzie.
