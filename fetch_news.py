#!/usr/bin/env python3
"""Забирает последние новости с dulaty.edu.kz и пишет их в news.json.

Запускается в GitHub Actions раз в час. Если страница не распарсилась
(0 новостей), скрипт падает с ошибкой, и старый news.json остаётся как есть.
"""
import json
import re
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

LIST_URL = "https://dulaty.edu.kz/index.php/ru/biz-turaly/medya/zhanalykhtar"
LINK_PART = "/medya/zhanalykhtar/"      # у статей после этого есть slug
LIMIT = 12
SUMMARY_LEN = 220
UA = "Mozilla/5.0 (compatible; student-communities-news/1.0)"

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
DATE_RE = re.compile(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4})\b")
IMG_RE = re.compile(r"/images/news/")


def fix_title(t: str) -> str:
    """Заголовки на сайте ПРОПИСНЫМИ: делаем обычный регистр (имена станут строчными)."""
    t = " ".join(t.split())
    return t[:1] + t[1:].lower() if t.isupper() else t


def summary_after(a, limit=SUMMARY_LEN) -> str:
    """Текст между заголовком и датой новости."""
    parts = []
    for s in a.find_all_next(string=True):
        if a in s.parents:
            continue                      # сам заголовок
        text = " ".join(str(s).split())
        if not text:
            continue
        if DATE_RE.search(text):
            break                         # дошли до даты: новость кончилась
        parts.append(text)
        if sum(len(p) for p in parts) > limit * 2:
            break
    out = " ".join(parts)
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0] + "…"
    return out


def main() -> None:
    r = requests.get(LIST_URL, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        url = urljoin(LIST_URL, a["href"]).split("#")[0]
        title = fix_title(a.get_text(" ", strip=True))
        if LINK_PART not in url or url in seen or not title:
            continue
        seen.add(url)

        img = a.find_previous("img", src=IMG_RE)
        image = urljoin(LIST_URL, img["src"]).replace(" ", "%20") if img else None

        date_iso = date_label = None
        node = a.find_next(string=DATE_RE)
        if node:
            d, month, y = DATE_RE.search(node).groups()
            date_label = f"{int(d)} {month} {y}"
            date_iso = f"{y}-{MONTHS[month]:02d}-{int(d):02d}"

        items.append({
            "title": title,
            "url": url,
            "image": image,
            "date": date_iso,
            "date_label": date_label,
            "summary": summary_after(a),
        })
        if len(items) >= LIMIT:
            break

    if not items:
        sys.exit("Новости не найдены: вёрстка сайта, видимо, изменилась")

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump({"source": LIST_URL, "items": items}, f, ensure_ascii=False, indent=2)
    print(f"OK: {len(items)} новостей")


if __name__ == "__main__":
    main()
