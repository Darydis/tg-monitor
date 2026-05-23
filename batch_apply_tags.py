"""Батч-простановка хештегов из CSV.

CSV формат:
    post_id,tags
    2807,#политика;#размышления

Использование:
    python batch_apply_tags.py <csv> [--apply] [--throttle SECONDS] [--limit N]

Без --apply делается dry-run (показывает план, ничего не отправляет).
"""

import asyncio
import argparse
import csv
import datetime
import sys
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import FloodWaitError, MessageNotModifiedError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config


def read_plan(csv_path: Path) -> list[tuple[int, list[str]]]:
    plan = []
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tags_raw = (row.get("tags") or "").strip()
            if not tags_raw:
                continue
            tags = [t.strip() for t in tags_raw.split(";") if t.strip()]
            plan.append((int(row["post_id"]), tags))
    return plan


async def process_post(client, channel, post_id: int, tags: list[str], backup_dir: Path, log) -> str:
    msg = await client.get_messages(channel, ids=post_id)
    if msg is None:
        log(f"[{post_id}] SKIP: пост не найден")
        return "missing"
    if msg.action is not None:
        log(f"[{post_id}] SKIP: служебное сообщение")
        return "service"
    original = msg.message or ""
    if not original:
        log(f"[{post_id}] SKIP: пустой текст (вероятно медиа без подписи)")
        return "empty"

    missing = [t for t in tags if t not in original]
    if not missing:
        log(f"[{post_id}] SKIP: все теги уже есть")
        return "already"

    new_text = original.rstrip() + "\n\n" + " ".join(missing)
    if len(new_text) > 4096:
        log(f"[{post_id}] SKIP: длина >4096 ({len(new_text)})")
        return "too_long"

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"{post_id}_{ts}.txt"
    backup.write_text(original, encoding="utf-8")

    try:
        await client.edit_message(channel, post_id, new_text, formatting_entities=msg.entities)
        log(f"[{post_id}] OK: +{' '.join(missing)} (было {len(original)} → {len(new_text)})")
        return "ok"
    except MessageNotModifiedError:
        log(f"[{post_id}] SKIP: MessageNotModifiedError")
        return "not_modified"
    except FloodWaitError as e:
        log(f"[{post_id}] FLOOD WAIT {e.seconds}с — жду и пробую ещё раз")
        await asyncio.sleep(e.seconds + 1)
        await client.edit_message(channel, post_id, new_text, formatting_entities=msg.entities)
        log(f"[{post_id}] OK после ожидания")
        return "ok_retry"


async def main(csv_path: Path, apply: bool, throttle: float, limit: int | None) -> None:
    config.require()
    plan = read_plan(csv_path)
    if limit:
        plan = plan[:limit]
    print(f"План: {len(plan)} постов")
    tag_counts: dict[str, int] = {}
    for _, tags in plan:
        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    print("Теги, которые предполагается добавить:")
    for t, c in sorted(tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {c:4d}  {t}")

    if not apply:
        print("\nDRY RUN — ничего не отправлено. Запусти с --apply.")
        return

    backup_dir = Path(__file__).resolve().parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    log_path = Path(__file__).resolve().parent / f"batch_apply_{datetime.datetime.now():%Y%m%d_%H%M%S}.log"
    log_f = log_path.open("w", encoding="utf-8")

    def log(msg: str) -> None:
        print(msg)
        log_f.write(msg + "\n")
        log_f.flush()

    log(f"Лог: {log_path}")
    log(f"Бэкапы: {backup_dir}")
    log(f"Throttle: {throttle}с между постами")

    stats: dict[str, int] = {}
    async with TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH) as client:
        for i, (post_id, tags) in enumerate(plan, 1):
            log(f"\n--- [{i}/{len(plan)}] post {post_id}, tags={tags} ---")
            try:
                status = await process_post(client, config.CHANNEL, post_id, tags, backup_dir, log)
            except Exception as e:
                log(f"[{post_id}] ERROR: {type(e).__name__}: {e}")
                status = "error"
            stats[status] = stats.get(status, 0) + 1
            if i < len(plan):
                await asyncio.sleep(throttle)

    log("\n=== ИТОГ ===")
    for k, v in sorted(stats.items()):
        log(f"  {k}: {v}")
    log_f.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv", type=Path)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--throttle", type=float, default=2.0, help="пауза между постами, сек")
    p.add_argument("--limit", type=int, default=None, help="обработать только N первых")
    args = p.parse_args()
    asyncio.run(main(args.csv, args.apply, args.throttle, args.limit))
