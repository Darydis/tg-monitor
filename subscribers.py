from telethon.errors import ChatAdminRequiredError

import db


async def snapshot_subscribers(client, channel, conn) -> dict:
    """Снять снимок подписчиков и зафиксировать join/leave события.

    Для broadcast-канала требует админ-прав у залогиненного аккаунта.
    Telegram отдаёт максимум ~10k участников канала; для бóльших каналов
    видна только верхушка.
    """
    cur = conn.cursor()
    now = db.now_iso()

    current_ids: set[int] = set()
    user_meta: dict[int, tuple[str | None, str | None]] = {}

    try:
        async for user in client.iter_participants(channel):
            current_ids.add(user.id)
            name = " ".join(filter(None, [user.first_name, user.last_name])) or None
            user_meta[user.id] = (user.username, name)
    except ChatAdminRequiredError:
        raise SystemExit(
            "Для просмотра подписчиков аккаунт должен быть админом канала. "
            "Команды collect/report работают и без админ-прав."
        )

    cur.execute("SELECT user_id FROM subscribers")
    prev_ids = {row["user_id"] for row in cur.fetchall()}

    joined = current_ids - prev_ids
    left = prev_ids - current_ids

    for uid in joined:
        username, name = user_meta[uid]
        cur.execute(
            """
            INSERT INTO subscribers (user_id, first_seen, last_seen, username, name)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              last_seen = excluded.last_seen,
              username  = excluded.username,
              name      = excluded.name
            """,
            (uid, now, now, username, name),
        )
        cur.execute(
            "INSERT INTO subscriber_events (user_id, event, detected_at, username, name) "
            "VALUES (?, 'join', ?, ?, ?)",
            (uid, now, username, name),
        )

    for uid in left:
        cur.execute("SELECT username, name FROM subscribers WHERE user_id = ?", (uid,))
        row = cur.fetchone()
        username = row["username"] if row else None
        name = row["name"] if row else None
        cur.execute(
            "INSERT INTO subscriber_events (user_id, event, detected_at, username, name) "
            "VALUES (?, 'leave', ?, ?, ?)",
            (uid, now, username, name),
        )
        cur.execute("DELETE FROM subscribers WHERE user_id = ?", (uid,))

    for uid in current_ids - joined:
        username, name = user_meta[uid]
        cur.execute(
            "UPDATE subscribers SET last_seen = ?, username = ?, name = ? WHERE user_id = ?",
            (now, username, name, uid),
        )

    cur.execute(
        "INSERT OR REPLACE INTO subscriber_counts (taken_at, count) VALUES (?, ?)",
        (now, len(current_ids)),
    )
    conn.commit()

    return {
        "total": len(current_ids),
        "joined": len(joined),
        "left": len(left),
        "joined_users": [(uid, *user_meta[uid]) for uid in joined],
    }
