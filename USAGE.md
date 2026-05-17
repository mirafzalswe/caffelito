# Coffee Loyalty — инструкция по использованию

Шаг за шагом: от чистого терминала до работающего бота **и web-админки**, которая реально начисляет штампы и показывает аналитику.

---

## 0. Что должно быть запущено заранее

В отдельном терминале — **проверь, что сервисы живы**:

```bash
# Redis
redis-cli ping
# → PONG

# Postgres (официальный installer)
PGPASSWORD=postgres /Library/PostgreSQL/18/bin/psql -h 127.0.0.1 -U postgres -d coffee_loyalty -c "SELECT 1"
# → должно вернуть 1
```

Если Redis не отвечает: `brew services start redis`.
Если Postgres не отвечает: открой Postgres.app или запусти его так, как запускался при установке.

---

## 1. Боты у @BotFather

В Telegram открой [@BotFather](https://t.me/BotFather) и создай **два отдельных бота**:

1. **Customer-бот** (для клиентов кофейни) — `/newbot` → имя «Demo Coffee Card». BotFather вернёт токен.
2. **Staff-бот** (для бариста) — повтори `/newbot`, имя «Demo Coffee Staff» → отдельный токен.

---

## 2. Файл `.env`

Боты и админка читают токены и пароли из файла **`.env`** (не `.env.example`). Открой `.env` в корне проекта:

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/coffee_loyalty
REDIS_URL=redis://127.0.0.1:6379/0

CUSTOMER_BOT_TOKEN=<твой customer bot token>
STAFF_BOT_TOKEN=<твой staff bot token>

TELEGRAM_WEBHOOK_SECRET=local-dev-secret-32b
SECURITY_PEPPER=local-dev-pepper-32b
JWT_SECRET=local-dev-jwt-32b
```

---

## 3. Миграции и seed

Если поднимаешь с нуля:

```bash
source .venv/bin/activate
alembic upgrade head             # 25 таблиц
python -m scripts.seed           # demo tenant + точка + продукты + кампания 10+1 + бариста + owner
```

Seed создаст тебе **двух пользователей**:

| Тип | Куда логиниться | Логин |
|---|---|---|
| **Owner (web admin)** | http://127.0.0.1:8000/admin/login | `owner@demo.local` / `owner1234` |
| **Barista (Telegram)** | staff-бот | PIN `1234` |

---

## 4. Запуск (четыре терминала)

В каждом сначала: `cd /Users/Macbook/Desktop/coffee && source .venv/bin/activate`

| # | Команда | Что делает |
|---|---|---|
| 1 | `uvicorn app.main:app --port 8000` | **API + web-админка** (http://127.0.0.1:8000/admin) |
| 2 | `python -m app.bots.customer` | Customer-бот (long-polling) |
| 3 | `python -m app.bots.staff` | Staff-бот (long-polling) |
| 4 | `arq app.workers.arq_worker.WorkerSettings` | Воркер: outbox + уведомления + expirations |

Для localhost-разработки это всё, что нужно. Webhook-режим для бота — отдельная история (V2).

---

## 5. Web-админка (http://127.0.0.1:8000/admin)

Зайди → введи `owner@demo.local` / `owner1234` → попадаешь в **Дашборд**.

### 📊 Дашборд
- KPI-плитки: всего клиентов, активных за 30 дней, транзакций сегодня, выручка за 7 дней, free redeems, prepaid выдач, активных точек.
- **Лента транзакций** — обновляется каждые 5 секунд через htmx (live).

### 👥 Клиенты
- Список + поиск по имени или цифрам телефона (например, `4567` найдёт `+998901234567`).
- Карточка клиента: профиль, балансы (карта/free/cashback/пакет), история транзакций, кнопки **Заблокировать / Разблокировать** (с записью в audit).

### 💳 Транзакции
- Лог всех транзакций с фильтром по типу (purchase / redeem_free / prepaid_consume / refund).
- Detail-страница: items, ledger entries (видно exactly что движок насчитал), idempotency key.

### 🎯 Кампании
- Список акций; кнопка **+ Создать**.
- Форма редактирования: код, название, тип, статус (`draft`/`active`/`paused`/`archived`), привязка к точкам, **JSON-rules** в textarea.
- Примеры rules:
  ```json
  {"type":"punchcard","trigger":{"product_category":"coffee","loyalty_eligible_only":true},
   "stamps_required":10,"expires_after_days":90,"cooldown_minutes":0}
  ```
  ```json
  {"type":"cashback","rate":0.05,"expires_after_days":180}
  ```

### 🧑‍🍳 Сотрудники
- Список сотрудников.
- Форма «Добавить»: для **бариста** нужен PIN (4-6 цифр), для **owner/manager/accountant/support** — email + пароль.

### 🏬 Точки
- Список + создание новой точки.

### 🔍 Аудит
- Read-only лог всех действий: кто, что, когда, причина.

---

## 6. Сценарий клиента (Telegram)

1. Открой customer-бота, нажми `/start`.
2. Поделись номером — бот покажет dashboard:
   ```
   ☕ Твоя карта
   ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜  0/10
   🎁 Бесплатных кофе: 0
   💰 Кэшбэк: 0.00 USD
   📦 В пакете: 0
   ```
3. Кнопки: 🔄 Обновить · 📜 История · 🪪 Показать код · 🎁 Использовать бесплатный кофе.

---

## 7. Сценарий бариста (Telegram)

1. Открой staff-бота, `/start` → введи **PIN `1234`**.
2. Точка одна → смена откроется автоматически.
3. **🔎 Найти клиента** → введи телефон / последние 4 цифры / 6-значный код.
4. Карточка клиента → жми кнопку нужного продукта (➕ Cappuccino M, ➕ Latte M…) → штамп засчитан, клиенту приходит уведомление через воркер.
5. После 10 штампов появится «🎁 Использовать бесплатный кофе» — нажми и подтверди.
6. **📦 Открыть пакет** → введи количество (10) и сумму (35.00).
7. После — кнопка **📦 Списать из пакета** появится в карточке клиента.

---

## 8. Что проверить

- В админке на дашборде **выручка за 7 дней** растёт после каждой покупки (htmx-feed обновляется live).
- В разделе **Транзакции** видны все операции в хронологическом порядке.
- В **Аудит** появляются записи о блокировках клиентов и редактировании кампаний.
- В **Клиенты → детали** видно прогресс по карте, балансы, последние 20 транзакций.

---

## 9. Прогон без Telegram (smoke-тест)

```bash
python -m scripts.smoke_e2e
```

Создаёт клиента, прогоняет 10 покупок, проверяет idempotency, redeem, prepaid open + consume.

---

## 10. Типичные ошибки

| Симптом | Причина | Решение |
|---|---|---|
| `CUSTOMER_BOT_TOKEN is not set` | Токен в `.env.example`, а не в `.env` | Скопируй в `.env` |
| Логин в админку: «Неверный email или пароль» | Не запущен seed или хешей нет | `python -m scripts.seed` |
| `/admin/` в браузере → 404 | Не запущен uvicorn | `uvicorn app.main:app --port 8000` |
| Уведомления не приходят клиенту | Не запущен `arq` | Запусти worker в 4-м терминале |
| Бот молчит на `/start` | Не запущен бот-процесс или нет интернета | Проверь логи терминала |

---

## 11. Сброс / переподнятие

```bash
# обнулить пользовательские данные (сохранив tenant/branches/products/campaigns/staff)
PGPASSWORD=postgres /Library/PostgreSQL/18/bin/psql -h 127.0.0.1 -U postgres -d coffee_loyalty -c \
  "TRUNCATE loyalty_cards, transactions, transaction_items, ledger_entries, outbox_events,
   user_dashboard, users, prepaid_packages, cashback_wallets, wallet_entries,
   notification_jobs, audit_logs RESTART IDENTITY CASCADE"

# полностью пересоздать
PGPASSWORD=postgres /Library/PostgreSQL/18/bin/dropdb -h 127.0.0.1 -U postgres coffee_loyalty
PGPASSWORD=postgres /Library/PostgreSQL/18/bin/createdb -h 127.0.0.1 -U postgres coffee_loyalty
alembic upgrade head
python -m scripts.seed
```

---

## 12. Что дальше

После знакомства с MVP — следующие шаги по плану из `IMPLEMENTATION_PLAN.md`:
- Cashback-кампания: создай в админке кампанию с типом `cashback` и rules `{"rate":0.05,"expires_after_days":180}` — движок подхватит автоматически.
- Несколько точек: добавь branch-ы в админке, привяжи бариста через форму создания сотрудника.
- Webhook-режим для ботов вместо polling: `CUSTOMER_BOT_WEBHOOK_URL=https://your-domain/webhook/customer` + ngrok/Cloudflare Tunnel.
- POS-интеграции (R-Keeper, iiko) и реферальная программа — V3.
