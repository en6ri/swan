#!/usr/bin/env python3
"""SWAN: generator statycznej strony magazynu (bez zależności, Python 3.9+).

Użycie:
    python3 build.py                                          # ustawienia z config.json
    python3 build.py --base "" --site-url http://localhost:8000   # podgląd lokalny

Wpisy leżą w content/posts/*.md, format opisuje README.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
STATIC = ROOT / "static"
HOME_EDITIONS = 8  # ile wydań (dni) pokazać na stronie głównej
HOME_SHORTS = 20

MONTHS = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
          "sierpnia", "września", "października", "listopada", "grudnia"]
MONTHS_NOM = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec",
              "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
MONTHS_SHORT = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]
WEEKDAYS = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]

FORMATS = {"article": "Artykuł", "thread": "Wątek", "short": "Krótko"}
CONFIDENCE = {
    "confirmed": ("Potwierdzone",
                  "Potwierdzone w co najmniej dwóch niezależnych źródłach albo w źródle pierwotnym."),
    "single-source": ("Jedno źródło",
                      "Pochodzi z jednego wiarygodnego źródła, bez niezależnego potwierdzenia."),
    "unconfirmed": ("Niepotwierdzone",
                    "Przecieki, plotki albo doniesienia. Warto wiedzieć, ale traktuj z dystansem."),
}

LOGO = (
    '<svg class="logo" viewBox="0 0 64 64" aria-hidden="true" focusable="false">'
    '<path class="logo-beak" d="M13.5 14.5 4 19.5l10.5-.5z"/>'
    '<path class="logo-neck" d="M15 17c3-8 15-8 15 1 0 9-14 14-14 26" fill="none" stroke-width="5.5" stroke-linecap="round"/>'
    '<path class="logo-body" d="M13 42c2 9 13 13 26 11 10-1.5 17-8 20-18-6 4-12 5-18 3-9-3-19 0-28 4z"/>'
    '</svg>'
)


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- pomocnicze

def esc(value) -> str:
    return html.escape(str(value), quote=True)


_PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def slugify(text: str) -> str:
    text = text.translate(_PL).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "temat"


def plural(n: int, one: str, few: str, many: str) -> str:
    if n == 1:
        return one
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return few
    return many


def date_long(d) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def date_short(d) -> str:
    return f"{d.day} {MONTHS_SHORT[d.month - 1]}"


def weekday(d) -> str:
    return WEEKDAYS[d.weekday()]


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:–—-") + "…"


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


# ---------------------------------------------------------------- wpisy

_FRONT = re.compile(r"\A---\n(.*?)\n---[ \t]*(?:\n(.*))?\Z", re.S)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def read_document(path: Path):
    text = path.read_text(encoding="utf-8").lstrip("﻿").replace("\r\n", "\n")
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


def _parse_date(value: str, name: str) -> dt.datetime:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value.strip(), fmt)
        except ValueError:
            pass
    raise BuildError(f"{name}: data {value!r} musi mieć postać RRRR-MM-DD albo RRRR-MM-DD GG:MM")


def _parse_source(raw: str, name: str) -> dict:
    if "|" in raw:
        label, url = (part.strip() for part in raw.rsplit("|", 1))
    else:
        url = raw.strip()
        label = ""
    if not re.match(r"^https?://\S+$", url):
        raise BuildError(f"{name}: źródło {raw!r} musi kończyć się adresem http(s)://")
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    return {"name": label or host, "url": url, "host": host}


def _text_field(meta: dict, key: str, name: str, required: bool = False) -> str:
    value = meta.get(key, "")
    if isinstance(value, list):
        raise BuildError(f"{name}: pole '{key}' powinno być jedną linijką tekstu")
    if required and not value.strip():
        raise BuildError(f"{name}: brak wymaganego pola '{key}'")
    return value.strip()


def load_posts(folder: Path) -> list:
    posts = []
    for path in sorted(folder.glob("*.md")):
        name = path.name
        meta, body = read_document(path)
        if str(meta.get("draft", "")).lower() in ("true", "tak", "yes"):
            continue
        if not re.fullmatch(r"[a-z0-9-]+", path.stem):
            raise BuildError(f"{name}: nazwa pliku może zawierać tylko małe litery, cyfry i myślniki")
        title = _text_field(meta, "title", name, True)
        topic = _text_field(meta, "topic", name, True)
        fmt = _text_field(meta, "format", name, True)
        if fmt not in FORMATS:
            raise BuildError(f"{name}: format musi być jednym z: {', '.join(FORMATS)}")
        conf = _text_field(meta, "confidence", name) or None
        if conf and conf not in CONFIDENCE:
            raise BuildError(f"{name}: confidence musi być jednym z: {', '.join(CONFIDENCE)}")
        raw_sources = meta.get("sources", [])
        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]
        sources = [_parse_source(s, name) for s in raw_sources]
        if conf and not sources:
            raise BuildError(f"{name}: wpis z oceną pewności musi mieć co najmniej jedno źródło")
        if not body.strip():
            raise BuildError(f"{name}: wpis nie ma treści")
        post = {
            "slug": path.stem,
            "title": title,
            "date": _parse_date(_text_field(meta, "date", name, True), name),
            "topic": topic,
            "topic_slug": slugify(topic),
            "format": fmt,
            "confidence": conf,
            "lead": _text_field(meta, "lead", name),
            "sources": sources,
            "plain": plain_text(body),
            "words": len(re.findall(r"\w+", body)),
        }
        if fmt == "thread":
            parts = [p.strip() for p in re.split(r"(?m)^\s*---\s*$", body) if p.strip()]
            post["parts"] = [markdown(p) for p in parts]
        else:
            post["html"] = markdown(body)
        posts.append(post)
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)
    return posts


# ---------------------------------------------------------------- strona

class Site:
    def __init__(self, config: dict, base: str, site_url: str, posts_dir: Path):
        self.c = config
        self.base = base.rstrip("/")
        self.site_url = site_url.rstrip("/")
        self.posts = load_posts(posts_dir)
        counts, names = {}, {}
        for p in self.posts:
            counts[p["topic_slug"]] = counts.get(p["topic_slug"], 0) + 1
            names.setdefault(p["topic_slug"], p["topic"])
        self.topics = sorted(((s, names[s], n) for s, n in counts.items()), key=lambda t: (-t[2], t[1]))
        days = sorted({p["date"].date() for p in self.posts})
        self.edition = {d: i + 1 for i, d in enumerate(days)}
        self.css_version = hashlib.sha1((STATIC / "style.css").read_bytes()).hexdigest()[:8]
        self.pages = []  # ścieżki do sitemap.xml

    def u(self, path: str) -> str:
        return self.base + path

    def absolute(self, path: str) -> str:
        return self.site_url + path

    def post_url(self, p: dict) -> str:
        return self.u(f"/p/{p['slug']}/")

    def topic_url(self, slug: str) -> str:
        return self.u(f"/tematy/{slug}/")

    # ---------- szkielet

    def layout(self, *, title: str, body: str, path: str, description: str = "",
               home: bool = False, kind: str = "website", current: str = "") -> str:
        c = self.c
        full_title = title if home else f"{title} · {c['title']}"
        desc = description or c["description"]
        nav = [f'<a href="{self.u("/")}"{" aria-current=page" if current == "home" else ""}>Wszystko</a>']
        for slug, name, _ in self.topics:
            mark = " aria-current=page" if current == slug else ""
            nav.append(f'<a href="{self.topic_url(slug)}"{mark}>{esc(name)}</a>')
        about = " aria-current=page" if current == "about" else ""
        nav.append(f'<a class="topnav-about" href="{self.u("/o-magazynie/")}"{about}>O magazynie</a>')

        if home and self.posts:
            latest = self.posts[0]["date"].date()
            dateline = (f'<p class="dateline"><span>{weekday(latest).capitalize()}, {date_long(latest)}</span>'
                        f'<span>Wydanie nr {self.edition[latest]}</span></p>')
        else:
            dateline = ""
        masthead_class = "masthead--home" if home else "masthead--inner"
        self.pages.append(path)
        return f"""<!doctype html>
