"""Menu bar app для macOS: показывает основные метрики и кнопку открытия дашборда."""
import subprocess
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

import rumps

import analytics
import config
import dashboard
import db


BASE = Path(__file__).resolve().parent
PYTHON = str(BASE / ".venv" / "bin" / "python")
LOG_PATH = BASE / "menubar.log"


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass


class TgMonitorApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("📊 …", quit_button=None)

        self.item_subs = rumps.MenuItem("Подписчиков: —")
        self.item_posts = rumps.MenuItem("Постов: —")
        self.item_views = rumps.MenuItem("Просмотры (медиана): —")
        self.item_comments = rumps.MenuItem("Комментариев: —")
        self.item_delta = rumps.MenuItem("За 7 дней: —")
        self.item_updated = rumps.MenuItem("Снимок: —")

        self.menu = [
            self.item_subs,
            self.item_posts,
            self.item_views,
            self.item_comments,
            self.item_delta,
            self.item_updated,
            None,
            rumps.MenuItem("📈 Открыть дашборд", callback=self.cb_dashboard),
            rumps.MenuItem("🔄 Обновить посты и комментарии", callback=self.cb_collect),
            rumps.MenuItem("👥 Обновить подписчиков", callback=self.cb_subs),
            rumps.MenuItem("✉️ Отправить сводку в личку", callback=self.cb_daily),
            None,
            rumps.MenuItem("📂 Папка проекта", callback=self.cb_open_folder),
            rumps.MenuItem("📝 Лог", callback=self.cb_open_log),
            None,
            rumps.MenuItem("Выйти", callback=rumps.quit_application),
        ]
        self.refresh_stats()

    @rumps.timer(300)
    def auto_tick(self, _) -> None:
        self.refresh_stats()

    def refresh_stats(self) -> None:
        try:
            conn = db.connect(config.DB_PATH)
            s = analytics.summary(conn)
            conn.close()
        except Exception as e:
            _log(f"refresh error: {e}")
            self.title = "📊 ?"
            return

        subs = s["subscribers_now"]
        self.title = f"📊 {subs}" if subs is not None else "📊 —"

        self.item_subs.title = f"Подписчиков: {subs if subs is not None else '—'}"
        self.item_posts.title = (
            f"Постов: {s['posts']}  (сообщений {s['messages']})"
            if s.get("posts") is not None else "Постов: —"
        )
        self.item_views.title = (
            f"Просмотры (медиана / макс): {s['views_median']:.0f} / {s['views_max']}"
            if s["views_median"] else "Просмотры: —"
        )
        self.item_comments.title = (
            f"Комментариев: {s['comments_total']} от {s['commenters_total']} авторов"
            if s["comments_total"] else "Комментариев: —"
        )

        d = s["subscribers_delta_7d"]
        if d is None:
            self.item_delta.title = "За 7 дней: —"
        else:
            self.item_delta.title = (
                f"За 7 дней: {d:+d}  (+{s['joins_7d']} / −{s['leaves_7d']})"
            )

        now_local = (
            datetime.now(timezone.utc) + timedelta(hours=config.TZ_OFFSET_HOURS)
        ).strftime("%H:%M")
        self.item_updated.title = f"Обновлено: {now_local}"

    def cb_dashboard(self, _) -> None:
        try:
            path = dashboard.generate()
            webbrowser.open(f"file://{path}")
        except Exception as e:
            _log(f"dashboard error: {e}")
            rumps.alert("Ошибка дашборда", str(e))

    def _run_async(self, name: str, args: list[str]) -> None:
        _log(f"start: {name} {args}")
        try:
            subprocess.Popen(
                [PYTHON, str(BASE / "cli.py"), *args],
                cwd=str(BASE),
                stdout=open(LOG_PATH, "a"),
                stderr=subprocess.STDOUT,
            )
            rumps.notification("tg_monitor", name, "Запущено в фоне")
        except Exception as e:
            _log(f"run error: {e}")
            rumps.alert("Не удалось запустить", str(e))

    def cb_collect(self, _) -> None:
        self._run_async("Снимок постов", ["collect"])

    def cb_subs(self, _) -> None:
        self._run_async("Снимок подписчиков", ["subs"])

    def cb_daily(self, _) -> None:
        self._run_async("Сводка в личку", ["daily"])

    def cb_open_folder(self, _) -> None:
        subprocess.run(["open", str(BASE)])

    def cb_open_log(self, _) -> None:
        if not LOG_PATH.exists():
            LOG_PATH.write_text("")
        subprocess.run(["open", str(LOG_PATH)])


if __name__ == "__main__":
    try:
        TgMonitorApp().run()
    except Exception as e:
        _log(f"fatal: {e}")
        raise
