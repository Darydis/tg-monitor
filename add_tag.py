"""Безопасное добавление хештега в конец существующего поста.

Использование:
    python add_tag.py <post_id> <hashtag> [--apply]

Без --apply делается dry-run (только показывает оригинал и предполагаемый результат).
С --apply редактирует пост через Telethon, сохраняя entities (URL, форматирование).

Перед редактированием оригинальный текст сохраняется в backups/<post_id>_<timestamp>.txt
"""

import asyncio
import sys
import datetime
from pathlib import Path
from telethon import TelegramClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config


async def main(post_id: int, hashtag: str, apply: bool) -> None:
    config.require()
    async with TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH) as client:
        msg = await client.get_messages(config.CHANNEL, ids=post_id)
        if msg is None:
            print(f"Пост {post_id} не найден в канале {config.CHANNEL}")
            return
        if msg.action is not None:
            print(f"Пост {post_id} — служебное сообщение, редактировать нельзя")
            return

        original = msg.message or ""
        entities = msg.entities or []
        print(f"=== ОРИГИНАЛ (id={post_id}, {len(original)} символов, entities={len(entities)}) ===")
        print(original)
        print("=== /ОРИГИНАЛ ===\n")

        if hashtag in original:
            print(f"Хештег {hashtag} уже есть в посте — ничего не делаю")
            return

        new_text = original.rstrip() + "\n\n" + hashtag
        print(f"=== ПРЕДПОЛАГАЕМЫЙ НОВЫЙ ТЕКСТ ({len(new_text)} символов) ===")
        print(new_text)
        print("=== /НОВЫЙ ===\n")

        if not apply:
            print("DRY RUN: ничего не отправлено. Запусти с --apply, чтобы применить.")
            return

        # Сохраняем оригинал в бэкап
        backup_dir = Path(__file__).resolve().parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{post_id}_{ts}.txt"
        backup_path.write_text(original, encoding="utf-8")
        print(f"Backup сохранён: {backup_path}")

        # Редактируем, сохраняя entities (URL, форматирование)
        result = await client.edit_message(
            config.CHANNEL,
            post_id,
            new_text,
            formatting_entities=entities,
        )
        print(f"Edit OK. msg_id={result.id}")

        # Верификация
        check = await client.get_messages(config.CHANNEL, ids=post_id)
        print(f"\n=== ФАКТИЧЕСКИЙ ТЕКСТ ПОСЛЕ ПРАВКИ ({len(check.message or '')} символов) ===")
        print(check.message)
        print("=== /ПОСЛЕ ПРАВКИ ===")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python add_tag.py <post_id> <hashtag> [--apply]")
        sys.exit(1)
    pid = int(sys.argv[1])
    tag = sys.argv[2]
    if not tag.startswith("#"):
        print("Хештег должен начинаться с #")
        sys.exit(1)
    apply_flag = "--apply" in sys.argv
    asyncio.run(main(pid, tag, apply_flag))