<html lang="{esc(c.get('language', 'pl'))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(self.absolute(path))}">
<link rel="icon" href="{self.u('/favicon.svg')}" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{esc(c['title'])}" href="{self.u('/feed.xml')}">
<link rel="stylesheet" href="{self.u('/style.css')}?v={self.css_version}">
<meta name="theme-color" content="#f8f5ef" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#141311" media="(prefers-color-scheme: dark)">
<meta property="og:site_name" content="{esc(c['title'])}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="{kind}">
<meta property="og:url" content="{esc(self.absolute(path))}">
<meta property="og:locale" content="pl_PL">
</head>
<body>
<a class="skip" href="#tresc">Przejdź do treści</a>
<header class="masthead {masthead_class}">
  <div class="wrap masthead-inner">
    <a class="brand" href="{self.u('/')}" aria-label="{esc(c['title'])}, strona główna">{LOGO}<span class="brand-name">{esc(c['title'])}</span></a>
    <p class="tagline">{esc(c['tagline'])}</p>
    {dateline}
  </div>
</header>
<nav class="topnav" aria-label="Działy"><div class="wrap topnav-inner">{''.join(nav)}</div></nav>
<main id="tresc">
{body}
</main>
<footer class="site-footer">
  <div class="wrap">
    <p><strong>{esc(c['title'])}</strong> to magazyn redagowany przez AI (Claude). Teksty mogą zawierać błędy, dlatego przy każdym wpisie są źródła i ocena pewności. W razie rozbieżności rację ma źródło.</p>
    <p><a href="{self.u('/o-magazynie/')}">Jak to działa</a> · <a href="{self.u('/archiwum/')}">Archiwum</a> · <a href="{self.u('/feed.xml')}">RSS</a></p>
  </div>
