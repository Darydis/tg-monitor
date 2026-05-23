"""Повторная простановка тегов с эмпирическим поиском лимита.

Telegram API не всегда даёт явный лимит для медиа — иногда Premium до 2048,
иногда выше. Скрипт пробует добавить все теги, при ошибке убирает последний
и пробует ещё раз. Никаких предположений о лимите.

Использование:
    python retry_failed_tags.py <csv> <failed_ids.txt> [--apply] [--throttle SECONDS]
"""

import asyncio
import argparse
import csv
import datetime
import sys
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import FloodWaitError, MediaCaptionTooLongError


sys.path.insert(0, str(Path(__file__).resolve().parent))
import config


def read_plan(csv_path: Path) -> dict[int, list[str]]:
    plan: dict[int, list[str]] = {}
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tags_raw = (row.get("tags") or "").strip()
            if not tags_raw:
                continue
            tags = [t.strip() for t in tags_raw.split(";") if t.strip()]
            plan[int(row["post_id"])] = tags
    return plan


async def try_edit(client, channel, post_id, original, missing_tags, entities, log) -> tuple[str, int]:
    """Пробует добавить теги, при ошибке откатывает по одному с конца."""
    for n in range(len(missing_tags), 0, -1):
        candidate = missing_tags[:n]
        new_text = original.rstrip() + "\n\n" + " ".join(candidate)
        try:
            await client.edit_message(channel, post_id, new_text, formatting_entities=entities)
            if n < len(missing_tags):
                dropped = missing_tags[n:]
                log(f"[{post_id}] OK PARTIAL: +{' '.join(candidate)}, не влезли {dropped}")
                return "partial", n
            log(f"[{post_id}] OK: +{' '.join(candidate)} (было {len(original)} → {len(new_text)})")
            return "ok", n
        except MediaCaptionTooLongError:
            continue
        except FloodWaitError as e:
            log(f"[{post_id}] FLOOD {e.seconds}с — жду")
            await asyncio.sleep(e.seconds + 1)
            try:
                await client.edit_message(channel, post_id, new_text, formatting_entities=entities)
                log(f"[{post_id}] OK после ожидания")
                return "ok_retry", n
            except MediaCaptionTooLongError:
                continue
    log(f"[{post_id}] SKIP: даже один тег не помещается (текст {len(original)})")
    return "no_room", 0


async def process_post(client, channel, post_id: int, tags: list[str], backup_dir: Path, log):
    msg = await client.get_messages(channel, ids=post_id)
    if msg is None:
        log(f"[{post_id}] SKIP: не найден")
        return "missing", 0
    if msg.action is not None:
        log(f"[{post_id}] SKIP: служебный")
        return "service", 0
    original = msg.message or ""
    if not original:
        log(f"[{post_id}] SKIP: пустой текст")
        return "empty", 0

    missing = [t for t in tags if t not in original]
    if not missing:
        log(f"[{post_id}] SKIP: уже все теги")
        return "already", 0

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    (backup_dir / f"{post_id}_{ts}.txt").write_text(original, encoding="utf-8")
    return await try_edit(client, channel, post_id, original, missing, msg.entities, log)


async def main(csv_path: Path, ids_path: Path, apply: bool, throttle: float):
    config.require()
    plan = read_plan(csv_path)
    ids = [int(x.strip()) for x in ids_path.read_text().splitlines() if x.strip()]
    print(f"Retry: {len(ids)} постов")

    if not apply:
        print("DRY RUN — ничего не отправлено. Запусти с --apply.")
        return

    backup_dir = Path(__file__).resolve().parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    log_path = Path(__file__).resolve().parent / f"retry_{datetime.datetime.now():%Y%m%d_%H%M%S}.log"
    log_f = log_path.open("w", encoding="utf-8")

    def log(msg: str) -> None:
        print(msg)
        log_f.write(msg + "\n")
        log_f.flush()

    log(f"Лог: {log_path}")
    stats: dict[str, int] = {}
    total_tags = 0
    async with TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH) as client:
        for i, post_id in enumerate(ids, 1):
            tags = plan.get(post_id, [])
            if not tags:
                continue
            log(f"\n--- [{i}/{len(ids)}] post {post_id}, tags={tags} ---")
            try:
                status, added = await process_post(client, config.CHANNEL, post_id, tags, backup_dir, log)
                total_tags += added
            except Exception as e:
                log(f"[{post_id}] ERROR: {type(e).__name__}: {e}")
                status = "error"
            stats[status] = stats.get(status, 0) + 1
            if i < len(ids):
                await asyncio.sleep(throttle)

    log("\n=== ИТОГ ===")
    for k, v in sorted(stats.items()):
        log(f"  {k}: {v}")
    log(f"  всего тегов добавлено: {total_tags}")
    log_f.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv", type=Path)
    p.add_argument("ids", type=Path)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--throttle", type=float, default=2.0)
    args = p.parse_args()
    asyncio.run(main(args.csv, args.ids, args.apply, args.throttle))
