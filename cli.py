import argparse
import asyncio

# --- macOS 26 / Python 3.14 compat ------------------------------------------
# На свежих macOS platform.mac_ver() возвращает пустую строку версии, из-за
# чего telethon.crypto.libssl падает на release.split('.') (ValueError) ещё на
# импорте. Подставляем валидную версию ДО импорта telethon.
import platform as _platform
if not _platform.mac_ver()[0]:
    _platform.mac_ver = lambda *_a, **_k: ("11.0", ("", "", ""), "")
# ----------------------------------------------------------------------------

from telethon import TelegramClient

import analytics
import collector
import comments as comments_mod
import config
import db
import subscribers


async def _make_client() -> TelegramClient:
    config.require()
    client = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH)
    await client.start()
    return client


async def cmd_setup() -> None:
    client = await _make_client()
    me = await client.get_me()
    print(f"Залогинен: {me.first_name} (@{me.username or '—'}, id={me.id})")
    try:
        entity = await client.get_entity(config.CHANNEL)
        print(f"Канал найден: {getattr(entity, 'title', config.CHANNEL)}")
    except Exception as e:
        print(f"Канал {config.CHANNEL} не найден или нет доступа: {e}")
    await client.disconnect()


async def cmd_collect(full: bool = False) -> None:
    conn = db.connect(config.DB_PATH)
    client = await _make_client()
    try:
        n_posts = await collector.collect_posts(
            client, config.CHANNEL, conn, force_full=full
        )
        n_comments, linked_id = await comments_mod.collect_comments(
            client, config.CHANNEL, conn
        )
        print(f"Снэпшот сохранён. Сообщений обработано: {n_posts}")
        if linked_id is None:
            print("Чат комментариев у канала не привязан.")
        else:
            print(f"Новых комментариев: {n_comments}")
    finally:
        await client.disconnect()
        conn.close()


async def cmd_comments() -> None:
    conn = db.connect(config.DB_PATH)
    client = await _make_client()
    try:
        n, linked_id = await comments_mod.collect_comments(
            client, config.CHANNEL, conn
        )
        if linked_id is None:
            print("Чат комментариев у канала не привязан.")
        else:
            print(f"Новых комментариев: {n}")
    finally:
        await client.disconnect()
        conn.close()


async def cmd_subs() -> None:
    conn = db.connect(config.DB_PATH)
    client = await _make_client()
    try:
        r = await subscribers.snapshot_subscribers(client, config.CHANNEL, conn)
        print(f"Подписчиков сейчас: {r['total']}")
        print(f"С прошлого замера: +{r['joined']} / −{r['left']}")
        for uid, username, name in r["joined_users"][:30]:
            print(f"  + {name or '—'} (@{username or '—'}, id={uid})")
        if len(r["joined_users"]) > 30:
            print(f"  …и ещё {len(r['joined_users']) - 30}")
    finally:
        await client.disconnect()
        conn.close()


def _fmt(n):
    return f"{n:.0f}" if isinstance(n, float) else str(n) if n is not None else "—"


async def cmd_report() -> None:
    conn = db.connect(config.DB_PATH)
    try:
        s = analytics.summary(conn)
        print("=== Сводка ===")
        print(f"Постов (уникальных):     {s['posts']}  (сообщений {s['messages']})")
        print(f"Подписчиков сейчас:      {_fmt(s['subscribers_now'])}")
        if s["subscribers_delta_7d"] is not None:
            print(f"Изменение за 7 дней:     {s['subscribers_delta_7d']:+d}")
        print(f"  присоединились (7д):   {s['joins_7d']}")
        print(f"  отписались (7д):       {s['leaves_7d']}")
        print(f"Просмотры — медиана:     {_fmt(s['views_median'])}")
        print(f"Просмотры — среднее:     {_fmt(s['views_avg'])}")
        print(f"Просмотры — максимум:    {_fmt(s['views_max'])}")
        print(f"Всего пересылок:         {s['forwards_total']}")

        bt = analytics.best_time(conn)
        print(f"\n=== Лучшее время (UTC+{config.TZ_OFFSET_HOURS}) ===")
        if not bt["by_hour"]:
            print("  Мало данных — нужно ≥1 день после публикации.")
        else:
            print("По часам:")
            for h in sorted(bt["by_hour"]):
                med, n = bt["by_hour"][h]
                bar = "█" * min(40, int(med / max(1, s["views_max"] or 1) * 40))
                print(f"  {h:02d}:00  медиана {med:>5.0f}  (n={n:>2})  {bar}")
            print("По дням недели:")
            for wd in sorted(bt["by_weekday"]):
                med, n = bt["by_weekday"][wd]
                print(
                    f"  {analytics.WEEKDAYS_RU[wd]}  медиана {med:>5.0f}  (n={n})"
                )

        rs = analytics.top_reactions(conn)
        if rs:
            print("\n=== Топ реакций ===")
            for emoji, count in rs:
                print(f"  {emoji}: {count}")

        if s["comments_total"]:
            print(
                f"\n=== Комментарии ===\n"
                f"Всего: {s['comments_total']} | уникальных авторов: "
                f"{s['commenters_total']}"
            )
            tc = analytics.top_commenters(conn, top_n=10)
            if tc:
                print("Топ комментаторов:")
                for i, c in enumerate(tc, 1):
                    handle = (
                        f"@{c['username']}" if c["username"] else f"id={c['sender_id']}"
                    )
                    print(
                        f"  {i:>2}. {c['name'] or '—'}  {handle}  — "
                        f"{c['n']} коммент."
                    )
            mc = analytics.most_commented_posts(conn, top_n=5)
            if mc:
                print("Самые обсуждаемые посты:")
                for p in mc:
                    preview = (p["text"] or "").replace("\n", " ")[:60] or "(медиа)"
                    print(
                        f"  id={p['id']} {p['date'][:10]} "
                        f"коммент={p['n']:>3}  «{preview}»"
                    )

        tp = analytics.top_posts(conn, top_n=5)
        if tp:
            print("\n=== Топ-5 постов по просмотрам ===")
            for p in tp:
                print(
                    f"  id={p['id']} {p['date'][:10]} "
                    f"views={p['views']:>5} reacts={p['reactions_total']:>3} "
                    f"fwds={p['forwards']:>3}  «{p['text']}»"
                )

        ev = analytics.recent_events(conn, days=7, limit=20)
        if ev:
            print("\n=== Последние подписки/отписки (7д) ===")
            for e in ev:
                sign = "+" if e["event"] == "join" else "−"
                handle = f"@{e['username']}" if e["username"] else f"id={e['user_id']}"
                print(
                    f"  {sign} {e['detected_at'][:16].replace('T', ' ')}  "
                    f"{e['name'] or '—'}  {handle}"
                )
    finally:
        conn.close()


