#!/usr/bin/env python3
"""SWAN: generator statycznej strony magazynu (bez zależności, Python 3.9+).

Użycie:
    python3 build.py                                              # ustawienia z config.json
    python3 build.py --base "" --site-url http://localhost:8765   # podgląd lokalny

Wpisy: content/posts/*.md, tematy: content/topics.json, stan wydania: content/status.json.
Format opisuje README.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import math
import random
import re
import shutil
import sys
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
STATIC = ROOT / "static"
FONT_CSS = "https://cdn.jsdelivr.net/npm/@fontsource-variable/inter@5.2.8/opsz.css"

MONTHS = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
          "sierpnia", "września", "października", "listopada", "grudnia"]
MONTHS_NOM = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec",
              "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
MONTHS_SHORT = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]
WEEKDAYS = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
WEEKDAYS_SHORT = ["pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "niedz."]

CONFIDENCE = ("confirmed", "single-source", "unconfirmed")
THRESHOLDS = {"all": "Wszystko", "important": "Ważne", "breakthrough": "Przełomy"}
COVERS = ("orbit", "wheel", "layers", "grid", "bounce", "globe", "track", "hemicycle")

LOGO = (
    '<svg class="logo" viewBox="0 0 64 64" aria-hidden="true" focusable="false">'
    '<path class="logo-neck" d="M15 17c3-8 15-8 15 1 0 9-14 14-14 26" fill="none" stroke-width="6" stroke-linecap="round"/>'
    '<path class="logo-body" d="M13 42c2 9 13 13 26 11 10-1.5 17-8 20-18-6 4-12 5-18 3-9-3-19 0-28 4z"/>'
    '</svg>'
)
SEARCH_ICON = ('<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false" fill="none" '
               'stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/>'
               '<path d="m20 20-3.5-3.5"/></svg>')


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- pomocnicze

def esc(value) -> str:
    return html.escape(str(value), quote=True)


def plural(n: int, one: str, few: str, many: str) -> str:
    if n == 1:
        return one
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return few
    return many


def date_long(d) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def date_day(d) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}"


def date_short(d) -> str:
    return f"{d.day} {MONTHS_SHORT[d.month - 1]}"


def weekday(d) -> str:
    return WEEKDAYS[d.weekday()]


def hhmm(d) -> str:
    return d.strftime("%H:%M")


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:–—-") + "…"


def sources_phrase(n: int) -> str:
    """'Zebrane z 5 źródeł' na kartach i w nagłówku wpisu."""
    if n <= 1:
        return "Jedno źródło"
    return f"Zebrane z {n} źródeł"


def sources_short(n: int) -> str:
    return f"{n} {plural(n, 'źródło', 'źródła', 'źródeł')}"


# ---------------------------------------------------------------- markdown (podzbiór)

def inline(text: str) -> str:
    out = html.escape(text, quote=False)
    codes = []

    def keep_code(m):
        codes.append(f"<code>{m.group(1)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    out = re.sub(r"`([^`]+)`", keep_code, out)

    def link(m):
        label, url = m.group(1), html.unescape(m.group(2))
        attrs = ' rel="noopener" target="_blank"' if re.match(r"https?://", url) else ""
        return f'<a href="{esc(url)}"{attrs}>{label}</a>'

    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])", r"<em>\1</em>", out)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], out)


_UL = re.compile(r"^[-*]\s+(.*)$")
_OL = re.compile(r"^\d+[.)]\s+(.*)$")


def markdown(src: str) -> str:
    lines = src.replace("\r\n", "\n").split("\n")
    out, para = [], []
    i = 0

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    while i < len(lines):
        s = lines[i].strip()
        if not s:
            flush()
            i += 1
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", s)
        if heading:
            flush()
            level = min(4, max(2, len(heading.group(1))))  # h1 zarezerwowany na tytuł strony
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,})$", s):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if s.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote>{markdown(chr(10).join(quote))}</blockquote>")
            continue
        for pattern, tag in ((_UL, "ul"), (_OL, "ol")):
            if pattern.match(s):
                flush()
                items = []
                while i < len(lines) and lines[i].strip():
                    t = lines[i].strip()
                    m = pattern.match(t)
                    if m:
                        items.append(m.group(1))
                    elif lines[i][:1] in (" ", "\t") and items:
                        items[-1] += " " + t
                    else:
                        break
                    i += 1
                body = "".join(f"<li>{inline(item)}</li>" for item in items)
                out.append(f"<{tag}>{body}</{tag}>")
                break
        else:
            para.append(s)
            i += 1
    flush()
    return "\n".join(out)


def plain_text(md: str) -> str:
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md)
    t = re.sub(r"(?m)^\s*(#{1,6}|>|[-*]|\d+[.)])\s+", "", t)
    t = re.sub(r"(?m)^\s*-{3,}\s*$", " ", t)
    t = t.replace("**", "").replace("`", "")
    t = re.sub(r"(?<!\w)\*|\*(?!\w)", "", t)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------- okładki rysowane kodem

def _rng(seed: str) -> random.Random:
    return random.Random(int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16))


def _f(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def cover_shapes(kind: str, seed: str):
    """Motyw liniowy kategorii w układzie 640x400 i kadr dla miniatury. Szczegóły zależą od wpisu (seed)."""
    r = _rng(seed)
    out = []
    thumb = (180, 60, 280, 280)
    if kind == "orbit":
        cx, cy = 320 + r.randint(-50, 50), 200 + r.randint(-20, 20)
        radii = [26, 48, 72, 98, 126, 156, 190, 228, 270, 316]
        out += [f'<circle cx="{cx}" cy="{cy}" r="{rr}"/>' for rr in radii]
        for i, rr in enumerate(r.sample(radii[2:8], 4)):
            a = r.uniform(0, 2 * math.pi)
            x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
            cls = "fill" if i == 0 else "ring"
            out.append(f'<circle class="{cls}" cx="{_f(x)}" cy="{_f(y)}" r="{9 if i == 0 else 8}"/>')
        thumb = (cx - 165, cy - 165, 330, 330)
    elif kind == "wheel":
        cx, cy, big = 320 + r.randint(-40, 40), 352, 190
        y0 = 76
        out.append(f'<path d="M0 {y0}H640"/>')
        bx = r.randint(150, 420)
        out.append(f'<path class="bold" d="M{bx} {y0}H{bx + 96}"/>')
        for rr in (big, big - 26):
            out.append(f'<path d="M{cx - rr} {cy}A{rr} {rr} 0 0 1 {cx + rr} {cy}"/>')
        hub = 36
        out.append(f'<path class="bold" d="M{cx - hub} {cy}A{hub} {hub} 0 0 1 {cx + hub} {cy}"/>')
        n = r.choice([14, 16, 18])
        for i in range(1, n):
            a = math.pi + math.pi * i / n
            x1, y1 = cx + hub * math.cos(a), cy + hub * math.sin(a)
            x2, y2 = cx + (big - 26) * math.cos(a), cy + (big - 26) * math.sin(a)
            out.append(f'<path d="M{_f(x1)} {_f(y1)}L{_f(x2)} {_f(y2)}"/>')
        out.append(f'<path d="M0 {cy}H640"/>')
        thumb = (cx - 200, cy - 230, 400, 260)
    elif kind == "layers":
        neck = r.uniform(0.42, 0.62)
        wide, narrow = r.randint(130, 170), r.randint(30, 55)
        ys = list(range(70, 320, 9))
        bold_i = min(range(len(ys)), key=lambda k: abs((ys[k] - 70) / 250 - neck))
        for k, y in enumerate(ys):
            t = (y - 70) / 250
            w = narrow + (wide - narrow) * min(1.0, abs(t - neck) / max(neck, 1 - neck)) ** 0.9
            cls = ' class="bold"' if k == bold_i else ""
            out.append(f'<path{cls} d="M{_f(320 - w)} {y}H{_f(320 + w)}"/>')
        out.append('<path d="M120 342H520"/>')
        thumb = (130, 50, 380, 310)
    elif kind == "grid":
        cols, rows, size, gap = 8, 3, 46, 14
        x0 = (640 - (cols * size + (cols - 1) * gap)) / 2
        y0 = (400 - (rows * size + (rows - 1) * gap)) / 2
        pick = (r.randrange(rows), r.randrange(cols))
        for row in range(rows):
            for col in range(cols):
                x, y = x0 + col * (size + gap), y0 + row * (size + gap)
                cls = ' class="fill"' if (row, col) == pick else ""
                out.append(f'<rect{cls} x="{_f(x)}" y="{_f(y)}" width="{size}" height="{size}" rx="10"/>')
        fx, fy = x0 + pick[1] * (size + gap) + size / 2, y0 + pick[0] * (size + gap) + size / 2
        thumb = (fx - 110, fy - 110, 220, 220)
    elif kind == "bounce":
        base = 330
        out.append(f'<path d="M40 {base}H600"/>')
        x = 70
        apex = None
        hops = [(200, 190), (140, 150), (90, 115), (52, 85)]
        pick = r.randrange(len(hops))
        for i, (h, w) in enumerate(hops):
            out.append(f'<path class="dash" d="M{x} {base}Q{x + w / 2} {base - 2 * h} {x + w} {base}"/>')
            if i == pick:
                apex = (x + w / 2, base - h)
            x += w
        out.append(f'<circle class="fill" cx="{_f(apex[0])}" cy="{_f(apex[1] - 13)}" r="13"/>')
        out.append(f'<path class="bold" d="M{_f(apex[0] - 30)} {base}H{_f(apex[0] + 30)}"/>')
        thumb = (apex[0] - 150, base - 250, 300, 280)
    elif kind == "globe":
        cx, cy, R = 320, 200, 150
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{R}"/>')
        for k in (0.25, 0.55, 0.82):
            out.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{_f(R * k)}" ry="{R}"/>')
        out.append(f'<path d="M{cx} {cy - R}V{cy + R}"/>')
        for lat in (-50, -22, 0, 22, 50):
            y = cy + R * math.sin(math.radians(lat))
            half = R * math.cos(math.radians(lat))
            out.append(f'<path d="M{_f(cx - half)} {_f(y)}H{_f(cx + half)}"/>')
        a1, a2 = r.uniform(200, 240), r.uniform(300, 340)
        p1 = (cx + R * 0.7 * math.cos(math.radians(a1)), cy - R * 0.7 * math.sin(math.radians(a1)) + 60)
        p2 = (cx + R * 0.75 * math.cos(math.radians(a2)), cy - R * 0.75 * math.sin(math.radians(a2)) - 70)
        mid = ((p1[0] + p2[0]) / 2 + 40, min(p1[1], p2[1]) - 90)
        out.append(f'<path class="dash bold" d="M{_f(p1[0])} {_f(p1[1])}Q{_f(mid[0])} {_f(mid[1])} {_f(p2[0])} {_f(p2[1])}"/>')
        out.append(f'<circle class="ring" cx="{_f(p1[0])}" cy="{_f(p1[1])}" r="8"/>')
        out.append(f'<circle class="fill" cx="{_f(p2[0])}" cy="{_f(p2[1])}" r="9"/>')
        thumb = (cx - 170, cy - 170, 340, 340)
    elif kind == "track":
        base = [(120, 300), (105, 190), (165, 110), (285, 118), (335, 175), (420, 108),
                (530, 118), (550, 222), (472, 250), (420, 305), (300, 322), (200, 332)]
        pts = [(x + r.randint(-14, 14), y + r.randint(-12, 12)) for x, y in base]
        mx = sum(x for x, _ in pts) / len(pts)
        my = sum(y for _, y in pts) / len(pts)

        def loop(points):
            n = len(points)
            d = f"M{_f(points[0][0])} {_f(points[0][1])}"
            for i in range(n):
                p0, p1, p2, p3 = points[i - 1], points[i], points[(i + 1) % n], points[(i + 2) % n]
                c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
                c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
                d += f"C{_f(c1[0])} {_f(c1[1])} {_f(c2[0])} {_f(c2[1])} {_f(p2[0])} {_f(p2[1])}"
            return d + "Z"

        inner = [(mx + (x - mx) * 0.84, my + (y - my) * 0.84) for x, y in pts]
        out.append(f'<path d="{loop(pts)}"/>')
        out.append(f'<path d="{loop(inner)}"/>')
        s0, s1 = pts[0], inner[0]
        out.append(f'<path class="bold" d="M{_f(s0[0])} {_f(s0[1])}L{_f(s1[0])} {_f(s1[1])}"/>')
        k = r.randrange(2, len(pts) - 2)
        car = ((pts[k][0] + inner[k][0]) / 2, (pts[k][1] + inner[k][1]) / 2)
        out.append(f'<circle class="fill" cx="{_f(car[0])}" cy="{_f(car[1])}" r="9"/>')
        j = (k + 1) % len(pts)
        rival = ((pts[j][0] + inner[j][0]) / 2, (pts[j][1] + inner[j][1]) / 2)
        out.append(f'<circle class="ring" cx="{_f(rival[0])}" cy="{_f(rival[1])}" r="8"/>')
        thumb = (car[0] - 140, car[1] - 140, 280, 280)
    elif kind == "hemicycle":
        cx, cy = 320, 345
        out.append(f'<path d="M40 {cy}H600"/>')
        seats = []
        for rr in (110, 140, 170, 200, 230, 260, 290):
            n = max(6, round(math.pi * rr / 27))
            for i in range(n):
                a = math.pi + math.pi * (i + 0.5) / n
                seats.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        pick = r.randrange(len(seats))
        for i, (x, y) in enumerate(seats):
            cls = ' class="fill"' if i == pick else ""
            out.append(f'<circle{cls} cx="{_f(x)}" cy="{_f(y)}" r="6"/>')
        out.append(f'<path class="bold" d="M{cx - 34} {cy - 22}H{cx + 34}"/>')
        fx, fy = seats[pick]
        thumb = (fx - 110, fy - 110, 220, 220)
    return "".join(out), thumb


def cover(kind: str, seed: str, size: str = "lg") -> str:
    shapes, thumb = cover_shapes(kind, seed)
    box = "0 0 640 400" if size != "sm" else " ".join(_f(v) for v in thumb)
    fit = "slice" if size != "sm" else "meet"
    return (f'<div class="cover cover--{size}" aria-hidden="true"><svg viewBox="{box}" '
            f'preserveAspectRatio="xMidYMid {fit}" focusable="false">{shapes}</svg></div>')


# ---------------------------------------------------------------- pliki z treścią

_FRONT = re.compile(r"\A---\n(.*?)\n---[ \t]*(?:\n(.*))?\Z", re.S)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def read_document(path: Path):
    text = path.read_text(encoding="utf-8").lstrip(chr(0xFEFF)).replace("\r\n", "\n")
    m = _FRONT.match(text)
    if not m:
        raise BuildError(f"{path.name}: plik musi zaczynać się od nagłówka między liniami ---")
    meta, current = {}, None
    for n, raw in enumerate(m.group(1).split("\n"), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s*-\s+(.*)$", raw)
        if item and current is not None:
            meta[current].append(_unquote(item.group(1)))
            continue
        kv = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", raw)
        if not kv:
            raise BuildError(f"{path.name}: nie rozumiem linii {n} nagłówka: {raw.strip()!r}")
        key, value = kv.group(1).lower(), kv.group(2)
        if value.strip():
            meta[key], current = _unquote(value), None
        else:
            meta[key], current = [], key
    return meta, (m.group(2) or "").strip("\n")


def _parse_datetime(value: str, name: str) -> dt.datetime:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value.strip(), fmt)
        except ValueError:
            pass
    raise BuildError(f"{name}: data {value!r} musi mieć postać RRRR-MM-DD albo RRRR-MM-DD GG:MM")


def _parse_source(raw: str, name: str) -> dict:
    parts = [p.strip() for p in raw.split(" | ")]
    url_i = next((i for i, p in enumerate(parts) if re.match(r"^https?://\S+$", p)), None)
    if url_i is None:
        raise BuildError(f"{name}: źródło {raw!r} musi zawierać adres http(s)://")
    url = parts[url_i]
    label = " | ".join(parts[:url_i]).strip()
    role = " | ".join(parts[url_i + 1:]).strip()
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    return {"name": label or host, "url": url, "host": host, "role": role}


def _text(meta: dict, key: str, name: str, required: bool = False) -> str:
    value = meta.get(key, "")
    if isinstance(value, list):
        raise BuildError(f"{name}: pole '{key}' powinno być jedną linijką tekstu")
    if required and not value.strip():
        raise BuildError(f"{name}: brak wymaganego pola '{key}'")
    return value.strip()


def _list(meta: dict, key: str) -> list:
    value = meta.get(key, [])
    return [value] if isinstance(value, str) else value


def load_topics() -> dict:
    data = json.loads((CONTENT / "topics.json").read_text(encoding="utf-8"))
    seen = set()
    for c in data["categories"]:
        for key in ("slug", "name", "cover"):
            if not c.get(key):
                raise BuildError(f"topics.json: kategoria bez pola '{key}'")
        if not re.fullmatch(r"[a-z0-9-]+", c["slug"]) or c["slug"] in seen:
            raise BuildError(f"topics.json: niepoprawny lub powtórzony slug {c['slug']!r}")
        if c["cover"] not in COVERS:
            raise BuildError(f"topics.json: okładka {c['cover']!r} musi być jedną z: {', '.join(COVERS)}")
        if c.get("threshold", "all") not in THRESHOLDS:
            raise BuildError(f"topics.json: próg {c.get('threshold')!r} musi być jednym z: {', '.join(THRESHOLDS)}")
        seen.add(c["slug"])
    return data


def load_status() -> dict:
    path = CONTENT / "status.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("checked_at"):
        data["checked_at"] = _parse_datetime(data["checked_at"], "status.json")
    return data


def load_posts(folder: Path, categories: dict) -> list:
    posts = []
    for path in sorted(folder.glob("*.md")):
        name = path.name
        meta, body = read_document(path)
        if str(meta.get("draft", "")).lower() in ("true", "tak", "yes"):
            continue
        if not re.fullmatch(r"[a-z0-9-]+", path.stem):
            raise BuildError(f"{name}: nazwa pliku może zawierać tylko małe litery, cyfry i myślniki")
        category = _text(meta, "category", name, True)
        if category not in categories:
            raise BuildError(f"{name}: kategoria {category!r} nie istnieje w topics.json "
                             f"(dostępne: {', '.join(categories)})")
        conf = _text(meta, "confidence", name) or None
        if conf and conf not in CONFIDENCE:
            raise BuildError(f"{name}: confidence musi być jednym z: {', '.join(CONFIDENCE)}")
        sources = [_parse_source(s, name) for s in _list(meta, "sources")]
        if not sources:
            raise BuildError(f"{name}: wpis musi mieć co najmniej jedno źródło")
        summary = _list(meta, "summary")
        if not summary:
            raise BuildError(f"{name}: brak punktów 'summary' (W skrócie)")
        relevance = _text(meta, "relevance", name)
        if relevance and not (relevance.isdigit() and 0 <= int(relevance) <= 100):
            raise BuildError(f"{name}: relevance musi być liczbą 0-100")
        if not body.strip():
            raise BuildError(f"{name}: wpis nie ma treści")
        words = len(re.findall(r"\w+", body + " " + " ".join(summary)))
        unconfirmed = conf in ("single-source", "unconfirmed") or len(sources) == 1
        posts.append({
            "slug": path.stem,
            "title": _text(meta, "title", name, True),
            "date": _parse_datetime(_text(meta, "date", name, True), name),
            "category": categories[category],
            "lead": _text(meta, "lead", name, True),
            "summary": summary,
            "relevance": int(relevance) if relevance else None,
            "why": _text(meta, "why", name),
            "unconfirmed": unconfirmed,
            "sources": sources,
            "html": markdown(body),
            "minutes": max(1, round(words / 200)),
        })
    posts.sort(key=lambda p: (p["date"], p["relevance"] or 0, p["slug"]), reverse=True)
    return posts


# ---------------------------------------------------------------- strona

class Site:
    def __init__(self, config: dict, base: str, site_url: str, posts_dir: Path):
        self.c = config
        self.base = base.rstrip("/")
        self.site_url = site_url.rstrip("/")
        self.topics = load_topics()
        self.cats = {c["slug"]: c for c in self.topics["categories"]}
        self.status = load_status()
        self.posts = load_posts(posts_dir, self.cats)
        self.asset_v = hashlib.sha1(b"".join(p.read_bytes() for p in sorted(STATIC.glob("*.*")))).hexdigest()[:8]
        self.pages = []

    # ---------- adresy

    def u(self, path: str) -> str:
        return self.base + path

    def absolute(self, path: str) -> str:
        return self.site_url + path

    def post_url(self, p: dict) -> str:
        return self.u(f"/p/{p['slug']}/")

    def cat_url(self, slug: str) -> str:
        return self.u(f"/kategoria/{slug}/")

    # ---------- szkielet

    def layout(self, *, title: str, body: str, path: str, description: str = "", current: str = "",
               kind: str = "website", home: bool = False) -> str:
        c = self.c
        full_title = title if home else f"{title} · {c['title']}"
        desc = description or c["description"]

        def nav_link(href: str, label: str, key: str) -> str:
            mark = ' aria-current="page"' if current == key else ""
            return f'<a href="{href}"{mark}>{esc(label)}</a>'

        links = [nav_link(self.u("/"), "Dziś", "home")]
        links += [nav_link(self.cat_url(cat["slug"]), cat["name"], cat["slug"])
                  for cat in self.topics["categories"] if cat.get("active", True)]
        topics_mark = ' aria-current="page"' if current == "topics" else ""
        self.pages.append(path)
        return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(self.absolute(path))}">
<link rel="icon" href="{self.u('/favicon.svg')}" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{esc(c['title'])}" href="{self.u('/feed.xml')}">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="{FONT_CSS}">
<link rel="stylesheet" href="{self.u('/style.css')}?v={self.asset_v}">
<meta name="theme-color" content="#fbfbfd" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#111215" media="(prefers-color-scheme: dark)">
<meta property="og:site_name" content="{esc(c['title'])}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="{kind}">
<meta property="og:url" content="{esc(self.absolute(path))}">
<meta property="og:locale" content="pl_PL">
<script defer src="{self.u('/app.js')}?v={self.asset_v}"></script>
</head>
<body>
<a class="skip" href="#tresc">Przejdź do treści</a>
<header class="nav">
  <div class="wrap nav-inner">
    <a class="brand" href="{self.u('/')}" aria-label="{esc(c['title'])}, strona główna">{LOGO}<span>{esc(c['title'])}</span></a>
    <nav class="nav-links" aria-label="Kategorie">{''.join(links)}</nav>
    <div class="nav-tools">
      <a class="icon-btn" href="{self.u('/szukaj/')}" aria-label="Szukaj" data-search-link{' aria-current="page"' if current == 'search' else ''}>{SEARCH_ICON}</a>
      <a class="pill" href="{self.u('/tematy/')}"{topics_mark}>Twoje tematy</a>
    </div>
  </div>
</header>
<main id="tresc">
{body}
</main>
<footer class="footer">
  <div class="wrap footer-inner">
    <p><strong>{esc(c['title'])}</strong> · {esc(c['tagline'])}. Wpisy pisze AI (Claude) wyłącznie na podstawie podanych źródeł. W razie rozbieżności rację ma źródło.</p>
    <p class="footer-links"><a href="{self.u('/o-swan/')}">Jak to działa</a><a href="{self.u('/archiwum/')}">Archiwum</a><a href="{self.u('/feed.xml')}">RSS</a></p>
  </div>
</footer>
</body>
</html>
"""

    # ---------- klocki

    def kicker(self, p: dict, link: bool = False) -> str:
        name = esc(p["category"]["name"])
        label = f'<a href="{self.cat_url(p["category"]["slug"])}">{name}</a>' if link else name
        return f'<p class="kicker"><span class="dot" aria-hidden="true"></span>{label}</p>'

    def meta(self, p: dict, short: bool = False) -> str:
        if short:
            bits = [sources_short(len(p["sources"])), f"{p['minutes']} min"]
        else:
            bits = [sources_phrase(len(p["sources"])), f"{p['minutes']} min czytania"]
        flag = '<span class="flag">Niepotwierdzone</span>' if p["unconfirmed"] else ""
        return f'<p class="meta">{esc(", ".join(bits))}{flag}</p>'

    def lead_story(self, p: dict) -> str:
        kind = p["category"]["cover"]
        return (f'<article class="lead-story item" data-slug="{p["slug"]}">'
                f'{cover(kind, p["slug"], "lg")}'
                f'<div class="lead-body">{self.kicker(p)}'
                f'<h2 class="lead-title"><a class="stretch" href="{self.post_url(p)}">{esc(p["title"])}</a></h2>'
                f'<p class="lead-text">{esc(p["lead"])}</p>{self.meta(p)}</div></article>')

    def card(self, p: dict) -> str:
        return (f'<article class="card item" data-slug="{p["slug"]}">'
                f'{cover(p["category"]["cover"], p["slug"], "md")}{self.kicker(p)}'
                f'<h3 class="card-title"><a class="stretch" href="{self.post_url(p)}">{esc(p["title"])}</a></h3>'
                f'<p class="card-text">{esc(truncate(p["lead"], 150))}</p>{self.meta(p, short=True)}</article>')

    def row(self, p: dict, with_date: bool = False) -> str:
        meta = self.meta(p, short=True)
        if with_date:
            meta = meta.replace('<p class="meta">', f'<p class="meta">{date_short(p["date"])} · ', 1)
        return (f'<article class="row item" data-slug="{p["slug"]}"><div class="row-body">'
                f'<h3 class="row-title"><span class="dot" aria-hidden="true"></span>'
                f'<a class="stretch" href="{self.post_url(p)}">{esc(p["title"])}</a></h3>{meta}</div>'
                f'{cover(p["category"]["cover"], p["slug"], "sm")}</article>')

    def next_check(self) -> str:
        checked = self.status.get("checked_at")
        slots = sorted(self.topics.get("schedule", []))
        if not checked or not slots:
            return ""
        for slot in slots:
            h, m = map(int, slot.split(":"))
            candidate = checked.replace(hour=h, minute=m)
            if candidate > checked:
                return f"Następne sprawdzenie {slot}"
        h, m = map(int, slots[0].split(":"))
        nxt = checked + dt.timedelta(days=1)
        return f"Następne sprawdzenie: {WEEKDAYS_SHORT[nxt.weekday()]} {date_short(nxt)}, {slots[0]}"

    def status_block(self) -> str:
        checked = self.status.get("checked_at")
        if not checked:
            return ""
        other = f"Sprawdzono {date_day(checked)} o {hhmm(checked)}"
        nxt = self.next_check()
        return (f'<div class="status"><p><span class="dot" aria-hidden="true"></span>'
                f'<span data-today data-other="{esc(other)}">Sprawdzono o {hhmm(checked)}</span></p>'
                f'{f"<p>{esc(nxt)}</p>" if nxt else ""}</div>')

    # ---------- strony

    def render_home(self) -> str:
        if not self.posts:
            body = ('<section class="wrap hero"><h1 class="hero-title">Pierwsze wydanie jest w drodze.</h1>'
                    '<p class="hero-text">Wróć po najbliższym sprawdzeniu źródeł.</p></section>')
            return self.layout(title=self.c["title"], body=body, path="/", current="home", home=True)

        live = [p for p in self.posts if p["category"].get("active", True)] or self.posts
        day = live[0]["date"].date()
        edition = sorted([p for p in live if p["date"].date() == day],
                         key=lambda p: (-(p["relevance"] or 0), p["date"]))
        n = len(edition)
        minutes = sum(p["minutes"] for p in edition)
        things = f"{n} {plural(n, 'rzecz warta', 'rzeczy warte', 'rzeczy wartych')} Twojej uwagi."
        pubs, outlets = self.status.get("publications"), self.status.get("outlets")
        scanned = ""
        if pubs and outlets:
            scanned = (f"SWAN przejrzał {pubs} {plural(pubs, 'publikację', 'publikacje', 'publikacji')} "
                       f"z {outlets} {plural(outlets, 'źródła', 'źródeł', 'źródeł')} i zostawił to, "
                       f"co pasuje do Twoich tematów. ")
        read_time = f"Całość przeczytasz w {minutes} {plural(minutes, 'minutę', 'minuty', 'minut')}."

        top, important, rest = edition[0], edition[1:4], edition[4:]
        parts = [f'<section class="wrap hero" data-edition="{day.isoformat()}">'
                 f'<p class="dateline">{weekday(day).capitalize()}, {date_day(day)}</p>'
                 f'<div class="hero-grid"><div><h1 class="hero-title">'
                 f'<span data-today data-other="">Dziś </span>{things}</h1>'
                 f'<p class="hero-text">{esc(scanned + read_time)}</p></div>{self.status_block()}</div>'
                 f'{self.lead_story(top)}</section>']
        if important:
            parts.append(f'<section class="wrap block" aria-labelledby="najwazniejsze"><div class="block-head">'
                         f'<h2 id="najwazniejsze">Najważniejsze</h2>'
                         f'<p class="counter" data-counter>{n} {plural(n, "wpis", "wpisy", "wpisów")}</p></div>'
                         f'<div class="cards">{"".join(self.card(p) for p in important)}</div></section>')
        if rest:
            groups = []
            for cat in self.topics["categories"]:
                items = [p for p in rest if p["category"]["slug"] == cat["slug"]]
                if items:
                    groups.append(f'<section class="group"><h2><a href="{self.cat_url(cat["slug"])}">'
                                  f'{esc(cat["name"])}</a></h2>{"".join(self.row(p) for p in items)}</section>')
            parts.append(f'<div class="wrap block groups">{"".join(groups)}</div>')
        nxt = self.next_check()
        parts.append(f'<section class="wrap end"><p class="end-title" data-today '
                     f'data-other="To wszystko w tym wydaniu.">To wszystko na dziś.</p>'
                     f'<p class="end-text">{esc(nxt + ". " if nxt else "")}Starsze wpisy znajdziesz w '
                     f'<a href="{self.u("/archiwum/")}">archiwum</a>.</p></section>')
        title = f"{self.c['title']}: {self.c['tagline']}"
        return self.layout(title=title, body="".join(parts), path="/", current="home", home=True,
                           description=f"{n} {plural(n, 'rzecz', 'rzeczy', 'rzeczy')} z {date_long(day)}. "
                                       + self.c["description"])

    def render_post(self, p: dict) -> str:
        cat = p["category"]
        summary = "".join(f"<li>{inline(s)}</li>" for s in p["summary"])
        sources = "".join(
            f'<li><a href="{esc(s["url"])}" rel="noopener" target="_blank">{esc(s["name"])}</a>'
            f'<span class="role">{esc(s["role"] or s["host"])}</span></li>' for s in p["sources"])
        why = ""
        if p["relevance"] is not None:
            why = (f'<section class="side-block why"><h2>Dlaczego to widzisz</h2>'
                   f'<p class="score"><strong>{p["relevance"]}</strong> na 100 trafności</p>'
                   f'<div class="bar" role="img" aria-label="Trafność {p["relevance"]} na 100">'
                   f'<span style="width:{p["relevance"]}%"></span></div>'
                   f'{f"<p>{esc(p[chr(119) + chr(104) + chr(121)])}</p>" if p["why"] else ""}</section>')
        flag = ""
        if p["unconfirmed"]:
            flag = ('<section class="side-block"><p class="note"><span class="flag">Niepotwierdzone</span> '
                    'Informacja ma tylko jedno źródło albo opiera się na nieoficjalnych doniesieniach.</p></section>')
        related = [q for q in self.posts if q["category"]["slug"] == cat["slug"] and q["slug"] != p["slug"]][:3]
        related_html = ""
        if related:
            related_html = (f'<section class="related"><h2>Więcej: {esc(cat["name"])}</h2>'
                            f'{"".join(self.row(q, with_date=True) for q in related)}</section>')
        meta = (f'{sources_phrase(len(p["sources"]))}, {p["minutes"]} min czytania, '
                f'opublikowano {date_day(p["date"])} o {hhmm(p["date"])}')
        body = (f'<div class="wrap article-grid"><article class="article" data-article="{p["slug"]}">'
                f'<header class="article-head">{self.kicker(p, link=True)}<h1>{esc(p["title"])}</h1>'
                f'<p class="meta">{esc(meta)}</p></header>'
                f'{cover(cat["cover"], p["slug"], "lg")}'
                f'<section class="tldr"><h2>W skrócie</h2><ul>{summary}</ul></section>'
                f'<div class="prose">{p["html"]}</div></article>'
                f'<aside class="article-side">{why}<section class="side-block sources"><h2>Źródła</h2>'
                f'<ul>{sources}</ul></section>{flag}'
                f'<p class="ai-note">Wpis przygotowało AI (Claude) na podstawie powyższych źródeł.</p></aside>'
                f'{related_html}</div>')
        return self.layout(title=p["title"], body=body, path=f"/p/{p['slug']}/", current=cat["slug"],
                           description=p["lead"], kind="article")

    def render_category(self, cat: dict) -> str:
        items = [p for p in self.posts if p["category"]["slug"] == cat["slug"]]
        chips = "".join(f'<li>{esc(s)}</li>' for s in cat.get("subtopics", []))
        rows = "".join(self.row(p, with_date=True) for p in items) or \
            '<p class="empty">W tej kategorii nie ma jeszcze wpisów.</p>'
        body = (f'<div class="wrap page"><header class="page-head"><h1>{esc(cat["name"])}</h1>'
                f'<p>{esc(cat.get("description", ""))}</p><ul class="chips">{chips}</ul></header>'
                f'<div class="list">{rows}</div></div>')
        return self.layout(title=cat["name"], body=body, path=f"/kategoria/{cat['slug']}/", current=cat["slug"],
                           description=cat.get("description", ""))

    def render_topics(self) -> str:
        rows = []
        cats = self.topics["categories"]
        ordered = [c for c in cats if c.get("active", True)] + [c for c in cats if not c.get("active", True)]
        for idx, cat in enumerate(ordered):
            if not cat.get("active", True) and (idx == 0 or ordered[idx - 1].get("active", True)):
                rows.append('<h2 class="topics-sub">Uśpione</h2>')
            chips = "".join(f'<li>{esc(s)}</li>' for s in cat.get("subtopics", []))
            if cat.get("sources"):
                chips += "".join(f'<li class="chip-src">{esc(s)}</li>' for s in cat["sources"])
            current = cat.get("threshold", "all")
            seg = "".join(f'<span{" class=on" if key == current else ""}>{label}</span>'
                          for key, label in THRESHOLDS.items())
            active = cat.get("active", True)
            state = "Aktywny" if active else "Uśpiony"
            rows.append(f'<section class="topic{"" if active else " is-off"}"><div class="topic-main">'
                        f'<h2>{esc(cat["name"])}</h2><p>{esc(cat.get("description", ""))}</p>'
                        f'<ul class="chips">{chips}</ul></div><div class="topic-side">'
                        f'<p class="segmented" aria-label="Próg ważności: {THRESHOLDS[current]}">{seg}</p>'
                        f'<p class="switch{" on" if active else ""}" aria-label="{state}">'
                        f'<span class="switch-knob"></span><span class="sr-only">{state}</span></p></div></section>')
        sched = ", ".join(self.topics.get("schedule", []))
        body = (f'<div class="wrap page narrow"><header class="page-head"><h1>Twoje tematy</h1>'
                f'<p>Tematy, które śledzi SWAN, i to, jak bardzo coś musi być ważne, żeby trafiło do wydania. '
                f'Sprawdzanie źródeł: codziennie o {esc(sched)}. Żeby coś zmienić, napisz do redakcji (Claude), '
                f'zwykłymi słowami.</p></header>{"".join(rows)}</div>')
        return self.layout(title="Twoje tematy", body=body, path="/tematy/", current="topics")

    def render_archive(self) -> str:
        days, out = [], []
        for p in self.posts:
            d = p["date"].date()
            if not days or days[-1][0] != d:
                days.append((d, []))
            days[-1][1].append(p)
        for d, items in days:
            out.append(f'<section class="archive-day"><h2>{weekday(d).capitalize()}, {date_long(d)}</h2>'
                       f'{"".join(self.row(p) for p in items)}</section>')
        n = len(self.posts)
        body = (f'<div class="wrap page narrow"><header class="page-head"><h1>Archiwum</h1>'
                f'<p>{n} {plural(n, "wpis", "wpisy", "wpisów")} ze wszystkich wydań.</p></header>'
                f'{"".join(out) or "<p class=empty>Jeszcze nic tu nie ma.</p>"}</div>')
        return self.layout(title="Archiwum", body=body, path="/archiwum/")

    def render_search(self) -> str:
        body = (f'<div class="wrap page narrow"><header class="page-head"><h1>Szukaj</h1></header>'
                f'<div class="search" data-search data-index="{self.u("/search.json")}">'
                f'<label class="sr-only" for="q">Czego szukasz?</label>'
                f'<input id="q" type="search" placeholder="np. Temu, OrcaSlicer, elektryki" autocomplete="off" autofocus>'
                f'<div class="list" data-results aria-live="polite"></div></div></div>')
        return self.layout(title="Szukaj", body=body, path="/szukaj/", current="search")

    def render_page(self, source: Path, path: str) -> str:
        meta, text = read_document(source)
        title = _text(meta, "title", source.name, True)
        body = (f'<div class="wrap page narrow"><header class="page-head"><h1>{esc(title)}</h1></header>'
                f'<div class="prose">{markdown(text)}</div></div>')
        return self.layout(title=title, body=body, path=path, description=_text(meta, "lead", source.name))

    def render_404(self) -> str:
        body = (f'<div class="wrap page narrow"><header class="page-head"><h1>Nie ma takiej strony</h1>'
                f'<p>Wróć do <a href="{self.u("/")}">dzisiejszego wydania</a> albo zajrzyj do '
                f'<a href="{self.u("/archiwum/")}">archiwum</a>.</p></header></div>')
        doc = self.layout(title="Nie ma takiej strony", body=body, path="/404.html")
        self.pages.remove("/404.html")
        return doc

    def render_search_index(self) -> str:
        return json.dumps([{"t": p["title"], "l": p["lead"], "c": p["category"]["name"],
                            "d": date_short(p["date"]), "u": self.post_url(p), "s": p["slug"],
                            "m": f"{sources_short(len(p['sources']))}, {p['minutes']} min"}
                           for p in self.posts], ensure_ascii=False)

    def render_feed(self) -> str:
        items = []
        for p in self.posts[:50]:
            link = self.absolute(f"/p/{p['slug']}/")
            items.append(
                "<item>"
                f"<title>{esc(p['title'])}</title>"
                f"<link>{esc(link)}</link><guid isPermaLink=\"true\">{esc(link)}</guid>"
                f"<pubDate>{format_datetime(_aware(p['date']))}</pubDate>"
                f"<category>{esc(p['category']['name'])}</category>"
                f"<description>{esc(p['lead'])}</description>"
                "</item>")
        last = format_datetime(_aware(self.posts[0]["date"])) if self.posts else ""
        return ('<?xml version="1.0" encoding="utf-8"?>\n'
                '<rss version="2.0"><channel>'
                f"<title>{esc(self.c['title'])}</title>"
                f"<link>{esc(self.absolute('/'))}</link>"
                f"<description>{esc(self.c['description'])}</description>"
                "<language>pl</language>"
                f"<lastBuildDate>{last}</lastBuildDate>"
                f"{''.join(items)}</channel></rss>\n")

    def render_sitemap(self) -> str:
        urls = "".join(f"<url><loc>{esc(self.absolute(path))}</loc></url>" for path in self.pages)
        return ('<?xml version="1.0" encoding="utf-8"?>\n'
                f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')

    # ---------- zapis

    def build(self, out: Path) -> None:
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)

        def write(rel: str, text: str) -> None:
            target = out / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")

        write("index.html", self.render_home())
        for p in self.posts:
            write(f"p/{p['slug']}/index.html", self.render_post(p))
        for cat in self.topics["categories"]:
            write(f"kategoria/{cat['slug']}/index.html", self.render_category(cat))
        write("tematy/index.html", self.render_topics())
        write("archiwum/index.html", self.render_archive())
        write("szukaj/index.html", self.render_search())
        write("o-swan/index.html", self.render_page(CONTENT / "pages" / "o-swan.md", "/o-swan/"))
        write("404.html", self.render_404())
        write("search.json", self.render_search_index())
        write("feed.xml", self.render_feed())
        write("sitemap.xml", self.render_sitemap())
        write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {self.absolute('/sitemap.xml')}\n")
        for item in STATIC.iterdir():
            if item.is_file():
                shutil.copy2(item, out / item.name)


def _aware(value: dt.datetime) -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return value.replace(tzinfo=ZoneInfo("Europe/Warsaw"))
    except Exception:  # brak bazy stref czasowych
        return value.replace(tzinfo=dt.timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Buduje stronę magazynu do katalogu dist/.")
    parser.add_argument("--base", help="prefiks ścieżek, np. /swan albo pusty dla własnej domeny")
    parser.add_argument("--site-url", help="pełny adres strony, np. https://en6ri.github.io/swan")
    parser.add_argument("--posts-dir", default=str(CONTENT / "posts"), help="katalog z wpisami")
    parser.add_argument("--out", default=str(ROOT / "dist"), help="katalog wynikowy")
    args = parser.parse_args()

    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    base = config.get("base_path", "") if args.base is None else args.base
    site_url = args.site_url or config["site_url"]
    try:
        site = Site(config, base, site_url, Path(args.posts_dir))
        site.build(Path(args.out))
    except BuildError as error:
        print(f"BŁĄD: {error}", file=sys.stderr)
        sys.exit(1)
    count = len(site.posts)
    print(f"Gotowe: {count} {plural(count, 'wpis', 'wpisy', 'wpisów')} → {args.out}")


if __name__ == "__main__":
    main()
