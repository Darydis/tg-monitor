"""Сбор комментариев из linked discussion chat канала."""
from telethon.errors import RPCError
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import PeerUser

import db


async def _find_linked_chat(client, channel) -> int | None:
    try:
        full = await client(GetFullChannelRequest(channel))
    except RPCError:
        return None
    return getattr(full.full_chat, "linked_chat_id", None) or None


async def collect_comments(client, channel, conn) -> tuple[int, int | None]:
    """Снять комментарии из чата обсуждений, инкрементально по `message_id`.

    Возвращает `(new_count, linked_chat_id)`. Если канал не имеет привязанного
    чата — `(0, None)`.
    """
    linked_id = await _find_linked_chat(client, channel)
    if not linked_id:
        return 0, None

    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(message_id) AS m FROM comments WHERE linked_chat_id = ?",
        (linked_id,),
    )
    last_id = (cur.fetchone() or {}).get("m") or 0

    count = 0
    try:
        async for msg in client.iter_messages(linked_id, min_id=last_id):
            if msg.action is not None:
                continue
            if not isinstance(msg.from_id, PeerUser):
                continue

            sender_id = msg.from_id.user_id

            post_id = None
            if msg.reply_to is not None:
                top = getattr(msg.reply_to, "reply_to_top_id", None)
                post_id = top or getattr(msg.reply_to, "reply_to_msg_id", None)

            username = None
            name = None
            try:
                sender = await msg.get_sender()
                if sender is not None:
                    username = getattr(sender, "username", None)
                    name = (
                        " ".join(
                            filter(
                                None,
                                [
                                    getattr(sender, "first_name", None),
                                    getattr(sender, "last_name", None),
                                ],
                            )
                        )
                        or None
                    )
            except RPCError:
                pass

            cur.execute(
                """
                INSERT OR IGNORE INTO comments
                  (linked_chat_id, message_id, post_id, sender_id,
                   sender_username, sender_name, date, text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    linked_id,
                    msg.id,
                    post_id,
                    sender_id,
                    username,
                    name,
                    msg.date.isoformat(timespec="seconds"),
                    (msg.message or "")[:4096],
                ),
            )
            if cur.rowcount:
                count += 1
    finally:
        conn.commit()

    return count, linked_id