async def cmd_daily() -> None:
    """Послать сводку по каналу владельцу (Даше) в личку — от лица Джаны. Раньше
    уходила в Saved Messages учётки монитора (т.е. «Джане», не Даше)."""
    conn = db.connect(config.DB_PATH)
    client = await _make_client()
    try:
        s = analytics.summary(conn)
        bt = analytics.best_time(conn)
        rs = analytics.top_reactions(conn, top_n=5)
        tc = analytics.top_commenters(conn, top_n=3)

        lines = ["📊 Канал — сводка"]
        lines.append(
            f"Подписчиков: {_fmt(s['subscribers_now'])}"
            + (
                f" ({s['subscribers_delta_7d']:+d} за 7д)"
                if s["subscribers_delta_7d"] is not None
                else ""
            )
        )
        lines.append(f"Постов: {s['posts']}")
        lines.append(
            f"Просмотры: медиана {_fmt(s['views_median'])}, "
            f"максимум {_fmt(s['views_max'])}"
        )
        lines.append(f"Пересылок всего: {s['forwards_total']}")
        if s["comments_total"]:
            lines.append(
                f"Комментариев: {s['comments_total']} от "
                f"{s['commenters_total']} авторов"
            )
            if tc:
                top_str = ", ".join(
                    f"{c['name'] or ('@' + c['username']) or c['sender_id']} ({c['n']})"
                    for c in tc
                )
                lines.append(f"Топ-3 комментатора: {top_str}")
        if bt["by_hour"]:
            best_h = max(bt["by_hour"], key=lambda h: bt["by_hour"][h][0])
            best_wd = max(bt["by_weekday"], key=lambda w: bt["by_weekday"][w][0])
            lines.append(
                f"Лучший слот: {analytics.WEEKDAYS_RU[best_wd]} "
                f"{best_h:02d}:00 (UTC+{config.TZ_OFFSET_HOURS})"
            )
        if rs:
            lines.append("Реакции: " + " ".join(f"{e}×{c}" for e, c in rs))

        target = config.DAILY_TO or "me"
        text = "\n".join(lines)
        try:
            await client.send_message(target, text)
        except ValueError:
            # сессия монитора могла не знать владельца по id (свежий session-файл без
            # access_hash) — пробуем резолв с сервера (для @username сработает; для
            # «голого» id нужно, чтобы учётка хоть раз видела этого пользователя).
            entity = await client.get_entity(target)
            await client.send_message(entity, text)
        where = "в Saved Messages" if target == "me" else f"владельцу в личку ({target})"
        print(f"Сводка отправлена {where}.")
    finally:
        await client.disconnect()
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Мониторинг Telegram-канала")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="Первый вход + проверка канала")
    p_collect = sub.add_parser(
        "collect", help="Снять снимок постов и комментариев"
    )
    p_collect.add_argument(
        "--full", action="store_true", help="Полный пересбор всех постов"
    )
    sub.add_parser("comments", help="Только комментарии")
    sub.add_parser("subs", help="Снять снимок подписчиков (нужны админ-права)")
    sub.add_parser("report", help="Отчёт в терминал")
    sub.add_parser("daily", help="Отправить сводку владельцу в личку (от Джаны)")

    args = parser.parse_args()
    if args.cmd == "collect":
        asyncio.run(cmd_collect(full=args.full))
    else:
        commands = {
            "setup": cmd_setup,
            "comments": cmd_comments,
            "subs": cmd_subs,
            "report": cmd_report,
            "daily": cmd_daily,
        }
        asyncio.run(commands[args.cmd]())


if __name__ == "__main__":
    main()
