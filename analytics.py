import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

import config


WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _to_local(dt_utc: datetime) -> datetime:
    return dt_utc + timedelta(hours=config.TZ_OFFSET_HOURS)


def _lead_ids(conn) -> set[int]:
    """ID «ведущих» сообщений: для альбомов — минимальный id в группе.

    Так альбом из 10 фото считается одним постом.
    """
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT MIN(id) AS id FROM posts GROUP BY COALESCE(grouped_id, id)"
    ).fetchall()
    return {row["id"] for row in rows}


def _latest_snapshot_per_post(conn, only_leads: bool = True) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ps.* FROM post_snapshots ps
        JOIN (
            SELECT post_id, MAX(taken_at) AS max_at
            FROM post_snapshots GROUP BY post_id
        ) m ON ps.post_id = m.post_id AND ps.taken_at = m.max_at
        """
    )
    rows = {row["post_id"]: dict(row) for row in cur.fetchall()}
    if only_leads:
        leads = _lead_ids(conn)
        rows = {pid: s for pid, s in rows.items() if pid in leads}
    return rows


def summary(conn) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM posts")
    n_messages = cur.fetchone()["n"]

    n_posts = cur.execute(
        """
        SELECT COUNT(*) AS n FROM (
          SELECT COALESCE(grouped_id, id) AS gid FROM posts GROUP BY gid
        )
        """
    ).fetchone()["n"]

    snapshots = _latest_snapshot_per_post(conn)
    views = [s["views"] for s in snapshots.values() if s["views"]]
    forwards = [s["forwards"] for s in snapshots.values() if s["forwards"]]

    n_comments = cur.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    n_commenters = cur.execute(
        "SELECT COUNT(DISTINCT sender_id) FROM comments WHERE sender_id IS NOT NULL"
    ).fetchone()[0]

    cur.execute("SELECT count FROM subscriber_counts ORDER BY taken_at DESC LIMIT 1")
    row = cur.fetchone()
    subs_now = row["count"] if row else None

    cur.execute(
        "SELECT count FROM subscriber_counts "
        "WHERE taken_at <= datetime('now', '-7 days') "
        "ORDER BY taken_at DESC LIMIT 1"
    )
    row = cur.fetchone()
    subs_week_ago = row["count"] if row else None

    cur.execute(
        "SELECT event, COUNT(*) AS n FROM subscriber_events "
        "WHERE detected_at > datetime('now', '-7 days') GROUP BY event"
    )
    events_7d = {r["event"]: r["n"] for r in cur.fetchall()}

    delta_7d = (
        subs_now - subs_week_ago
        if subs_now is not None and subs_week_ago is not None
        else None
    )

    return {
        "posts": n_posts,
        "messages": n_messages,
        "subscribers_now": subs_now,
        "subscribers_7d_ago": subs_week_ago,
        "subscribers_delta_7d": delta_7d,
        "joins_7d": events_7d.get("join", 0),
        "leaves_7d": events_7d.get("leave", 0),
        "views_median": statistics.median(views) if views else None,
        "views_avg": statistics.mean(views) if views else None,
        "views_max": max(views) if views else None,
        "forwards_total": sum(forwards) if forwards else 0,
        "comments_total": n_comments,
        "commenters_total": n_commenters,
    }


def top_commenters(conn, top_n: int = 15) -> list:
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT sender_id,
               MAX(sender_name) AS name,
               MAX(sender_username) AS username,
               COUNT(*) AS n,
               MAX(date) AS last_at
        FROM comments
        WHERE sender_id IS NOT NULL
        GROUP BY sender_id
        ORDER BY n DESC
        LIMIT ?
        """,
        (top_n,),
    ).fetchall()
    return [dict(r) for r in rows]


def most_commented_posts(conn, top_n: int = 10) -> list:
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT p.id, p.date,
               COALESCE(NULLIF(p.text, ''), '') AS text,
               COUNT(c.id) AS n
        FROM posts p
        JOIN comments c ON c.post_id = p.id
        GROUP BY p.id
        ORDER BY n DESC, p.date DESC
        LIMIT ?
        """,
        (top_n,),
    ).fetchall()
    return [dict(r) for r in rows]


def best_time(conn, min_days: int = 1, max_days: int = 90) -> dict:
    """Лучшее время публикации: медиана охватов по часам и дням недели
    в локальном часовом поясе. Берём посты от min_days до max_days дней —
    свежие ещё не «дозрели», очень старые искажают рост канала.
    """
    cur = conn.cursor()
    snapshots = _latest_snapshot_per_post(conn)

    cur.execute("SELECT id, date FROM posts")
    posts = {row["id"]: row["date"] for row in cur.fetchall()}

    now = datetime.now().astimezone().replace(tzinfo=None)
    by_hour = defaultdict(list)
    by_weekday = defaultdict(list)
    by_slot = defaultdict(list)

    for pid, date_iso in posts.items():
        snap = snapshots.get(pid)
        if not snap or not snap["views"]:
            continue
        dt_utc = datetime.fromisoformat(date_iso).replace(tzinfo=None)
        age_days = (now - dt_utc).total_seconds() / 86400
        if age_days < min_days or age_days > max_days:
            continue
        dt_local = _to_local(dt_utc)
        h = dt_local.hour
        wd = dt_local.weekday()
        by_hour[h].append(snap["views"])
        by_weekday[wd].append(snap["views"])
        by_slot[(wd, h)].append(snap["views"])

    def _summ(d):
        return {k: (statistics.median(v), len(v)) for k, v in d.items()}

    return {
        "by_hour": _summ(by_hour),
        "by_weekday": _summ(by_weekday),
        "by_slot": _summ(by_slot),
    }


def top_reactions(conn, top_n: int = 10) -> list:
    snapshots = _latest_snapshot_per_post(conn)
    total = defaultdict(int)
    for snap in snapshots.values():
        try:
            r = json.loads(snap["reactions_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            r = {}
        for k, v in r.items():
            total[k] += v
    return sorted(total.items(), key=lambda x: -x[1])[:top_n]


def top_posts(conn, top_n: int = 10) -> list:
    cur = conn.cursor()
    snapshots = _latest_snapshot_per_post(conn)
    cur.execute("SELECT id, date, text FROM posts")
    posts = {row["id"]: dict(row) for row in cur.fetchall()}

    rows = []
    for pid, snap in snapshots.items():
        if pid not in posts:
            continue
        rows.append(
            {
                "id": pid,
                "date": posts[pid]["date"],
                "text": (posts[pid]["text"] or "").replace("\n", " ")[:80],
                "views": snap["views"] or 0,
                "forwards": snap["forwards"] or 0,
                "reactions_total": sum(
                    json.loads(snap["reactions_json"] or "{}").values()
                ),
            }
        )
    return sorted(rows, key=lambda r: -r["views"])[:top_n]


def recent_events(conn, days: int = 7, limit: int = 50) -> list:
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM subscriber_events "
        "WHERE detected_at > datetime('now', ?) "
        "ORDER BY detected_at DESC LIMIT ?",
        (f"-{days} days", limit),
    )
    return [dict(r) for r in cur.fetchall()]
