"""Генератор HTML-дашборда из накопленных данных в SQLite."""
import html
from datetime import datetime, timedelta, timezone
from pathlib import Path

import analytics
import config
import db


CSS = """
:root {
  --bg: #0f1115;
  --panel: #181b22;
  --panel-2: #1f2330;
  --text: #e8eaf0;
  --muted: #8a93a6;
  --accent: #7c9cff;
  --good: #6ee7b7;
  --bad: #fca5a5;
  --border: #2a2f3d;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f6f7fa;
    --panel: #ffffff;
    --panel-2: #f0f2f7;
    --text: #1a1c22;
    --muted: #5b6577;
    --accent: #3358ff;
    --good: #0a8c5b;
    --bad: #c43d3d;
    --border: #e5e8ef;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 24px;
  font: 14px/1.5 -apple-system, system-ui, "SF Pro Text", sans-serif;
  background: var(--bg); color: var(--text);
}
.header {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 16px; margin-bottom: 24px;
}
.header h1 { margin: 0; font-size: 22px; font-weight: 600; }
.header .meta { color: var(--muted); font-size: 12px; }
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
@media (max-width: 800px) { .cards { grid-template-columns: repeat(2, 1fr); } }
.card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px;
}
.card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
.card .value { font-size: 28px; font-weight: 600; margin-top: 4px; }
.card .delta { font-size: 12px; margin-top: 2px; }
.delta.up { color: var(--good); } .delta.down { color: var(--bad); }
.grid { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; margin-bottom: 24px; }
@media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
.panel {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px;
}
.panel h2 { margin: 0 0 12px; font-size: 14px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
.bar-row { display: grid; grid-template-columns: 60px 1fr 60px; gap: 8px; align-items: center; padding: 2px 0; }
.bar-row .lbl { color: var(--muted); font-variant-numeric: tabular-nums; }
.bar-row .bar { background: var(--panel-2); height: 14px; border-radius: 4px; overflow: hidden; }
.bar-row .bar > span { display: block; height: 100%; background: var(--accent); }
.bar-row .v { text-align: right; font-variant-numeric: tabular-nums; }
.bar-row .v small { color: var(--muted); }
.commenter-row { display: grid; grid-template-columns: 240px 1fr 60px; gap: 12px; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--border); }
.commenter-row:last-child { border-bottom: none; }
.commenter-id { min-width: 0; overflow: hidden; display: flex; flex-direction: column; gap: 2px; }
.commenter-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.commenter-handle { color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.reactions { display: flex; flex-wrap: wrap; gap: 8px; }
.reactions .chip {
  background: var(--panel-2); border-radius: 999px; padding: 6px 12px;
  display: inline-flex; align-items: center; gap: 6px;
}
.reactions .chip .n { color: var(--muted); font-variant-numeric: tabular-nums; }
.events { display: flex; flex-direction: column; gap: 4px; }
.events .ev { display: grid; grid-template-columns: 20px 1fr auto; gap: 8px; font-size: 13px; padding: 4px 0; border-bottom: 1px solid var(--border); }
.events .ev:last-child { border-bottom: none; }
.events .ev .sign.join { color: var(--good); } .events .ev .sign.leave { color: var(--bad); }
.events .ev .when { color: var(--muted); font-size: 12px; }
.footer { color: var(--muted); font-size: 12px; text-align: center; margin-top: 24px; }
.empty { color: var(--muted); font-style: italic; padding: 4px 0; }
"""


def _fmt_int(n):
    if n is None:
        return "—"
    return f"{int(n):,}".replace(",", " ")


def _fmt_delta(d):
    if d is None or d == 0:
        return ("", "")
    cls = "up" if d > 0 else "down"
    sign = "+" if d > 0 else ""
    return (cls, f"{sign}{d} за 7 дней")


def _bar(value, maxval, label, count, fmt="{:.0f}"):
    pct = 0 if not maxval else min(100, value / maxval * 100)
    return (
        f'<div class="bar-row"><div class="lbl">{html.escape(label)}</div>'
        f'<div class="bar"><span style="width:{pct:.1f}%"></span></div>'
        f'<div class="v">{fmt.format(value)} <small>n={count}</small></div></div>'
    )


