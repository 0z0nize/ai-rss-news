#!/usr/bin/env python3
"""
Читает RSS-ленты из feeds.txt, находит новые записи и дописывает их
в DIGEST.md. Уже виденные записи запоминаются в seen.json, поэтому
коммит происходит ТОЛЬКО при наличии новых статей (без пустых коммитов).

Зависимости: feedparser
    pip install feedparser
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent
FEEDS_FILE = ROOT / "feeds.txt"
DIGEST_FILE = ROOT / "DIGEST.md"
SEEN_FILE = ROOT / "seen.json"

# Максимум новых записей за один запуск (защита от «простыни» при первом старте)
MAX_NEW_PER_RUN = 12


def load_feeds() -> list[str]:
    if not FEEDS_FILE.exists():
        print(f"[!] Не найден {FEEDS_FILE}", file=sys.stderr)
        return []
    feeds = []
    for line in FEEDS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            feeds.append(line)
    return feeds


def load_seen() -> set[str]:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return set()
    return set()


def save_seen(seen: set[str]) -> None:
    # Храним последние 2000 идентификаторов, чтобы файл не рос бесконечно
    trimmed = list(seen)[-2000:]
    SEEN_FILE.write_text(json.dumps(trimmed, ensure_ascii=False, indent=0), encoding="utf-8")


def entry_id(entry) -> str:
    raw = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def collect_new(feeds: list[str], seen: set[str]) -> list[dict]:
    new_items = []
    for url in feeds:
        print(f"[*] Читаю: {url}")
        try:
            parsed = feedparser.parse(url)
        except Exception as exc:  # noqa: BLE001
            print(f"    [!] Ошибка: {exc}", file=sys.stderr)
            continue
        source = parsed.feed.get("title", url)
        for entry in parsed.entries:
            eid = entry_id(entry)
            if eid in seen:
                continue
            seen.add(eid)
            new_items.append(
                {
                    "title": entry.get("title", "(без названия)").strip(),
                    "link": entry.get("link", "").strip(),
                    "source": source,
                    "published": entry.get("published", entry.get("updated", "")),
                }
            )
    return new_items[:MAX_NEW_PER_RUN]


def prepend_to_digest(items: list[dict]) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = [f"\n## Обновление {now}\n"]
    for it in items:
        title = it["title"]
        link = it["link"]
        source = it["source"]
        line = f"- [{title}]({link}) — {source}" if link else f"- {title} — {source}"
        block.append(line)
    block_text = "\n".join(block) + "\n"

    header = "# RSS-дайджест\n\nАвтоматически обновляемая подборка статей по ML / NLP / Data Science.\n"
    if DIGEST_FILE.exists():
        existing = DIGEST_FILE.read_text(encoding="utf-8")
        if existing.startswith("# RSS-дайджест"):
            # Вставляем новый блок сразу после шапки
            parts = existing.split("\n", 4)
            rest = existing[len(header):] if existing.startswith(header) else existing
            DIGEST_FILE.write_text(header + block_text + rest, encoding="utf-8")
            return
    DIGEST_FILE.write_text(header + block_text, encoding="utf-8")


def main() -> int:
    feeds = load_feeds()
    if not feeds:
        print("[!] Нет лент для обработки.")
        return 0
    seen = load_seen()
    new_items = collect_new(feeds, seen)
    if not new_items:
        print("[=] Новых записей нет — коммита не будет.")
        return 0
    prepend_to_digest(new_items)
    save_seen(seen)
    print(f"[+] Добавлено новых записей: {len(new_items)}")
    # Для GitHub Action: пишем флаг в выходную переменную
    gha_out = os.environ.get("GITHUB_OUTPUT")
    if gha_out:
        with open(gha_out, "a", encoding="utf-8") as fh:
            fh.write(f"new_count={len(new_items)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
