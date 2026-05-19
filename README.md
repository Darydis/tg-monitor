# tg_monitor — мониторинг своего Telegram-канала

Локальный скрипт на Python + Telethon (User API). Снимает срезы постов и
участников канала в SQLite, считает охваты, реакции, лучшее время
публикации, динамику подписчиков.

## Что собирает

- **Просмотры** — текущее значение каждого поста, при регулярных запусках
  накапливается история роста.
- **Реакции** — по каждому эмодзи отдельно, плюс топ за всё время.
- **Охваты** — медиана/среднее/максимум по просмотрам.
- **Пересылки и комментарии** — счётчики forwards и replies.
- **Лучшее время публикации** — медиана просмотров по часам и дням недели
  в локальном поясе (по умолчанию UTC+3, Москва).
- **Подписки и отписки** — поимённо, через сравнение снимков участников
  (нужны админ-права в канале).

## Установка

```bash
cd ~/tg-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Открой `.env` и заполни:

1. **TG_API_ID** и **TG_API_HASH** — забери на https://my.telegram.org/apps
   (нужен Telegram-аккаунт; «App title» и «Short name» — любые).
2. **TG_CHANNEL** — `@username` канала или числовой id вида
   `-1001234567890`.
3. **TG_TZ_OFFSET** — часовой пояс для отчётов (по умолчанию `3`).

## Запуск

```bash
# 1) Первый вход. Telethon спросит телефон, SMS-код, при включённом 2FA — пароль.
python cli.py setup

# 2) Снять снимок постов: просмотры, реакции, пересылки
python cli.py collect

# 3) Снять снимок подписчиков (нужны админ-права у твоего аккаунта)
python cli.py subs

# 4) Отчёт в терминал
python cli.py report

# 5) Отправить сводку себе в «Избранное» (Saved Messages)
python cli.py daily
```

После первого `setup` появится файл `tg_monitor.session` — это сохранённая
авторизация Telethon. Не выкладывай его никуда.

## Menu bar app + автозапуск (рекомендуется)

В `launchagents/` лежат четыре `.plist`, скрипт `install_agents.sh` ставит их
в `~/Library/LaunchAgents/` и подгружает в `launchctl`.

```bash
./install_agents.sh
```

После установки:
- В строке меню macOS появляется иконка **📊** с числом подписчиков.
- Клик по иконке → меню с метриками и кнопками «Открыть дашборд»,
  «Обновить просмотры/реакции», «Обновить подписчиков», «Сводка в Saved Messages».
- Дашборд — одностраничный HTML (`dashboard.html`), сам обновляется в браузере
  раз в минуту.

Что делают агенты:

| Агент | Расписание | Действие |
|---|---|---|
| `com.tgmonitor.collect` | каждые 60 минут | `cli.py collect` |
| `com.tgmonitor.subs` | каждый день в 09:30 | `cli.py subs` |
| `com.tgmonitor.daily` | каждый день в 09:35 | `cli.py daily` (отправляет сводку в Saved Messages) |
| `com.tgmonitor.menubar` | при логине, KeepAlive | приложение в строке меню |

Снять всё:

```bash
./uninstall_agents.sh
```

После правки кода — выгрузить и снова загрузить нужный агент:

```bash
launchctl unload ~/Library/LaunchAgents/com.tgmonitor.menubar.plist
launchctl load   ~/Library/LaunchAgents/com.tgmonitor.menubar.plist
```

## Альтернатива: cron вместо launchd

Если хочешь без launchd:

```cron
0 * * * * cd ~/tg-monitor && .venv/bin/python cli.py collect >> cron.log 2>&1
30 9 * * * cd ~/tg-monitor && .venv/bin/python cli.py subs >> cron.log 2>&1
35 9 * * * cd ~/tg-monitor && .venv/bin/python cli.py daily >> cron.log 2>&1
```

## Ограничения Telegram User API

- **Список подписчиков** broadcast-канала отдаётся только админам, и не
  более ~10 000 человек суммарно. Для каналов крупнее видны только
  последние ~10к; отписки за пределами этой выборки система отследить
  не сможет.
- **Анонимные подписки** Telegram не раскрывает в API — у таких юзеров
  будет пустой `name` и `username`.
- **Просмотры** в API — это итоговое число (как видно под постом).
  Тренд роста собирается за счёт регулярных снимков.
- **Аккуратнее с частотой**: 1 раз в час — норма, чаще не нужно.
  Агрессивный опрос User API может привести к временному ограничению
  аккаунта.

## База данных

SQLite-файл `tg_monitor.db`. Основные таблицы:

- `posts` — каталог постов (id, дата, текст).
- `post_snapshots` — снимки метрик по постам во времени (views, forwards,
  replies, JSON реакций). Используй для собственных запросов и графиков.
- `subscribers` — текущий список подписчиков.
- `subscriber_events` — события join/leave с таймстемпом.
- `subscriber_counts` — общее число подписчиков на момент каждого снимка.

Посмотреть глазами:

```bash
sqlite3 tg_monitor.db
.tables
SELECT date, views, reactions_json FROM posts p
  JOIN post_snapshots s ON p.id = s.post_id
  ORDER BY date DESC LIMIT 10;
```