def generate(db_path=None, channel_title: str | None = None) -> Path:
    db_path = Path(db_path or config.DB_PATH)
    conn = db.connect(db_path)
    try:
        s = analytics.summary(conn)
        bt = analytics.best_time(conn)
        rs = analytics.top_reactions(conn, top_n=12)
        tp = analytics.top_posts(conn, top_n=10)
        ev = analytics.recent_events(conn, days=14, limit=30)
        tc = analytics.top_commenters(conn, top_n=15)
        mc = analytics.most_commented_posts(conn, top_n=10)
    finally:
        conn.close()

    title = channel_title or config.CHANNEL
    now_local = (datetime.now(timezone.utc) + timedelta(hours=config.TZ_OFFSET_HOURS)).strftime("%Y-%m-%d %H:%M")

    delta_cls, delta_txt = _fmt_delta(s["subscribers_delta_7d"])

    cards = [
        ("Подписчиков", _fmt_int(s["subscribers_now"]), (delta_cls, delta_txt)),
        ("Постов", _fmt_int(s["posts"]), ("", f"сообщений: {_fmt_int(s['messages'])}")),
        (
            "Просмотров — медиана",
            _fmt_int(s["views_median"]),
            ("", f"макс: {_fmt_int(s['views_max'])}"),
        ),
        (
            "Комментариев",
            _fmt_int(s["comments_total"]),
            ("", f"авторов: {_fmt_int(s['commenters_total'])}"),
        ),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="label">{html.escape(lbl)}</div>'
        f'<div class="value">{val}</div>'
        f'<div class="delta {d_cls}">{html.escape(d_txt)}</div></div>'
        for lbl, val, (d_cls, d_txt) in cards
    )

    by_hour = bt.get("by_hour") or {}
    by_wd = bt.get("by_weekday") or {}
    max_hour = max((v[0] for v in by_hour.values()), default=0)
    max_wd = max((v[0] for v in by_wd.values()), default=0)

    if by_hour:
        hours_html = "".join(
            _bar(by_hour[h][0], max_hour, f"{h:02d}:00", by_hour[h][1])
            for h in sorted(by_hour)
        )
    else:
        hours_html = '<div class="empty">Мало данных. Нужно ≥1 день после публикации.</div>'

    if by_wd:
        wd_html = "".join(
            _bar(by_wd[w][0], max_wd, analytics.WEEKDAYS_RU[w], by_wd[w][1])
            for w in sorted(by_wd)
        )
    else:
        wd_html = '<div class="empty">Мало данных.</div>'

    if rs:
        reactions_html = '<div class="reactions">' + "".join(
            f'<div class="chip">{html.escape(emoji if not emoji.startswith("custom:") else "🎨")}'
            f'<span class="n">{count}</span></div>'
            for emoji, count in rs
        ) + "</div>"
    else:
        reactions_html = '<div class="empty">Нет данных.</div>'

    if tp:
        tp_rows = "".join(
            f'<tr><td>{p["date"][:10]}</td>'
            f'<td>{html.escape(p["text"]) or "—"}</td>'
            f'<td class="num">{p["views"]}</td>'
            f'<td class="num">{p["reactions_total"]}</td>'
            f'<td class="num">{p["forwards"]}</td></tr>'
            for p in tp
        )
        tp_html = (
            '<table><thead><tr><th>Дата</th><th>Превью</th>'
            '<th>Просм.</th><th>Реакц.</th><th>Перес.</th></tr></thead>'
            f'<tbody>{tp_rows}</tbody></table>'
        )
    else:
        tp_html = '<div class="empty">Нет данных.</div>'

    if tc:
        max_n = max(c["n"] for c in tc)
        tc_rows = []
        for c in tc:
            handle = (
                "@" + c["username"] if c["username"] else f"id={c['sender_id']}"
            )
            pct = c["n"] / max_n * 100
            tc_rows.append(
                f'<div class="commenter-row">'
                f'<div class="commenter-id">'
                f'<div class="commenter-name">{html.escape(c["name"] or "—")}</div>'
                f'<div class="commenter-handle">{html.escape(handle)}</div>'
                f'</div>'
                f'<div class="bar"><span style="width:{pct:.1f}%"></span></div>'
                f'<div class="v">{c["n"]}</div>'
                f'</div>'
            )
        tc_html = "".join(tc_rows)
    else:
        tc_html = '<div class="empty">Нет комментариев в базе.</div>'

    if mc:
        mc_rows = "".join(
            f'<tr><td>{p["date"][:10]}</td>'
            f'<td>{html.escape((p["text"] or "").replace(chr(10), " ")[:80]) or "(медиа)"}</td>'
            f'<td class="num">{p["n"]}</td></tr>'
            for p in mc
        )
        mc_html = (
            '<table><thead><tr><th>Дата</th><th>Превью</th>'
            '<th>Коммент.</th></tr></thead>'
            f'<tbody>{mc_rows}</tbody></table>'
        )
    else:
        mc_html = '<div class="empty">Нет данных.</div>'

    if ev:
        ev_rows = "".join(
            f'<div class="ev">'
            f'<div class="sign {e["event"]}">{"+" if e["event"] == "join" else "−"}</div>'
            f'<div>{html.escape(e["name"] or "—")} '
            f'{html.escape("@" + e["username"] if e["username"] else "id=" + str(e["user_id"]))}</div>'
            f'<div class="when">{e["detected_at"][:16].replace("T", " ")}</div>'
            f'</div>'
            for e in ev
        )
        ev_html = f'<div class="events">{ev_rows}</div>'
    else:
        ev_html = '<div class="empty">Подписок/отписок за 14 дней не было.</div>'

    html_doc = f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>{html.escape(title)} — статистика</title>
<style>{CSS}</style>
</head><body>
<div class="header">
  <h1>📊 {html.escape(title)}</h1>
  <div class="meta">Обновлено: {now_local} (UTC+{config.TZ_OFFSET_HOURS})</div>
</div>

<div class="cards">{cards_html}</div>

<div class="grid">
  <div class="panel">
    <h2>Лучшее время по часам</h2>
    {hours_html}
  </div>
  <div class="panel">
    <h2>По дням недели</h2>
    {wd_html}
  </div>
</div>

<div class="grid">
  <div class="panel">
    <h2>Топ-10 постов по просмотрам</h2>
    {tp_html}
  </div>
  <div class="panel">
    <h2>Реакции — всего</h2>
    {reactions_html}
  </div>
</div>

<div class="grid">
  <div class="panel">
    <h2>Топ комментаторов</h2>
    {tc_html}
  </div>
  <div class="panel">
    <h2>Самые обсуждаемые посты</h2>
    {mc_html}
  </div>
</div>

<div class="panel" style="margin-bottom: 24px;">
  <h2>Подписки и отписки (14 дней)</h2>
  {ev_html}
</div>

<div class="footer">tg_monitor • страница сама обновляется раз в минуту</div>
</body></html>
"""

    out = Path(config.BASE_DIR) / "dashboard.html"
    out.write_text(html_doc, encoding="utf-8")
    return out


if __name__ == "__main__":
    p = generate()
    print(f"Дашборд: file://{p}")