</footer>
</body>
</html>
"""

    # ---------- klocki

    def badge(self, conf) -> str:
        if not conf:
            return ""
        label, note = CONFIDENCE[conf]
        return f'<span class="badge badge--{conf}" title="{esc(note)}">{label}</span>'

    def format_label(self, p: dict) -> str:
        if p["format"] == "article":
            return f"Artykuł · {max(1, round(p['words'] / 200))} min"
        if p["format"] == "thread":
            n = len(p["parts"])
            return f"Wątek · {n} {plural(n, 'część', 'części', 'części')}"
        return "Krótko"

    def kicker(self, p: dict) -> str:
        return (f'<div class="kicker"><a class="topic" href="{self.topic_url(p["topic_slug"])}">{esc(p["topic"])}</a>'
                f'<span class="fmt">{self.format_label(p)}</span></div>')

    def meta_line(self, p: dict, show_date: bool = True) -> str:
        bits = []
        if show_date:
            bits.append(f'<time datetime="{p["date"].date().isoformat()}">{date_long(p["date"])}</time>')
        if p["confidence"]:
            bits.append(self.badge(p["confidence"]))
        n = len(p["sources"])
        if n:
            bits.append(f"<span>{n} {plural(n, 'źródło', 'źródła', 'źródeł')}</span>")
        if not bits:
            return ""
        return '<div class="meta">' + '<span class="sep" aria-hidden="true">·</span>'.join(bits) + "</div>"

    def summary(self, p: dict, limit: int = 220) -> str:
        return p["lead"] or truncate(p["plain"], limit)

    def card(self, p: dict, size: str = "md", show_date: bool = True, heading: str = "h3") -> str:
        return (f'<article class="card card--{size} card--{p["format"]}">{self.kicker(p)}'
                f'<{heading} class="card-title"><a href="{self.post_url(p)}">{esc(p["title"])}</a></{heading}>'
                f'<p class="card-lead">{esc(self.summary(p))}</p>{self.meta_line(p, show_date)}</article>')

    def short_card(self, p: dict, heading: str = "h3") -> str:
        foot = [self.badge(p["confidence"])] if p["confidence"] else []
        if p["sources"]:
            s = p["sources"][0]
            more = len(p["sources"]) - 1
            extra = f' <span class="more">+{more}</span>' if more else ""
            foot.append(f'<span class="src">Źródło: <a href="{esc(s["url"])}" rel="noopener" target="_blank">'
                        f'{esc(s["name"])}</a>{extra}</span>')
        foot_html = f'<div class="short-foot">{"".join(foot)}</div>' if foot else ""
        return (f'<article class="short"><div class="short-head">'
                f'<a class="topic" href="{self.topic_url(p["topic_slug"])}">{esc(p["topic"])}</a>'
                f'<a class="short-time" href="{self.post_url(p)}" title="Link do wpisu">'
                f'<time datetime="{p["date"].isoformat()}">{date_short(p["date"])}</time></a></div>'
                f'<{heading} class="short-title"><a href="{self.post_url(p)}">{esc(p["title"])}</a></{heading}>'
                f'<div class="short-body">{p["html"]}</div>{foot_html}</article>')

    def any_card(self, p: dict) -> str:
        return self.short_card(p) if p["format"] == "short" else self.card(p)

    # ---------- strony

    def render_home(self) -> str:
        longs = [p for p in self.posts if p["format"] != "short"]
        shorts = [p for p in self.posts if p["format"] == "short"][:HOME_SHORTS]
        groups = []
        for p in longs:
            day = p["date"].date()
            if groups and groups[-1][0] == day:
                groups[-1][1].append(p)
            else:
                groups.append((day, [p]))

        main = []
        if groups:
            day, items = groups[0]
            # czołówka: najnowszy artykuł z wydania, a jeśli go nie ma, najnowszy wpis
            top = next((p for p in items if p["format"] == "article"), items[0])
            items = [top] + [p for p in items if p is not top]
            main.append(f'<section class="edition" aria-labelledby="wydanie"><h2 class="section-title" id="wydanie">'
                        f'Najnowsze · {date_long(day)}</h2>')
            main.append(self.card(items[0], "lg", show_date=False))
            if items[1:]:
                main.append('<div class="card-grid">' +
                            "".join(self.card(p, "md", show_date=False) for p in items[1:]) + "</div>")
            main.append("</section>")
            older = groups[1:HOME_EDITIONS]
            if older:
                main.append('<section class="older" aria-labelledby="wczesniej">'
                            '<h2 class="section-title" id="wczesniej">Wcześniejsze wydania</h2>')
                for day, items in older:
                    rows = "".join(
                        f'<li><span class="fmt-chip">{FORMATS[p["format"]]}</span>'
                        f'<a href="{self.post_url(p)}">{esc(p["title"])}</a>'
                        f'<span class="older-topic">{esc(p["topic"])}</span></li>' for p in items)
                    main.append(f'<div class="older-day"><h3 class="older-date">{weekday(day).capitalize()}, '
                                f'{date_long(day)}</h3><ul class="older-list">{rows}</ul></div>')
                main.append(f'<p class="more-link"><a href="{self.u("/archiwum/")}">Całe archiwum →</a></p>'
                            "</section>")
        else:
            main.append('<p class="empty">Pierwsze wydanie jest w drodze.</p>')

        side = "".join(self.short_card(p) for p in shorts) or '<p class="empty">Tu pojawią się krótkie wpisy.</p>'
        body = (f'<h1 class="sr-only">{esc(self.c["title"])}: {esc(self.c["tagline"])}</h1>'
                f'<div class="wrap home"><div class="home-main">{"".join(main)}</div>'
                f'<aside class="home-side" aria-labelledby="krotko"><h2 class="section-title" id="krotko">Krótko</h2>'
                f'{side}</aside></div>')
        return self.layout(title=f"{self.c['title']}: {self.c['tagline']}", body=body, path="/",
                           home=True, current="home")

    def render_post(self, p: dict) -> str:
        if p["format"] == "thread":
            n = len(p["parts"])
            parts = "".join(f'<li class="thread-part"><span class="thread-n" aria-label="Część {i} z {n}">{i}/{n}</span>'
                            f'<div class="prose">{part}</div></li>' for i, part in enumerate(p["parts"], 1))
            content = f'<ol class="thread">{parts}</ol>'
        else:
            content = f'<div class="prose">{p["html"]}</div>'

        sources = ""
        if p["sources"]:
            items = "".join(f'<li><a href="{esc(s["url"])}" rel="noopener" target="_blank">{esc(s["name"])}</a>'
                            f' <span class="host">{esc(s["host"])}</span></li>' for s in p["sources"])
            conf = ""
            if p["confidence"]:
                conf = f'<p class="conf-note">{self.badge(p["confidence"])}<span>{esc(CONFIDENCE[p["confidence"]][1])}</span></p>'
            sources = f'<aside class="sources" aria-labelledby="zrodla"><h2 id="zrodla">Źródła</h2><ol>{items}</ol>{conf}</aside>'

        related = [q for q in self.posts if q["topic_slug"] == p["topic_slug"] and q["slug"] != p["slug"]][:4]
        related_html = ""
        if related:
            rows = "".join(f'<li><a href="{self.post_url(q)}">{esc(q["title"])}</a>'
                           f'<span class="meta-inline">{FORMATS[q["format"]]} · {date_short(q["date"])}</span></li>'
                           for q in related)
            related_html = (f'<nav class="related" aria-labelledby="wiecej"><h2 class="section-title" id="wiecej">'
                            f'Więcej: {esc(p["topic"])}</h2><ul>{rows}</ul></nav>')

        lead = f'<p class="lead">{esc(p["lead"])}</p>' if p["lead"] else ""
        meta = self.meta_line(p)
        if p["format"] == "article":
            meta = meta.replace("</div>", f'<span class="sep" aria-hidden="true">·</span>'
                                          f'<span>{max(1, round(p["words"] / 200))} min czytania</span></div>', 1) \
                if meta else ""
        ai_note = ('<p class="ai-note">Tekst przygotowany przez AI (Claude) na podstawie podanych źródeł.</p>'
                   if p["sources"] else "")
        body = (f'<div class="wrap"><article class="post post--{p["format"]}">'
                f'<header class="post-head"><div class="kicker"><a class="topic" href="{self.topic_url(p["topic_slug"])}">'
                f'{esc(p["topic"])}</a><span class="fmt">{FORMATS[p["format"]]}</span></div>'
                f'<h1>{esc(p["title"])}</h1>{lead}{meta}</header>'
                f'{content}{sources}{ai_note}{related_html}</article></div>')
        return self.layout(title=p["title"], body=body, path=f"/p/{p['slug']}/",
                           description=self.summary(p, 200), kind="article")

    def render_topic(self, slug: str, name: str, count: int) -> str:
        items = [p for p in self.posts if p["topic_slug"] == slug]
        body = (f'<div class="wrap"><header class="page-head"><h1>{esc(name)}</h1>'
                f'<p>{count} {plural(count, "wpis", "wpisy", "wpisów")}</p></header>'
                f'<div class="feed">{"".join(self.any_card(p) for p in items)}</div></div>')
        return self.layout(title=name, body=body, path=f"/tematy/{slug}/", current=slug,
                           description=f"Wszystkie wpisy z działu {name}.")

    def render_archive(self) -> str:
        months, out = [], []
        for p in self.posts:
            key = (p["date"].year, p["date"].month)
            if not months or months[-1][0] != key:
                months.append((key, []))
            months[-1][1].append(p)
        for (year, month), items in months:
            rows = "".join(f'<li><time datetime="{p["date"].date().isoformat()}">{date_short(p["date"])}</time>'
                           f'<span class="fmt-chip">{FORMATS[p["format"]]}</span>'
                           f'<a href="{self.post_url(p)}">{esc(p["title"])}</a>'
                           f'<span class="older-topic">{esc(p["topic"])}</span></li>' for p in items)
            out.append(f'<section class="archive-month"><h2 class="section-title">{MONTHS_NOM[month - 1]} {year}</h2>'
                       f'<ul class="older-list archive-list">{rows}</ul></section>')
        n = len(self.posts)
        body = (f'<div class="wrap"><header class="page-head"><h1>Archiwum</h1>'
                f'<p>{n} {plural(n, "wpis", "wpisy", "wpisów")}</p></header>'
                f'<div class="feed">{"".join(out) or "<p class=empty>Jeszcze nic tu nie ma.</p>"}</div></div>')
        return self.layout(title="Archiwum", body=body, path="/archiwum/")

    def render_page(self, source: Path, path: str, current: str = "") -> str:
        meta, text = read_document(source)
        title = _text_field(meta, "title", source.name, True)
        body = (f'<div class="wrap"><article class="post post--page"><header class="post-head"><h1>{esc(title)}</h1>'
                f'</header><div class="prose">{markdown(text)}</div></article></div>')
        return self.layout(title=title, body=body, path=path, current=current,
                           description=_text_field(meta, "lead", source.name))

    def render_404(self) -> str:
        body = (f'<div class="wrap"><header class="page-head page-404"><h1>Nie ma takiej strony</h1>'
                f'<p>Może wpis zmienił adres. <a href="{self.u("/")}">Wróć na stronę główną</a> '
                f'albo zajrzyj do <a href="{self.u("/archiwum/")}">archiwum</a>.</p></header></div>')
        html_doc = self.layout(title="Nie ma takiej strony", body=body, path="/404.html")
        self.pages.remove("/404.html")
        return html_doc

    def render_feed(self) -> str:
        items = []
        for p in self.posts[:40]:
            link = self.absolute(f"/p/{p['slug']}/")
            items.append(
                "<item>"
                f"<title>{esc(p['title'])}</title>"
                f"<link>{esc(link)}</link><guid isPermaLink=\"true\">{esc(link)}</guid>"
                f"<pubDate>{format_datetime(_aware(p['date']))}</pubDate>"
                f"<category>{esc(p['topic'])}</category>"
                f"<description>{esc(self.summary(p, 400))}</description>"
                "</item>")
        now = format_datetime(_aware(self.posts[0]["date"])) if self.posts else ""
        return ('<?xml version="1.0" encoding="utf-8"?>\n'
                '<rss version="2.0"><channel>'
                f"<title>{esc(self.c['title'])}</title>"
                f"<link>{esc(self.absolute('/'))}</link>"
                f"<description>{esc(self.c['description'])}</description>"
                f"<language>{esc(self.c.get('language', 'pl'))}</language>"
                f"<lastBuildDate>{now}</lastBuildDate>"
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
        for slug, name, count in self.topics:
            write(f"tematy/{slug}/index.html", self.render_topic(slug, name, count))
        write("archiwum/index.html", self.render_archive())
        write("o-magazynie/index.html", self.render_page(CONTENT / "pages" / "o-magazynie.md",
                                                         "/o-magazynie/", current="about"))
        write("404.html", self.render_404())
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
    np, nt = len(site.posts), len(site.topics)
    print(f"Gotowe: {np} {plural(np, 'wpis', 'wpisy', 'wpisów')}, "
          f"{nt} {plural(nt, 'dział', 'działy', 'działów')} → {args.out}")


if __name__ == "__main__":
    main()
