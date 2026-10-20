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


WORD_RE = re.compile(r"[^\W\d_]+")      # слова из букв (любой алфавит)


def proper_words(text: str) -> set:
    """Слова, которые в тексте новости стоят с заглавной НЕ в начале предложения
    (имена, названия): по ним восстанавливаем регистр в заголовке."""
    found = set()
    for m in WORD_RE.finditer(text):
        w = m.group(0)
        if len(w) < 3 or not w[0].isupper() or w.isupper():
            continue
        before = text[:m.start()].rstrip()
        if not before or (before[-1] in ".!?…" and not re.search(r"\b\w\.$", before)):
            continue                              # начало предложения (инициалы «М.Х.» не считаем)
        found.add(w.lower())
    return found


def fix_title(t: str, body: str = "") -> str:
    """Заголовки на сайте ПРОПИСНЫМИ: делаем обычный регистр, а имена, названия
    в «кавычках» и слова, которые в тексте новости пишутся с заглавной, оставляем заглавными."""
    t = " ".join(t.split())
    if not t.isupper():
        return t
    low = t.lower()
    quoted = [(m.start(), m.end()) for m in re.finditer(r"«[^»]*»", low)]
    proper = proper_words(body)

    def conv(m):
        w = m.group(0)
        in_quotes = any(a <= m.start() < b for a, b in quoted)
        initial = len(w) == 1 and low[m.end():m.end() + 1] == "."   # инициалы: м.х. -> М.Х.
        if in_quotes or initial or w in proper:
            return w.capitalize()
        return w

    out = WORD_RE.sub(conv, low)
    for i, ch in enumerate(out):                  # первая буква заголовка — заглавная
        if ch.isalpha():
            out = out[:i] + ch.upper() + out[i + 1:]
            break
    return out


def body_after(a, cap=2500) -> str:
    """Текст между заголовком и датой новости (целиком, до cap символов)."""
    parts, total = [], 0
    for s in a.find_all_next(string=True):
        if a in s.parents:
            continue                      # сам заголовок
        text = " ".join(str(s).split())
        if not text:
            continue
        if DATE_RE.search(text):
            break                         # дошли до даты: новость кончилась
        parts.append(text)
        total += len(text)
        if total > cap:
            break
    return " ".join(parts)


def trim(text: str, limit=SUMMARY_LEN) -> str:
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def main() -> None:
    r = requests.get(LIST_URL, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        url = urljoin(LIST_URL, a["href"]).split("#")[0]
        raw_title = " ".join(a.get_text(" ", strip=True).split())
        if LINK_PART not in url or url in seen or not raw_title:
            continue
        seen.add(url)
        body = body_after(a)
        title = fix_title(raw_title, body)

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
            "summary": trim(body),
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
