#!/usr/bin/env python3
"""Собирает ближайшие забеги из нескольких источников и пишет events.json.
Запуск: python scraper.py   (раз в сутки — через GitHub Actions)"""
import json, re, sys, datetime as dt
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
OUT, MANUAL = ROOT / "events.json", ROOT / "manual.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; run-calendar-bot/1.0)"}
MSK = dt.timezone(dt.timedelta(hours=3))

# Источники. kind: begaem — свой парсер; jsonld — любой сайт со schema.org/Event
SOURCES = [
    {"kind": "begaem", "url": "https://begaem.com/blizhayshie-startyi-v-rossii/"},
    {"kind": "jsonld", "url": "https://www.kp.ru/afisha/spb/sport/zabegi-v-sankt-peterburge/"},
]

MONTHS = "январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь"
DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
MONTH_RE = re.compile(rf"^({MONTHS})\s+\d{{4}}$", re.I)
LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)")


def fetch(url):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def parse_begaem(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    for a in soup.find_all("a", href=True):  # ссылки -> [текст](url), чтобы не потерять href
        a.replace_with(f"[{a.get_text(' ', strip=True)}]({a['href']})")
    lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]
    idx = [i for i, l in enumerate(lines) if DATE_RE.match(l)]
    out = []
    for n, i in enumerate(idx):
        end = idx[n + 1] if n + 1 < len(idx) else len(lines)
        blk = []
        for l in lines[i + 1:end]:
            if MONTH_RE.match(l) or l.startswith("---"):
                break
            blk.append(l)
        if len(blk) < 2:
            continue
        d, m, y = DATE_RE.match(lines[i]).groups()
        links = [(t, u) for l in blk for t, u in LINK_RE.findall(l)]
        official = next((u for t, u in links if "begaem.com" not in u), "")
        detail = next((u for t, u in links if "begaem.com" in u), "")
        text = [l for l in blk[2:] if not LINK_RE.search(l) and "Официальный сайт" not in l]
        dist = next((l for l in text if re.search(r"\d\s*км|миля|детск|уточн", l, re.I)), "")
        out.append({"date": f"{y}-{m}-{d}", "name": blk[0], "city": blk[1],
                    "distances": dist.replace(" / ", " · "), "url": official or detail,
                    "official": bool(official), "source": "begaem"})
    return out


def _walk(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from _walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk(v)


def parse_jsonld(html, page_url=""):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except ValueError:
            continue
        for o in _walk(data):
            sd, name = str(o.get("startDate", ""))[:10], o.get("name")
            if not (re.match(r"\d{4}-\d{2}-\d{2}$", sd) and isinstance(name, str)):
                continue
            loc = o.get("location") or {}
            city = loc.get("name", "") if isinstance(loc, dict) else str(loc)
            out.append({"date": sd, "name": name.strip(), "city": city, "distances": "",
                        "url": o.get("url") or page_url, "official": False, "source": "jsonld"})
    return out


def norm(s):
    return re.sub(r"[^0-9a-zа-яё]", "", s.lower().replace("ё", "е"))


def merge(groups, today):
    """groups — списки событий по убыванию приоритета. Дубли (дата + похожее название) склеиваются."""
    res = []
    for g in groups:
        for e in g:
            if e["date"] < today:
                continue
            k = norm(e["name"])
            dup = next((r for r in res if r["date"] == e["date"]
                        and (norm(r["name"]) in k or k in norm(r["name"]))), None)
            if not dup:
                res.append(dict(e))
                continue
            for f in ("distances", "city"):  # дополняем пустые поля
                dup[f] = dup[f] or e[f]
            if e["official"] and not dup["official"]:  # официальная ссылка важнее агрегатора
                dup["url"], dup["official"] = e["url"], True
    return sorted(res, key=lambda r: (r["date"], r["name"]))


def main():
    today = dt.datetime.now(MSK).date().isoformat()
    manual = json.loads(MANUAL.read_text("utf-8")) if MANUAL.exists() else []
    scraped, ok = [], 0
    for s in SOURCES:
        try:
            html = fetch(s["url"])
            ev = parse_begaem(html) if s["kind"] == "begaem" else parse_jsonld(html, s["url"])
            print(f"{s['url']}: {len(ev)} событий")
            ok += bool(ev)
            scraped.append(ev)
        except Exception as ex:
            print(f"ОШИБКА {s['url']}: {ex}", file=sys.stderr)
    if not ok:
        print("Ни один источник не дал данных — events.json не обновляю", file=sys.stderr)
        sys.exit(1)
    events = merge([manual, *scraped], today)
    OUT.write_text(json.dumps({"updated_at": dt.datetime.now(MSK).isoformat(timespec="minutes"),
                               "count": len(events), "events": events}, ensure_ascii=False, indent=1), "utf-8")
    print(f"Записано {len(events)} забегов")


if __name__ == "__main__":
    main()
