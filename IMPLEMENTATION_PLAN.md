# Coffee Loyalty Platform — Production-Grade Implementation Plan

> Loyalty / Cashback / Prepaid система для сети coffee shop через Telegram Bot.
> Документ написан как **technical & product blueprint** для команды, реализующей production SaaS.

---

## 0. TL;DR (Executive Summary)

**Что строим:** мульти-tenant loyalty platform (B2B2C) для кофеен, состоящая из:
1. **Customer Telegram Bot** — клиент видит баланс, прогресс, историю, получает push-уведомления.
2. **Staff App** (Telegram Bot для бариста + минимальный Web PWA) — выдаёт кофе, начисляет покупки, активирует пакеты.
3. **Admin/Owner Web Panel** — управление акциями, точками, сотрудниками, аналитика.
4. **Backend API + Notification/Scheduler workers** — ядро бизнес-логики.

**Ключевая инженерная сложность:**
- Идентификация клиента **до** того, как он нажал `/start` в боте → identity-by-phone, deferred linking.
- Race conditions при одновременной выдаче кофе на разных кассах одной точки.
- Idempotent transactions (бариста дважды нажал «Начислить»).
- Fraud prevention (бариста выдаёт кофе «себе»).
- Множество loyalty-механик (3+1, 5+1, 10+1, prepaid, cashback, bonus) под одной моделью.

**Главный архитектурный приём:** все loyalty-механики моделируются как **rule-based campaigns** поверх единого журнала `ledger_entries` (event-sourced, append-only). Балансы и progress — это **проекции (read models)** этого журнала. Это даёт точность, аудит, refund/rollback и масштабирование.

---

# 1. PRODUCT ANALYSIS

## 1.1 Цель продукта

Превратить **импульсные транзакционные покупки** кофе в **повторяющийся ритуал с эмоциональным крючком** через прозрачную loyalty-механику и низкофрикционный канал коммуникации (Telegram).

Бизнес-цель кофейни: ↑ retention, ↑ frequency, ↑ AOV, ↓ CAC через word-of-mouth, ↑ predictable cashflow (prepaid).

## 1.2 Target audience

**B2C (конечные клиенты):**
- 18–45 лет, городские жители, регулярно покупают кофе (2–7 раз в неделю).
- Telegram-active (СНГ, Восточная Европа, часть LATAM/MENA).
- Сегменты:
  - **Daily commuters** (главный JTBD) — кофе по дороге, ритуал.
  - **Office crowd** — несколько кофе в день, часто в одну точку.
  - **Students** — чувствительны к цене, хорошо реагируют на 5+1/10+1.

**B2B (заказчики платформы):**
- **Single-shop owners** — 1 точка, 50–500 транзакций/день. Платят SaaS subscription.
- **Multi-shop / small chains** — 2–20 точек.
- **Franchise networks** — 20+ точек, нужны branch management, role permissions, BI.

## 1.3 Какую проблему решает

| Проблема кофейни | Текущее «решение» | Что даём мы |
|---|---|---|
| Бумажные карточки 10+1 теряются, легко подделать | Картон + штамп | Цифровой ledger, anti-fraud |
| Нет данных о клиенте (кто он, как часто, что любит) | Никаких | CRM-профиль, RFM сегменты |
| Нет канала reach-out (email никто не читает) | SMS дорого | Telegram bot — free, 80%+ open rate |
| Cashflow рваный (особенно зимой) | Ничего | Prepaid packages |
| Бариста забывает напомнить про free coffee | Человеческий фактор | Автоматический progress |

## 1.4 Business value (для кофейни)

- **+15–35% repeat visits** в первые 90 дней (бенчмарк Square Loyalty, Punchcard, Stamp Me).
- **+8–20% AOV** через bonus-механики (купи капучино — получи бонус на круассан).
- **Cashflow предоплата** — prepaid packages дают деньги «вперёд» (2–6 недель runway).
- **Customer database** — главный долгоиграющий актив; принадлежит кофейне, экспортируется.

## 1.5 Monetization model (наш доход как SaaS)

Рекомендую **гибридную** модель:

1. **SaaS subscription** (основа) — tiered:
   - **Starter** — 1 точка, до 500 клиентов, базовые акции.
   - **Growth** — до 5 точек, неограниченно клиентов, аналитика, A/B акции.
   - **Chain/Franchise** — 5+ точек, RBAC, аудит, API, white-label.
2. **Transaction fee** на prepaid packages (1–2% от суммы предоплаты) — выровнено с интересами клиента: чем больше prepaid продаёт кофейня, тем больше зарабатываем.
3. **Add-ons:** SMS fallback, кастомизация бота (white-label под бренд), POS-интеграции.

Почему **не** per-transaction fee на обычных покупках: разрушает unit-economics для кофейни (маржа на чашке 50–70%, отдавать 1–2% жалко).

## 1.6 Retention mechanics (почему клиент будет возвращаться)

Слои retention, упорядоченные по силе:

1. **Loss aversion** (главный) — «у тебя 7/10 кофе, не теряй прогресс». Sunk cost эффект.
2. **Variable reward** — bonus coffee, surprise drops, «secret menu» по достижении статусов.
3. **Identity & status** — VIP-уровни (Bronze/Silver/Gold по частоте посещений).
4. **Habit-forming notifications** — утром «доброе утро, до бесплатного 2 кофе» в 8:00.
5. **Sunk cost prepaid** — «у тебя оплачено ещё 4 кофе» → клиент идёт сюда, а не к конкуренту.
6. **Social** — реферальная программа (V2), gift coffee другу.

## 1.7 Risks / pitfalls

- **Notification fatigue** → unsubscribe → канал теряет ценность. Нужны frequency caps, ML-driven send-time optimization.
- **Promo cannibalization** — 10+1 пожирает маржу, если нет лимита на дешёвые позиции.
- **Bариста-fraud** — выдача free coffee «своим». Главная угроза unit-economics.
- **Telegram dependency** — что если Telegram заблокирован? Нужна Web PWA как backup identity (V2).

---

# 2. SYSTEM ARCHITECTURE

## 2.1 High-level

```
┌─────────────────────────────────────────────────────────────┐
│  Clients                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Customer Bot │  │ Staff Bot    │  │ Admin Web    │       │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘       │
└─────────┼─────────────────┼─────────────────┼───────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Edge: API Gateway (NGINX/Traefik) + WAF + Rate-limit       │
└─────────────────────────────────────────────────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│  Application layer (stateless, horizontally scalable)       │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐    │
│  │ Bot      │ │ REST/    │ │ Webhook  │ │ Admin BFF    │    │
│  │ Adapter  │ │ GraphQL  │ │ Receiver │ │ (Next.js)    │    │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘    │
│       └────────────┴────────────┴──────────────┘            │
│                          │                                  │
│              ┌───────────▼────────────┐                     │
│              │  Domain Services       │                     │
│              │  • Identity            │                     │
│              │  • Loyalty Engine      │                     │
│              │  • Wallet (cashback)   │                     │
│              │  • Prepaid             │                     │
│              │  • Campaign            │                     │
│              │  • Notification        │                     │
│              │  • Audit               │                     │
│              └───────────┬────────────┘                     │
└──────────────────────────┼──────────────────────────────────┘
                           │
   ┌───────────────────────┼───────────────────────┐
   ▼                       ▼                       ▼
┌──────────┐         ┌──────────┐           ┌──────────────┐
│PostgreSQL│         │  Redis   │           │ Message bus  │
│(primary) │◀───────▶│ cache +  │           │ NATS/Kafka   │
│ + replica│         │ rate-lim │           │ + outbox     │
└──────────┘         └──────────┘           └──────┬───────┘
                                                   │
                       ┌───────────────┬───────────┴──────────┐
                       ▼               ▼                      ▼
                  ┌─────────┐   ┌─────────────┐      ┌──────────────┐
                  │ Workers │   │ Scheduler   │      │ Analytics    │
                  │ (queue) │   │ (cron)      │      │ pipeline     │
                  └─────────┘   └─────────────┘      │ (CH/BigQuery)│
                                                     └──────────────┘
```

## 2.2 Сервисы / модули (modular monolith → splittable)

Стартую с **modular monolith** (один deployable, чёткие domain boundaries). Это правильный выбор для текущего масштаба и команды; распилить на микросервисы можно позже по линиям модулей.

| Модуль | Ответственность | Когда выносить отдельно |
|---|---|---|
| **identity** | users, phone normalization, deferred linking, sessions | Никогда (ядро) |
| **loyalty-engine** | rule evaluation (3+1, 10+1, bonus) | При >5M transactions/день |
| **wallet** | cashback balances, expirations | Вместе с loyalty |
| **prepaid** | пакеты, списание, refund | Вместе с loyalty |
| **campaign** | CRUD акций, scheduling, A/B | Вместе с loyalty |
| **notification** | templates, send-time, delivery | **Сразу выносим как worker** |
| **billing** (SaaS) | подписки кофеен | Отдельно (Stripe) |
| **bot-gateway** | Telegram updates, webhooks | Отдельно (i/o-bound) |
| **audit** | append-only log, fraud signals | Можно выносить позже |
| **analytics-ingest** | CDC из Postgres → ClickHouse | Отдельно (batch) |

## 2.3 Telegram Bot architecture

**Webhook mode**, не long polling. Long polling — debug only.

```
Telegram → HTTPS webhook → bot-gateway (FastAPI/aiogram3 or grammy/Node)
                              │
                              ├─ deduplicate update_id (Redis SETNX, TTL 1h)
                              ├─ extract user (telegram_id, phone if shared)
                              ├─ identify_or_link_user()
                              ├─ route to handler
                              └─ enqueue side-effects (notifications, analytics)
```

**Критично:**
- Webhook handler должен ответить Telegram за **<5s**, иначе retry. Тяжёлую работу — в очередь.
- `update_id` дедуплицируется (Telegram ретраит при таймауте).
- Один пользователь — `(telegram_id, phone_e164)`. Один из них может отсутствовать → см. **Deferred Identity**.
- Inline-кнопки → `callback_data` ≤ 64 байта. Используем компактные коды + Redis-mapping для длинных payload.

## 2.4 Нужен ли queue system? — **Да, обязательно.**

Кейсы:
- **Notifications fan-out** (каждое утро отправить 50k сообщений; Telegram лимит ~30 msg/sec на бота → нужна аккуратная rate-limited очередь).
- **Async после транзакции** (после `purchase` → пересчёт progress → trigger notification → analytics event → audit).
- **Retries** при сбоях Telegram API.
- **Backpressure** при пиках (утренний rush 8–10:00).

**Outbox pattern** обязателен: транзакция в БД и публикация в queue должны быть атомарными. Запись в `outbox_events` идёт в той же DB-транзакции, что и бизнес-операция; отдельный publisher вычитывает outbox и пушит в шину.

## 2.5 Нужен ли cron/scheduler? — **Да.**

Задачи:
- **Daily motivational** (08:00 в timezone клиента) — fan-out по сегменту.
- **Expiration jobs** — bonus coffee истёк → списать; cashback просрочен → списать.
- **Re-engagement** — клиент не был 14/30/60 дней.
- **Prepaid expiry warnings** — пакет истекает через 7 дней.
- **Daily/weekly reports** для owner.
- **Monthly billing** SaaS подписок.

Реализация: **Temporal.io** (durable workflows, идеален для долгих flows типа expirations) либо проще — **APScheduler / BullMQ + cron** для MVP. Не использовать `cron` контейнера — нет HA, нет визибилити.

## 2.6 Notification service architecture

Это **отдельный domain**, не «функция в боте».

```
[Trigger] ──► [Notification Builder] ──► [Send-time optimizer] ──► [Rate-limited sender]
   │                  │                          │                         │
   │                  │                          │                         ├─ Telegram
   │                  │                          │                         └─ SMS fallback (V2)
   │                  ▼                          ▼
   │            templates (Jinja, i18n)     user timezone, frequency caps
   │
   ├─ event-driven (purchase made, level up, package opened)
   └─ scheduled (daily motivational, expirations)
```

Слои:
1. **Triggers** — события домена (`PurchaseRecorded`, `FreeCoffeeUnlocked`, `PackageLowBalance`) либо cron.
2. **Audience resolver** — кому отправлять (segment query).
3. **Template renderer** — Jinja-like с i18n; A/B варианты.
4. **Frequency cap** — не более N сообщений в день/неделю на пользователя.
5. **Quiet hours** — не слать ночью (по timezone клиента).
6. **Send-time optimization** (V2) — ML или эвристика на основе истории посещений.
7. **Sender** — token-bucket rate-limit (Telegram: 30/sec global, 1/sec per chat); retry с exp backoff; dead-letter queue.
8. **Delivery log** — `notification_log` со статусом и `unsubscribe_reason`.

## 2.7 Event-driven подход

Domain events (через outbox → bus):

```
PurchaseRecorded { user_id, branch_id, products[], total, ts }
FreeCoffeeUnlocked { user_id, campaign_id, ts }
FreeCoffeeRedeemed { user_id, campaign_id, transaction_id, ts }
PrepaidPackageOpened { user_id, package_id, qty, paid_amount }
PrepaidConsumed { user_id, package_id, remaining_qty }
CashbackEarned { user_id, amount, source_tx_id }
CashbackSpent { user_id, amount, target_tx_id }
TransactionRefunded { user_id, transaction_id, reason }
UserLinked { user_id, telegram_id }
```

Подписчики: notification, analytics, audit, fraud-detection, gamification (V2).

## 2.8 Caching strategy

| Слой | Что | TTL | Инвалидация |
|---|---|---|---|
| Redis | user profile by `telegram_id` | 5 min | on update |
| Redis | active campaigns per branch | 1 min | on campaign change |
| Redis | progress projection (`progress_view`) | до next purchase | по событию |
| Redis | bot session/FSM state | 30 min | по завершении flow |
| Redis | rate-limit counters (token bucket) | 1 min sliding | natural |
| App memory | template metadata | весь lifetime pod, инвалидация по pub/sub | |
| CDN | статика admin-панели | long | on deploy |

**Критично:** балансы (cashback, prepaid) **никогда не читаем из кэша как source-of-truth для списания**. Только из БД с `SELECT … FOR UPDATE` либо через atomic `UPDATE ... RETURNING`. Кэш — только для read-only отображения.

---

# 3. DATABASE DESIGN

**Выбор:** PostgreSQL 16+. Аргументы: транзакции, JSONB для гибкости campaign rules, partial indexes, generated columns, pg_partman для партиционирования, `LISTEN/NOTIFY` для outbox, расширения (`pgcrypto`, `citext`, `pg_trgm`).

Принципы:
- Деньги — `NUMERIC(12,2)`, никогда `float`.
- Все timestamps — `TIMESTAMPTZ`, хранить UTC.
- Soft delete (`deleted_at`) для пользовательских сущностей; hard delete для технических.
- `created_at`, `updated_at` везде.
- UUID v7 (k-sortable) для PK во всех бизнес-таблицах. Telegram_id — `BIGINT`.
- Все денежные операции — append-only ledger, балансы — проекции.

## 3.1 Tenancy

Multi-tenant на уровне БД: одна БД, поле `tenant_id` (= `coffee_chain_id`) во всех таблицах + RLS (Row Level Security). Клиенты при сравнении телефонов уникальны **в рамках tenant**.

```sql
CREATE TABLE tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug CITEXT UNIQUE NOT NULL,
  plan TEXT NOT NULL CHECK (plan IN ('starter','growth','chain')),
  status TEXT NOT NULL CHECK (status IN ('active','suspended','trial','churned')),
  default_currency CHAR(3) NOT NULL DEFAULT 'USD',
  default_timezone TEXT NOT NULL DEFAULT 'UTC',
  settings JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 3.2 Branches

```sql
CREATE TABLE branches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  address TEXT,
  geo POINT,
  timezone TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','closed','paused')),
  opening_hours JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);
CREATE INDEX idx_branches_tenant ON branches(tenant_id) WHERE status = 'active';
```

## 3.3 Users (clients)

Ключевое: **identity by phone**, telegram_id опционален.

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  phone_e164 TEXT NOT NULL,                    -- +998901234567
  phone_hash BYTEA GENERATED ALWAYS AS (digest(phone_e164,'sha256')) STORED,
  full_name TEXT,
  telegram_id BIGINT,                          -- nullable! linking deferred
  telegram_username TEXT,
  language CHAR(2) NOT NULL DEFAULT 'ru',
  timezone TEXT,
  birthday DATE,
  status TEXT NOT NULL CHECK (status IN ('active','blocked','merged')) DEFAULT 'active',
  notify_opt_in BOOLEAN NOT NULL DEFAULT TRUE,
  notify_quiet_from TIME,
  notify_quiet_to TIME,
  source TEXT,                                  -- 'admin','self','import'
  first_seen_at TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);

-- ОБЯЗАТЕЛЬНО: телефон уникален в рамках tenant
CREATE UNIQUE INDEX uq_users_tenant_phone
  ON users (tenant_id, phone_e164) WHERE deleted_at IS NULL;

-- Telegram_id уникален в рамках tenant (один клиент в одном TG аккаунте на кофейню)
CREATE UNIQUE INDEX uq_users_tenant_tgid
  ON users (tenant_id, telegram_id) WHERE telegram_id IS NOT NULL AND deleted_at IS NULL;

-- Поиск по последним цифрам телефона (бариста ввёл 4 цифры)
CREATE INDEX idx_users_phone_trgm ON users USING gin (phone_e164 gin_trgm_ops);

-- Активные клиенты для notification fan-out
CREATE INDEX idx_users_active_notify ON users (tenant_id)
  WHERE deleted_at IS NULL AND notify_opt_in AND telegram_id IS NOT NULL;
```

**Почему phone_e164 + uniq per tenant:** клиент может быть в нескольких сетях независимо. **phone_hash** — для быстрого privacy-safe поиска при импорте.

## 3.4 Admins / Staff (employees)

```sql
CREATE TABLE staff (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  email CITEXT,
  phone_e164 TEXT,
  full_name TEXT NOT NULL,
  telegram_id BIGINT,
  role TEXT NOT NULL CHECK (role IN ('owner','manager','barista','accountant','support')),
  status TEXT NOT NULL CHECK (status IN ('active','suspended','left')) DEFAULT 'active',
  password_hash TEXT,             -- argon2id для admin web
  totp_secret BYTEA,              -- 2FA для owner/manager
  pin_hash TEXT,                  -- короткий PIN для бариста в боте
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);

CREATE TABLE staff_branches (
  staff_id UUID REFERENCES staff(id) ON DELETE CASCADE,
  branch_id UUID REFERENCES branches(id) ON DELETE CASCADE,
  PRIMARY KEY (staff_id, branch_id)
);

CREATE TABLE roles (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL
);
CREATE TABLE permissions (
  code TEXT PRIMARY KEY,
  description TEXT
);
CREATE TABLE role_permissions (
  role_code TEXT REFERENCES roles(code) ON DELETE CASCADE,
  permission_code TEXT REFERENCES permissions(code) ON DELETE CASCADE,
  PRIMARY KEY (role_code, permission_code)
);
```

Permissions примеры: `purchase.create`, `purchase.refund`, `prepaid.open`, `bonus.grant`, `campaign.manage`, `analytics.view`, `staff.manage`, `audit.view`.

## 3.5 Products

```sql
CREATE TABLE products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  sku TEXT,
  name TEXT NOT NULL,
  category TEXT,                   -- 'coffee','tea','food','merch'
  size TEXT,                        -- 'S','M','L'
  base_price NUMERIC(12,2) NOT NULL CHECK (base_price >= 0),
  is_loyalty_eligible BOOLEAN NOT NULL DEFAULT TRUE, -- участвует ли в 10+1
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, sku)
);
CREATE INDEX idx_products_tenant_active ON products(tenant_id) WHERE is_active;
```

## 3.6 Campaigns + rules (loyalty-engine core)

Главная архитектурная мысль: **все типы акций — это конфигурация одного движка**.

```sql
CREATE TABLE campaigns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  code TEXT NOT NULL,                       -- 'COFFEE_10_PLUS_1'
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN
    ('punchcard','prepaid','cashback','bonus_item','tiered_status','first_purchase','birthday')),
  status TEXT NOT NULL CHECK (status IN ('draft','active','paused','archived')),
  starts_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ends_at TIMESTAMPTZ,
  priority INT NOT NULL DEFAULT 100,        -- порядок применения
  stackable BOOLEAN NOT NULL DEFAULT FALSE, -- можно ли с другими
  rules JSONB NOT NULL,                     -- см. ниже
  created_by UUID REFERENCES staff(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, code)
);

CREATE INDEX idx_campaigns_active ON campaigns(tenant_id)
  WHERE status = 'active';

CREATE TABLE campaign_branches (        -- какие точки участвуют
  campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
  branch_id UUID REFERENCES branches(id) ON DELETE CASCADE,
  PRIMARY KEY (campaign_id, branch_id)
);

CREATE TABLE campaign_products (        -- какие продукты участвуют
  campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
  product_id UUID REFERENCES products(id) ON DELETE CASCADE,
  PRIMARY KEY (campaign_id, product_id)
);
```

### Примеры `rules` (JSONB):

**10+1 punchcard:**
```json
{
  "type": "punchcard",
  "trigger": {"product_category": "coffee", "min_size": "M"},
  "stamps_required": 10,
  "reward": {"kind": "free_product", "category": "coffee", "max_size": "M"},
  "max_active_cards": 1,
  "expires_after_days": 90,
  "cooldown_minutes": 5
}
```

**Cashback 5%:**
```json
{
  "type": "cashback",
  "rate": 0.05,
  "applies_to": {"all_products": true},
  "wallet": "default",
  "expires_after_days": 180,
  "min_transaction": 0
}
```

**Bonus item:**
```json
{
  "type": "bonus_item",
  "trigger": {"product_id": "uuid-cappuccino-L"},
  "reward": {"product_id": "uuid-croissant", "discount_pct": 100},
  "max_per_day": 1
}
```

JSONB + JSON-schema validation в коде даёт гибкость **без миграций** при появлении новых типов.

## 3.7 Loyalty progress (punchcard state)

```sql
CREATE TABLE loyalty_cards (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  campaign_id UUID NOT NULL REFERENCES campaigns(id),
  stamps INT NOT NULL DEFAULT 0 CHECK (stamps >= 0),
  stamps_required INT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open','complete','redeemed','expired')) DEFAULT 'open',
  opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  redeemed_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  redeemed_tx_id UUID,                      -- ссылка на транзакцию выдачи
  version INT NOT NULL DEFAULT 0,           -- optimistic locking
  UNIQUE (user_id, campaign_id, status) DEFERRABLE INITIALLY DEFERRED
);
-- Активная карта: только одна 'open' или 'complete' на (user, campaign)
CREATE UNIQUE INDEX uq_active_card
  ON loyalty_cards (user_id, campaign_id)
  WHERE status IN ('open','complete');

CREATE INDEX idx_cards_user ON loyalty_cards(user_id);
CREATE INDEX idx_cards_expiring ON loyalty_cards(expires_at)
  WHERE status IN ('open','complete');
```

## 3.8 Prepaid packages

```sql
CREATE TABLE prepaid_packages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  user_id UUID NOT NULL REFERENCES users(id),
  campaign_id UUID REFERENCES campaigns(id),  -- из какой акции продан
  product_scope JSONB NOT NULL,                -- какие продукты можно списывать
  qty_total INT NOT NULL CHECK (qty_total > 0),
  qty_remaining INT NOT NULL CHECK (qty_remaining >= 0),
  amount_paid NUMERIC(12,2) NOT NULL,
  currency CHAR(3) NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','exhausted','refunded','expired','suspended')),
  opened_by UUID REFERENCES staff(id),
  opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ,
  closed_at TIMESTAMPTZ,
  version INT NOT NULL DEFAULT 0,
  CHECK (qty_remaining <= qty_total)
);
CREATE INDEX idx_prepaid_user_active ON prepaid_packages(user_id)
  WHERE status = 'active';
CREATE INDEX idx_prepaid_expiring ON prepaid_packages(expires_at)
  WHERE status = 'active';
```

## 3.9 Cashback wallets

Один wallet на пользователя на валюту. Балансы считаем как проекцию `wallet_entries` (event-sourced).

```sql
CREATE TABLE cashback_wallets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  user_id UUID NOT NULL REFERENCES users(id),
  currency CHAR(3) NOT NULL,
  balance NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (balance >= 0), -- проекция
  version INT NOT NULL DEFAULT 0,
  UNIQUE (user_id, currency)
);

CREATE TABLE wallet_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wallet_id UUID NOT NULL REFERENCES cashback_wallets(id),
  amount NUMERIC(12,2) NOT NULL,           -- + earn / - spend
  kind TEXT NOT NULL CHECK (kind IN ('earn','spend','expire','adjust','refund')),
  source_type TEXT NOT NULL,                -- 'transaction','manual','expiration'
  source_id UUID,
  expires_at TIMESTAMPTZ,                   -- для FIFO списания просроченного
  idempotency_key TEXT NOT NULL,
  created_by UUID REFERENCES staff(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (wallet_id, idempotency_key)
);
CREATE INDEX idx_wallet_entries_wallet_ts ON wallet_entries(wallet_id, created_at);
CREATE INDEX idx_wallet_entries_expiring ON wallet_entries(expires_at)
  WHERE kind = 'earn' AND expires_at IS NOT NULL;
```

## 3.10 Transactions + ledger (heart of the system)

```sql
CREATE TABLE transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  branch_id UUID NOT NULL REFERENCES branches(id),
  user_id UUID NOT NULL REFERENCES users(id),
  staff_id UUID NOT NULL REFERENCES staff(id),
  type TEXT NOT NULL CHECK (type IN
    ('purchase','redeem_free','prepaid_consume','manual_grant','manual_revoke','refund')),
  status TEXT NOT NULL CHECK (status IN ('pending','committed','reversed')) DEFAULT 'committed',
  total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
  currency CHAR(3) NOT NULL,
  payment_method TEXT,                          -- 'cash','card','prepaid','free'
  source TEXT NOT NULL,                          -- 'staff_bot','admin_panel','pos_api'
  device_id TEXT,
  geo POINT,
  client_request_id TEXT NOT NULL,               -- UUID от клиента (бариста бота) — idempotency
  reversed_by UUID,                              -- ссылка на refund-транзакцию
  reverses UUID REFERENCES transactions(id),
  notes TEXT,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, client_request_id)         -- IDEMPOTENCY KEY
);

CREATE INDEX idx_tx_user_ts ON transactions(user_id, created_at DESC);
CREATE INDEX idx_tx_branch_ts ON transactions(branch_id, created_at DESC);
CREATE INDEX idx_tx_staff_ts ON transactions(staff_id, created_at DESC);
-- Партиционирование по created_at (range, monthly) с pg_partman.
```

```sql
CREATE TABLE transaction_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
  product_id UUID REFERENCES products(id),
  qty INT NOT NULL CHECK (qty > 0),
  unit_price NUMERIC(12,2) NOT NULL,
  discount NUMERIC(12,2) NOT NULL DEFAULT 0,
  paid_with TEXT NOT NULL,                       -- 'money','prepaid','free'
  prepaid_package_id UUID REFERENCES prepaid_packages(id),
  loyalty_card_id UUID REFERENCES loyalty_cards(id)
);
```

```sql
-- Универсальный append-only ledger всех «последствий» транзакции
CREATE TABLE ledger_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  user_id UUID NOT NULL,
  transaction_id UUID NOT NULL REFERENCES transactions(id),
  account TEXT NOT NULL,         -- 'wallet:cashback','card:<campaign_id>','prepaid:<pkg_id>'
  delta NUMERIC(14,4) NOT NULL,  -- + или -
  unit TEXT NOT NULL,            -- 'currency','stamp','coffee_unit'
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ledger_user ON ledger_entries(user_id, created_at DESC);
CREATE INDEX idx_ledger_account ON ledger_entries(account, created_at DESC);
```

## 3.11 Outbox (for queue)

```sql
CREATE TABLE outbox_events (
  id BIGSERIAL PRIMARY KEY,
  tenant_id UUID NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id UUID NOT NULL,
  type TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ
);
CREATE INDEX idx_outbox_unpub ON outbox_events(id) WHERE published_at IS NULL;
```

## 3.12 Notifications

```sql
CREATE TABLE notification_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID,                 -- NULL = global default
  code TEXT NOT NULL,
  language CHAR(2) NOT NULL,
  channel TEXT NOT NULL CHECK (channel IN ('telegram','sms','push')),
  body TEXT NOT NULL,
  buttons JSONB,
  variant TEXT NOT NULL DEFAULT 'A',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (tenant_id, code, language, variant)
);

CREATE TABLE notification_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID,
  user_id UUID REFERENCES users(id),
  template_code TEXT NOT NULL,
  scheduled_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued','sent','failed','skipped','cancelled')) DEFAULT 'queued',
  attempt INT NOT NULL DEFAULT 0,
  context JSONB NOT NULL,
  sent_at TIMESTAMPTZ,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_notify_due ON notification_jobs(scheduled_at) WHERE status = 'queued';

CREATE TABLE notification_log (   -- партиционированная по месяцам
  id BIGSERIAL,
  user_id UUID NOT NULL,
  template_code TEXT NOT NULL,
  channel TEXT NOT NULL,
  status TEXT NOT NULL,
  delivered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  meta JSONB
) PARTITION BY RANGE (delivered_at);
```

## 3.13 Audit log (append-only)

```sql
CREATE TABLE audit_logs (
  id BIGSERIAL,
  tenant_id UUID NOT NULL,
  actor_type TEXT NOT NULL,         -- 'staff','system','customer'
  actor_id UUID,
  action TEXT NOT NULL,             -- 'transaction.create','user.merge','campaign.update'
  target_type TEXT,
  target_id UUID,
  before JSONB,
  after JSONB,
  ip INET,
  user_agent TEXT,
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
) PARTITION BY RANGE (created_at);
```

REVOKE UPDATE/DELETE on `audit_logs` от роли приложения — только INSERT.

## 3.14 Anti-fraud signals

```sql
CREATE TABLE fraud_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  user_id UUID,
  staff_id UUID,
  branch_id UUID,
  kind TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('low','medium','high','critical')),
  payload JSONB NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open','investigating','dismissed','confirmed')) DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 3.15 Read-models / projections

Для UI бота строим `user_dashboard_view` (Postgres MATERIALIZED VIEW либо обычная таблица-проекция, обновляемая по событиям):

```sql
CREATE TABLE user_dashboard (
  user_id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  stamps_total INT NOT NULL DEFAULT 0,         -- по активной 10+1 карте
  stamps_required INT NOT NULL DEFAULT 0,
  free_coffees_available INT NOT NULL DEFAULT 0,
  cashback_balance NUMERIC(12,2) NOT NULL DEFAULT 0,
  prepaid_remaining INT NOT NULL DEFAULT 0,
  last_visit_at TIMESTAMPTZ,
  last_visit_branch_id UUID,
  visits_30d INT NOT NULL DEFAULT 0,
  rfm_segment TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

# 4. BUSINESS LOGIC

## 4.1 Core invariants

1. **Каждое финансовое/loyalty изменение** = транзакция в БД + запись в `transactions` + минимум 0..N записей в `ledger_entries` + 0..N изменений проекций — **в одной DB-транзакции**.
2. **Идемпотентность** через `client_request_id` (UUID, генерится на клиенте бариста-бота при первом нажатии). Повторная отправка → возвращаем тот же результат.
3. **Optimistic locking** через `version` в `loyalty_cards`, `prepaid_packages`, `cashback_wallets`.
4. **Pessimistic lock** для prepaid списания: `SELECT ... FOR UPDATE` на `prepaid_packages`.

## 4.2 Punchcard 10+1 — алгоритм

```
input: user_id, branch_id, staff_id, products[], client_request_id

BEGIN TRANSACTION;
  -- 1. idempotency
  IF EXISTS (SELECT 1 FROM transactions WHERE client_request_id = $crid)
     RETURN existing result;

  -- 2. find applicable active campaigns of type punchcard
  campaigns := SELECT * FROM campaigns
               WHERE status='active' AND type='punchcard'
                 AND (ends_at IS NULL OR ends_at > now())
                 AND branch participates
                 AND product matches rules.trigger;

  -- 3. for each eligible product line:
  FOR each unit in expanded_lines:
     card := SELECT FOR UPDATE FROM loyalty_cards
             WHERE user_id=? AND campaign_id=? AND status='open';
     IF NOT FOUND:
        INSERT card (status='open', stamps=0, expires_at=now()+INTERVAL N DAYS);
     UPDATE card SET stamps = stamps + 1, version = version + 1;
     IF stamps == stamps_required:
        UPDATE card SET status='complete', completed_at=now();
        emit FreeCoffeeUnlocked event;

  -- 4. write transaction + items + ledger entries
  INSERT INTO transactions (...);
  INSERT INTO transaction_items (...);
  INSERT INTO ledger_entries (account='card:<id>', delta=+1, unit='stamp', ...);

  -- 5. update user_dashboard projection
  UPDATE user_dashboard SET stamps_total=..., free_coffees_available=...;

  -- 6. outbox
  INSERT INTO outbox_events (PurchaseRecorded);

COMMIT;
```

**Edge-cases:**
- **Клиент купил 3 кофе одной транзакцией при 8/10:** даём 3 stamp, карта закрывается на 10/10 → новая открывается на 1/10. Алгоритм сам обрабатывает (loop). 11-й kофе — НЕ автоматический free; free coffee redeem — отдельное действие (бариста должен явно нажать «использовать бесплатный»).
- **Бариста забыл начислить:** есть кнопка «retro-add» с лимитом 24h и audit log.
- **Клиент сменил телефон:** `user_merge` (см. ниже).

## 4.3 Free coffee redeem

```
BEGIN;
  card := SELECT FOR UPDATE FROM loyalty_cards
          WHERE user_id=? AND status='complete'
          ORDER BY completed_at LIMIT 1;
  IF NOT FOUND: RAISE 'no free coffee available';

  IF expired: UPDATE card SET status='expired'; RAISE 'expired';

  INSERT transactions (type='redeem_free', total=0, ...);
  INSERT transaction_items (paid_with='free', loyalty_card_id=card.id, ...);
  UPDATE card SET status='redeemed', redeemed_tx_id=<tx>, redeemed_at=now();
  INSERT ledger_entries (account='card:<id>', delta=-1, unit='coffee_unit');
  UPDATE user_dashboard SET free_coffees_available -= 1;
  outbox(FreeCoffeeRedeemed);
COMMIT;
```

## 4.4 Prepaid package

**Открытие:**
```
- проверка оплаты (cash/card зафиксирован);
- INSERT prepaid_packages (qty_total=10, qty_remaining=10, amount_paid=…, expires_at=now()+180d);
- transaction(type='purchase', metadata.package_id);
- ledger(account='prepaid:<id>', delta=+10, unit='coffee_unit');
- notify клиента: «вы открыли пакет на 10 кофе».
```

**Списание:**
```
BEGIN;
  pkg := SELECT FOR UPDATE FROM prepaid_packages
         WHERE user_id=? AND status='active' AND product allowed
         ORDER BY expires_at NULLS LAST LIMIT 1;       -- FIFO по истечению
  IF NOT FOUND: RAISE 'no package';
  IF qty_remaining == 0: RAISE 'exhausted';            -- защита; не должно
  UPDATE pkg SET qty_remaining = qty_remaining - 1, version=version+1
         WHERE id=? AND qty_remaining > 0;             -- guard
  IF affected = 0: RETRY (concurrent consume);
  IF qty_remaining == 0: UPDATE pkg SET status='exhausted', closed_at=now();
  INSERT transactions(type='prepaid_consume', total=0);
  INSERT items(paid_with='prepaid', prepaid_package_id=pkg.id);
  INSERT ledger(account='prepaid:<id>', delta=-1, unit='coffee_unit');
  outbox(PrepaidConsumed);
COMMIT;
```

**Edge-cases:**
- **Race на двух кассах одновременно:** `SELECT FOR UPDATE` сериализует. Альтернатива — `UPDATE … WHERE qty_remaining > 0 RETURNING` (более compact и atomic).
- **Истечение пакета с остатком:** cron находит `expires_at < now()` AND `qty_remaining > 0` → переводит в `expired`. Правило бизнеса: остаток сгорает или мигрирует в cashback (зависит от tenant settings).
- **Refund:** клиент просит вернуть деньги за неиспользованный пакет → создаём `refund` транзакцию, рассчитываем pro-rata, переводим в `refunded`.

## 4.5 Cashback

**Earn (после purchase):**
```
amount := round(total * rate, 2)   -- bankers rounding
INSERT wallet_entries (kind='earn', amount=+amount, expires_at=now()+180d, idempotency_key=tx_id);
UPDATE cashback_wallets SET balance = balance + amount, version=version+1;
```

**Spend:**
```
BEGIN;
  wallet := SELECT FOR UPDATE WHERE id=?;
  IF wallet.balance < requested: RAISE 'insufficient';
  -- FIFO списание по earned entries (чтобы expiration работал корректно);
  remaining := requested;
  FOR earn IN earns ORDER BY created_at:
      take := min(earn.unspent, remaining);
      INSERT wallet_entries (kind='spend', amount=-take, source_id=earn.id);
      remaining -= take;
      IF remaining == 0: BREAK;
  UPDATE wallet SET balance = balance - requested;
COMMIT;
```

**Expiration cron:**
- Каждый день находит `wallet_entries kind='earn' AND expires_at < now() AND unspent > 0` → INSERT compensating `kind='expire'`.
- Уведомляет пользователя за 7 дней до сгорания.

## 4.6 Idempotency design

- На клиенте бариста-бота при нажатии «Начислить» генерируется UUID v4 = `client_request_id`.
- При retry (потеря соединения) тот же UUID → backend отвечает с предыдущим результатом (cache на 24h в Redis + uniq-constraint в БД как final guard).
- Idempotency-Key и для admin web (HTTP header `Idempotency-Key`).

## 4.7 Refund / rollback

Никогда не делаем `UPDATE transactions SET status='reversed'` без compensating entries. Refund — это **новая** транзакция type=`refund`, ссылающаяся `reverses` на исходную. Применяет inverse изменения:
- если был +1 stamp → −1 stamp (если карта стала redeemed-after — refund невозможен без отдельного approval);
- если +cashback → −cashback (compensating entry с idempotency `refund:<tx_id>`);
- если списан prepaid → +1 в qty_remaining (пакет может быть `exhausted` → переводится обратно в `active`).

Refund возможен только через `purchase.refund` permission и обязательно требует reason.

## 4.8 Duplicate transaction protection

Слои:
1. `client_request_id` UNIQUE.
2. Cooldown per (user, campaign): `cooldown_minutes` в rules — нельзя получить stamp 2 раза в минуту (защита от двойного нажатия).
3. Daily cap per user (опционально): не более N stamps в сутки.
4. Velocity check (fraud): >X транзакций за 1 час → флаг.

## 4.9 Race conditions

| Сценарий | Защита |
|---|---|
| Двойной prepaid consume | `SELECT FOR UPDATE` или conditional UPDATE с guard |
| Stamp одновременно на 2 кассах | Per-card `SELECT FOR UPDATE` + version |
| Wallet spend дважды | Wallet `SELECT FOR UPDATE` + idempotency |
| Linking — два user-а с одним телефоном | Unique index на `(tenant_id, phone_e164)` + `user_merge` процедура |
| Webhook update пришёл дважды | Redis SETNX по `update_id` |
| Outbox publisher двойная отправка | At-least-once + consumer-side idempotency (event_id) |

## 4.10 Fraud prevention

**Источник угрозы № 1 — недобросовестный бариста:**
- Создаёт «фантомного» клиента и сам себе начисляет purchases → free coffee.
- Активирует prepaid за себя.
- Refund-ит чужие транзакции.

**Контроль:**
1. **Геолокация / device binding** — бариста-бот привязан к конкретной точке + диапазону геолокации (опционально); транзакции вне геофенса флагуются.
2. **Velocity rules** — staff_id выдал >N stamps за час одному user_id; >K новых клиентов за день.
3. **Connection patterns** — staff X стабильно работает с тем же user Y (cluster в graph).
4. **Refund cap** — staff может рефандить не более N$ в день без manager approval.
5. **PIN/2FA** для критических действий (refund, prepaid open).
6. **Owner-side review** — еженедельный отчёт с топ-выбросами.
7. **Owner-only blocked operations** — нельзя выдать free coffee без active purchase транзакции (т.е. бариста физически должен прошагать «покупку»).
8. **Per-user/per-staff анализ** — ML-модель в V2.

## 4.11 Multi-branch consistency

- Все балансы привязаны к `tenant_id`, не к branch — клиент может накапливать stamps в одной точке, использовать в другой (если `campaign_branches` allows).
- При сетевом сбое одной точки бариста работает в **degraded mode**: бариста-бот пишет в локальный буфер (offline queue в Telegram-боте через FSM-state) и синхронизирует при восстановлении. Конфликты разрешаются через idempotency_key. **MVP:** требовать online; offline — V2.

## 4.12 Edge-cases (систематически)

1. **Customer без telegram_id** добавлен админом → транзакции работают; уведомления — через SMS fallback (V2) либо отложены до linking.
2. **Клиент дважды зарегистрирован** (опечатка в телефоне) → admin merge (`user_merge` SP: переносит транзакции, складывает балансы, ставит `status='merged'` и `merged_into_user_id`).
3. **Клиент сменил номер** → manual rebind через support permission; audit log обязателен.
4. **Кампания изменена** в момент начисления → loyalty card помнит `stamps_required` на момент открытия (snapshot полей при INSERT).
5. **Кампания stack-overlap** — при `stackable=false` берётся одна с max `priority`.
6. **Бариста начислил продукт, который не loyalty-eligible** → нет stamp, нет cashback; видно в UI.
7. **Удаление продукта** во время активной prepaid → prepaid scope заморожен (snapshot в `product_scope` JSONB).
8. **Возврат после free coffee redeemed** → редкий кейс; политика: free coffee не возвращается в stamps (только compensating cashback по решению owner).
9. **Часовые пояса** — каждая ветка имеет timezone, все «дневные» лимиты считаются по timezone branch; пользовательские уведомления — по timezone user.
10. **Дата рождения** — bonus-кампания «free coffee on birthday» с tolerance ±1 день.
11. **Уведомление в quiet hours** → reschedule на ближайшее окно.
12. **Telegram заблокировал бот** (user blocked) → ставим `notify_opt_in=false` автоматически.
13. **Удаление пользователя по GDPR** — `user.delete()` обнуляет PII, оставляет анонимизированный audit trail (для finance).

---

# 5. TELEGRAM BOT UX

## 5.1 Identity model (главное)

Идея: клиент существует **до** контакта с ботом. Админ заносит телефон → `user` создан, `telegram_id=NULL`. Когда клиент откроет бот, мы должны **автоматически связать**.

**Linking flow (deferred):**

```
1. Клиент открывает бот → /start
2. Bot: "Поделись номером, чтобы я нашёл твою карту лояльности"
   → Telegram native button [Share contact] (KeyboardButton.request_contact)
3. Клиент жмёт → Telegram отправляет phone_number и user_id (only own number, нельзя подделать)
4. Backend: normalize phone to E.164;
   SELECT user FROM users WHERE phone_e164=? AND telegram_id IS NULL → link
                          OR phone_e164=? AND telegram_id=? → already linked
                          OR phone_e164=? AND telegram_id<>? → conflict (другой TG аккаунт)
                          OR не найден → create new user, source='self'
5. После linking — показать дашборд.
```

Почему **только** `request_contact`, а не ввод текста: Telegram гарантирует, что переданный phone — это телефон **этого** аккаунта. Это бесплатная **верификация номера**. Плюс защита от user enumeration.

## 5.2 Onboarding (cold start)

```
[/start]
 ├─ есть deep-link payload? (например /start ref_<branch_id>)
 │   → запоминаем источник
 ├─ показать приветствие + brand intro (1 экран)
 ├─ кнопка [Поделиться номером]
 ├─ после shared:
 │   ├─ если linked — "Привет, <name>! У тебя 7/10 ☕"
 │   └─ если new — "Добро пожаловать! Это твоя цифровая карта"
 ├─ предложить включить уведомления (с прозрачным opt-in)
 └─ показать главный дашборд
```

Принципы:
- **0 шагов, требующих набора текста** в onboarding.
- Brand-customisable: логотип, accent color, имя сети (V2).
- Progressive disclosure: не показывать сразу всё, только релевантное (если у клиента 0/10 — не пугать всеми механиками сразу).

## 5.3 Меню (main keyboard)

Reply keyboard всегда видим (persistent), inline — для контекста.

```
 ┌──────────────────────────────────┐
 │ ☕ Моя карта   🎁 Бонусы          │
 │ 💰 Кэшбэк     📦 Мой пакет        │
 │ 📜 История    ❓ Помощь           │
 └──────────────────────────────────┘
```

Если у клиента **нет** prepaid — кнопка «📦 Мой пакет» меняется на «📦 Купить пакет» с CTA.

## 5.4 Главный экран (дашборд)

```
☕ Привет, Анна!

🟦🟦🟦🟦🟦🟦🟦⬜⬜⬜  7 / 10
До бесплатного — 3 кофе!

🎁 Доступно бесплатных: 1
💰 Кэшбэк: 3.40 USD
📦 Пакет: 4 / 10 (до 12.06)

[Показать QR-код]  ← для верификации в кофейне
[История покупок]
```

**QR-код** — это identity-token (короткоживущий, 60 секунд) для бариста: сканирует и видит профиль клиента. Альтернатива: бариста ищет по телефону. **MVP может работать без QR**, но QR снижает фрикцию очереди в часы пик.

## 5.5 Progress page

Отдельный экран про активную карту:
- большой визуальный stamp-grid;
- история stamps этой карты (даты, branch);
- срок истечения — «карта активна до 12 июля»;
- если есть несколько активных кампаний — список карт.

## 5.6 Cashback page

- balance с разбивкой по «сгорающему» (которые истекают в ближайшие 30 дней);
- история earn/spend с пагинацией;
- кнопка «Как использовать?» — пояснение.

## 5.7 Free coffee page

- список доступных к погашению (карта 1, кампания «10+1», истекает 30 июля);
- кнопка [Показать бариста] → генерит **redeem code** (4–6 цифр, TTL 5 мин);
- бариста вводит код → списание;
- альтернатива: QR с redeem token.

**Important:** redeem не должен быть «нажми и сразу списано» — это создаёт risk случайного списания. Двухшаговый: клиент показывает code/QR → бариста активно подтверждает.

## 5.8 Prepaid page

- остаток, прогресс, дата истечения;
- история использования;
- кнопка «Купить ещё» → ведёт в кофейню или внутри (V2 со Stripe / Click / Payme).

## 5.9 История

- хронологический фид транзакций;
- фильтр по типу (purchase / refund / free / prepaid);
- инфинит-скролл.

## 5.10 Notifications UX (правила хорошего тона)

| Категория | Когда | Пример | Frequency cap |
|---|---|---|---|
| Transactional | сразу после действия | «✅ +1 кофе. У тебя 8/10» | без лимита |
| Milestone | unlock free | «🎁 У тебя есть бесплатный кофе!» | без лимита |
| Reminder | 7d, 3d, 1d до expire | «⚠ Free coffee сгорит через 3 дня» | 1/событие |
| Daily motivational | 8:00 user-tz, не каждый день | «Доброе утро ☀️ кофе ждёт» | 2–3/неделя max |
| Re-engagement | 14d / 30d отсутствия | «Скучаем 😢 +50% к stamp эту неделю» | 1/30 дней |
| Marketing | акции, новинки | сегментировано | 1/неделя |

UX-правила:
- Каждое сообщение — actionable (есть кнопка/CTA).
- Mute / unsubscribe доступен **в каждом** marketing-сообщении.
- Quiet hours user-configurable.
- A/B тест шаблонов через `variant` поле.
- **Никогда** не дублируем одно и то же сообщение чаще раза в день.

## 5.11 Re-engagement mechanics

- **Comeback bonus** — после 30+ дней отсутствия бот предлагает «вернись — двойные stamps на этой неделе».
- **Streak gamification** (V2) — «5 дней подряд = bonus».
- **Tiered status** (V2) — Bronze/Silver/Gold с накопительными привилегиями.
- **Referral** (V2) — `/start ref_<user_id>` → реферер и приглашённый получают bonus после первой покупки приглашённого.

## 5.12 Staff Bot UX (отдельная роль)

```
[/start] → "Введите PIN" → list of branches assigned → выбор branch для смены
Главный экран:
 [Найти клиента]   ← по телефону / QR / последние 4 цифры
 [Открыть пакет]
 [Refund]   ← требует reason + confirmation
 [Конец смены]   ← печатает summary
```

Найден клиент:
```
Анна, +99890***4567
Карта: 7/10, free: 1, cashback: 3.40, prepaid: 4

[+ Кофе]  [+ Капучино]  [+ Latte]  [+ Custom]
[Использовать free]  [Использовать prepaid]  [Открыть пакет]
[История клиента]
```

Каждое действие требует визуальное confirmation («Начислить 1 кофе Анне? [Да] [Нет]») — снижает количество ошибок и дублей.

---

# 6. ADMIN PANEL (Web)

## 6.1 Roles в админке

- **Owner** — всё.
- **Manager** (одной/нескольких branches) — управление штатом, кампаниями (без billing), аналитика.
- **Accountant** — только финансовые отчёты, refund approval.
- **Support** — поиск клиента, ручные действия (с audit), без массовых рассылок.

## 6.2 Информационная архитектура (sidebar)

1. **Dashboard** (KPI overview)
2. **Customers** (CRM)
3. **Transactions**
4. **Campaigns**
5. **Branches**
6. **Staff & Roles**
7. **Notifications** (templates, broadcasts)
8. **Analytics** (deep-dive)
9. **Audit & Fraud**
10. **Settings** (tenant, integrations, billing)

## 6.3 Dashboard (главный экран)

Виджеты:
- **Today / WoW / MoM:** transactions count, revenue, new customers, active customers, free coffees redeemed, prepaid sold.
- **Live feed** (websocket) — последние 20 транзакций.
- **Top branches** (sparkline).
- **Cohort retention** (heatmap).
- **Loyalty funnel** — кто на каком стадии (0/10, 5/10, 10/10, redeemed).
- **Campaign performance** (incremental revenue per campaign).
- **Anomalies** — 3 верхних fraud-сигнала.

Critical: показывать **incrementality**, а не просто «redemptions». Бизнес хочет знать, сколько лишних покупок принесла программа.

## 6.4 Customers (CRM)

Таблица + drill-down карточка:
- **List view:** phone, name, last visit, visits 30d, LTV, RFM segment, cashback, free coffees, status.
- **Customer card:** профиль + полная история транзакций + активные карты + пакеты + кэшбэк + fraud signals + действия (выдать bonus, заблокировать, merge).

Filters: RFM segment, branch, last visit range, has prepaid, churn risk.

Bulk: export CSV, broadcast to segment.

## 6.5 Campaigns

Wizard-style создание:
1. Type (punchcard / prepaid / cashback / bonus / tiered).
2. Audience (all / segment / new only / has prepaid / churn-risk).
3. Branches (multi-select).
4. Products (filter by category/SKU).
5. Rules (UI-builder, рендерится в JSON).
6. Schedule (start/end, days of week, time of day).
7. Notification templates linked to campaign.
8. Preview & save as draft → activate.

A/B testing: разделение audience на варианты + side-by-side metrics.

## 6.6 Transactions

- Поиск по клиенту, branch, staff, дате, типу.
- Refund с reason → требует подтверждения и записывается в audit.
- Detail view с linked ledger entries (полная картина последствий).

## 6.7 Loyalty metrics (важные!)

- **Activation rate** = % клиентов, открывших ≥1 карту.
- **Stamp velocity** = avg stamps/неделя per active user.
- **Completion rate** = % карт, дошедших до redeem / открытых.
- **Time-to-reward** = median дней.
- **Redemption rate** = % free coffee, реально полученных от unlocked.
- **Repeat-7d / 14d / 30d** до vs после первой stamp.
- **Prepaid attach rate** = % купивших пакет.
- **Cashback redemption ratio** = spent / earned.

## 6.8 Branch management

- KPI per branch: revenue, transactions, redeems, customers.
- Working hours, geo, staff.
- Branch-specific campaign opt-out.

## 6.9 Audit & Fraud

- **Audit search** по actor / action / target / период.
- **Fraud queue** — открытые сигналы, кнопка [Investigate] / [Dismiss] / [Confirm + Block staff].
- **Staff scorecard** — необычные паттерны: refund rate, free coffees выданных, новых клиентов в день.

## 6.10 Notification builder

- WYSIWYG для шаблонов с предпросмотром.
- Переменные: `{first_name}`, `{stamps}`, `{stamps_remaining}`, `{branch_name}`.
- A/B варианты с авто-выбором победителя по open/CTR.
- Broadcasts → segment → schedule → preview send to test user.

## 6.11 UX-приоритеты админки

- **Speed > beauty** — кофейня, оператор кликает быстро в моб-телефоне между чашками.
- **Mobile-first для критичного** — staff должен мочь сделать refund с телефона.
- **Confirmation для деструктивных** действий + undo (когда возможно).
- **Глобальный поиск** (Cmd+K) — мгновенно по customer / transaction / staff.
- **Live updates** через WebSocket — owner смотрит «как идут продажи прямо сейчас».
- **Empty states** с next-action подсказкой.

---

# 7. SCALABILITY

## 7.1 Целевые масштабы

| Метрика | MVP | V2 (1 год) | Scale (3 года) |
|---|---|---|---|
| Tenants (кофеен) | 10 | 200 | 5 000 |
| Branches | 20 | 800 | 20 000 |
| MAU customers | 5k | 200k | 5M |
| Transactions/day | 5k | 500k | 20M peak |
| Notifications/day | 10k | 1M | 50M |
| RPS peak | 50 | 5k | 50k |

## 7.2 Horizontal scaling приложения

- Stateless app pods за L7 LB (NGINX/Traefik / cloud LB).
- Bot-gateway отдельный deployment (i/o-bound, отдельные limits).
- Workers (notification, scheduler, projector) — отдельные deployments.
- Auto-scaling на CPU + custom metrics (queue depth).

## 7.3 Database scaling

**Phase 1 (до ~2k tx/sec):** одна Postgres primary + 1–2 read replicas.
- Read replicas для: admin dashboards, аналитика, поиск клиента, сборка дашборда бота. Все money-paths остаются на primary.

**Phase 2 (~5–10k tx/sec):**
- **Партиционирование** `transactions`, `ledger_entries`, `audit_logs`, `notification_log` по `created_at` (monthly, через pg_partman).
- **Hot/cold** — старые партиции в дешёвом storage / move to ClickHouse.
- **Connection pooler** — pgbouncer (transaction mode).

**Phase 3 (>20k tx/sec):**
- **Sharding по tenant_id** через Citus / собственный shard router.
- Каждый tenant — на одном шарде; cross-tenant операций нет (это упрощение).
- **CQRS:** write на Postgres, read из ClickHouse / Elasticsearch.

## 7.4 Caching strategy при росте

- **Redis Cluster** (sharded) для session/state/rate-limit.
- **CDN** для admin static.
- **Application-level cache** (in-process) для редко меняющихся справочников (templates, role permissions).
- **Materialized projections** — `user_dashboard` обновляется по событиям, читается за 1ms.

## 7.5 Queues / async

- Стартовать с **Redis Streams + BullMQ** или **NATS JetStream** — простые, быстрые.
- Перейти на **Kafka** при >50k events/sec, нужна replayability и долгое хранение.
- **Dead-letter queues** для каждого consumer.
- **Outbox publisher** с at-least-once гарантией.

## 7.6 Notification scale

Telegram limits — **главное узкое место**:
- 30 messages/sec на бота global; 1 msg/sec per chat; ~20/min на одного пользователя.
- Решение: **выделенные боты per tenant** (если нужно >30/sec по одной кофейне) либо **whitelisted commercial bot** (через Telegram BSP).
- **Rate-limited sender** с token bucket, шардирование send-jobs по `tenant_id`.

## 7.7 Async processing patterns

- **Fan-out** для broadcast: разбиваем audience на чанки 1k, кладём в очередь, обрабатываем с throttle.
- **Idempotent consumers** через `(event_id, consumer_name)` уникальность в `processed_events`.
- **Saga pattern** для refund flow (несколько шагов, нужна compensating logic).

## 7.8 Monitoring / observability

- **Metrics:** Prometheus (RED method: rate, errors, duration). Дашборды в Grafana.
- **Tracing:** OpenTelemetry → Tempo/Jaeger. Trace_id пробрасывается из bot webhook через все сервисы.
- **Logging:** structured JSON → Loki/ELK. Поля: `tenant_id`, `user_id`, `trace_id`.
- **Alerts** (главные):
  - error rate > 1%;
  - tx p99 latency > 1s;
  - notification delivery success < 95%;
  - outbox lag > 5 min;
  - DB connections > 80%;
  - fraud signals critical > 0.
- **Business metrics dashboard** для owner (отдельный, не engineering): DAU, transactions, notifications.
- **Synthetic monitoring** — каждые 30 сек fake bot user проходит /start → linking → balance check.

## 7.9 Deployment & infra

- **Kubernetes** (managed: GKE/EKS) c HPA. Для MVP — Render/Fly.io / single VPS с docker-compose, чтобы не оверинжинирить.
- **Blue-green / canary** деплой.
- **Feature flags** (Unleash/PostHog) для постепенного роллаута.
- **DB migrations** — Atlas / Sqitch с zero-downtime практиками (expand-migrate-contract).

---

# 8. SECURITY

## 8.1 Authentication

- **Customer:** Telegram-based. `request_contact` верифицирует номер; нет паролей. Sessions — короткие JWT (или Redis session) per webhook update; ничего долгоживущего.
- **Staff (Telegram):** PIN code (4–6 цифр) + bound `telegram_id`. Hash через argon2id с salt и pepper.
- **Admin web:** email + password (argon2id) + **обязательно 2FA TOTP** для owner/manager. Sessions через short-lived JWT + rotating refresh, secure HttpOnly SameSite=Strict cookies.

## 8.2 Authorization (RBAC)

- Permissions гранулярно (`purchase.create`, `campaign.publish`, `audit.view`).
- Каждый запрос проверяется через middleware: `(tenant_id, role) → allowed_permissions ⊇ required`.
- **Row-Level Security в Postgres** — second line of defense: даже если код забыл WHERE tenant_id, RLS не пустит.

```sql
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON users
  USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

В каждом DB-соединении в начале транзакции `SET LOCAL app.tenant_id = '...'`.

## 8.3 Telegram security

- **Webhook secret:** `setWebhook` с `secret_token` — Telegram шлёт его в заголовке, проверяем.
- **HTTPS** обязательно (Telegram требует).
- **Не доверяй `from.first_name`** — это редактируется. Только `id` и `phone_number` (из contact) — надёжные.
- **Защита от user spoofing**: never identify by username (changes), only by `telegram_id` + verified phone.

## 8.4 Phone verification

- В рамках бота — `request_contact` достаточно (Telegram гарантирует).
- В рамках admin / web (V2 — клиентский кабинет) — OTP via SMS / Telegram Login Widget.

## 8.5 Rate limiting

| Слой | Что | Лимит |
|---|---|---|
| Edge | per IP | 60 rpm |
| Bot | per `telegram_id` | 30 rpm |
| Bot | per `tenant_id` | по плану |
| Admin API | per session | 600 rpm |
| Auth | per email/IP | 5 attempts / 15 min, then exponential lockout |
| OTP | per phone | 3 attempts / 1h |

Реализация — token bucket в Redis.

## 8.6 Abuse prevention

- **Replay protection** в bot webhook (`update_id` уникален + sequential).
- **CSRF** на admin (SameSite + per-form token).
- **CORS** strict allow-list.
- **SQL injection** — только параметризованные запросы; ORM/Query-builder (нет raw concat).
- **XSS** в admin — auto-escape, CSP strict.
- **SSRF** — outgoing requests white-list (в основном в notification webhooks).

## 8.7 Audit logs

- Append-only (`REVOKE UPDATE, DELETE`).
- Подписаны HMAC chain (опционально — каждая запись содержит hash предыдущей; сильная защита от ретроактивного редактирования).
- Хранение ≥ 1 года, экспорт.
- Каждое действие staff и admin логируется с `before/after`.

## 8.8 Employee fraud prevention

См. §4.10. Дополнительно:
- **Запрет начисления самому себе** — staff и customer с одним phone/telegram_id → блокировка.
- **Cooling-off** на refund > N$ — требует second approver.
- **Daily limits per staff** на free coffee redeem без объяснения.

## 8.9 Data protection

- **PII at rest:** phone E.164 хранится открытым (нужно для матчинга), но имя/email можно encrypt at rest (PG TDE / column-level через pgcrypto). Для GDPR-export — полный профиль.
- **PII in logs:** маскировать phone (`+998***4567`), никогда не логировать TG user object целиком.
- **Secrets:** Vault / cloud KMS; не в env-файлах в репо.
- **TLS:** только TLS 1.3 на edge; mTLS между внутренними сервисами при росте.
- **GDPR/CCPA right-to-be-forgotten** — `user.delete()` SP, обнуляет PII, оставляет анонимный финансовый аудит.
- **Data residency** — по плану. EU клиенты — EU region.

## 8.10 Backup strategy

- **PG WAL archiving** + point-in-time recovery.
- **Daily full** + WAL непрерывно. RPO ≤ 5 минут, RTO ≤ 30 минут.
- **Replicas в другом регионе** (V2).
- **Quarterly restore drills** — обязательно. Backup, который не восстановили — это не backup.
- **Logical exports** для долгосрочного хранения / migration.

---

# 9. RECOMMENDED STACK

Принципы выбора: **boring, battle-tested, hireable**, минимум магии, типизация end-to-end.

| Слой | Выбор | Почему |
|---|---|---|
| **Backend язык** | Python 3.12 + FastAPI **или** TypeScript + NestJS | Python — ML-friendly (нужно для V2 fraud / send-time), отличная экосистема aiogram. TS — единый язык с фронтом, более строгая типизация. **Рекомендую TypeScript + NestJS**, если команда не Python-heavy. |
| **Bot framework** | **grammy** (TS) / **aiogram 3** (Python) | Современный API, FSM, middleware, высокая производительность. |
| **DB** | **PostgreSQL 16** | Транзакции, JSONB, partial/expression indexes, partitioning, RLS, mature. |
| **Migrations** | **Atlas** / Prisma migrations | Declarative, diff-based. |
| **ORM** | **Drizzle** (TS) / SQLAlchemy 2.x | Drizzle — близко к SQL, типобезопасно. |
| **Cache / pub-sub** | **Redis 7** | Cache, FSM-state, rate-limit, streams для очередей. |
| **Queue** | **BullMQ** (поверх Redis) → **NATS JetStream** при росте → **Kafka** при scale | Простота → масштаб. |
| **Scheduler** | **Temporal.io** | Durable workflows для expirations, retry, long flows. Альтернатива MVP — node-cron. |
| **Frontend admin** | **Next.js 15 + React 19 + tRPC + TanStack Query + shadcn/ui** | Быстрый dev, type-safe end-to-end, отличные таблицы/формы. |
| **Auth admin** | **Auth.js** (NextAuth) с Credentials + TOTP | Hireable, гибкая. |
| **Analytics warehouse** | **ClickHouse** | OLAP по transactions, sub-second aggregations. |
| **CDC / ingest** | **Debezium → Kafka → CH** (на scale) | Стандарт. |
| **Notifications** | Собственный sender через Telegram Bot API; **Twilio** для SMS fallback | Telegram — основной, SMS — резерв. |
| **Object storage** | **S3-compatible** (R2 / B2 / S3) | Чеки, аватарки, экспорт. |
| **Search** | Postgres `pg_trgm` (MVP) → **Meilisearch** / **Typesense** (V2) | Поиск клиентов в админке. |
| **Monitoring** | **Prometheus + Grafana + Loki + Tempo + Sentry** | Industry standard. |
| **Tracing** | **OpenTelemetry SDK** → Tempo/Jaeger | Vendor-neutral. |
| **Feature flags** | **PostHog** (бесплатно self-hosted, плюс product analytics 2-в-1) | Совмещает FF + analytics + session replay для админки. |
| **Infra** | **Kubernetes на managed** (EKS/GKE) при scale; **Fly.io / Render** для MVP | MVP не требует k8s. |
| **CI/CD** | **GitHub Actions + ArgoCD** (на scale) | Mainstream. |
| **IaC** | **Terraform + Helm** | Reproducible. |
| **Secrets** | **HashiCorp Vault** или Cloud KMS | Не env-файлы. |
| **Email transactional** | **Postmark** / Resend | Reliable. |
| **Payments (V2)** | **Stripe** / локальные (Click, Payme, Stripe Connect) | Для prepaid pre-purchase в боте. |
| **i18n** | **Fluent / ICU MessageFormat** | Plurals, gender — критично для русского. |
| **Testing** | Vitest + Playwright + k6 (load) + Pact (contract bot↔backend) | Полная пирамида. |

**Один deploy environment в начале:** monorepo (Turborepo) → packages: `apps/api`, `apps/bot-gateway`, `apps/admin-web`, `apps/workers`, `packages/domain`, `packages/db`, `packages/bot-ui`, `packages/notif`. Modular monolith ≠ один файл.

---

# 10. MVP ROADMAP

## 10.1 MVP (8–10 недель, 2–3 инженера)

**Goal:** одна сеть кофеен, до 5 точек, до 10k клиентов; продуктово-валидная программа лояльности.

Scope:
- ✅ Multi-tenant скелет (даже если 1 клиент сейчас — заложить).
- ✅ Identity by phone, deferred linking, `request_contact`.
- ✅ Customer Bot: dashboard, balance, history, free coffee redeem (через QR/code).
- ✅ Staff Bot: PIN auth, поиск клиента (phone / last 4 digits), purchase, free redeem, prepaid open & consume, refund (24h window).
- ✅ Admin web: customers list, transactions list, **одна** punchcard кампания, **одна** prepaid конфигурация, базовый dashboard, staff CRUD, branches CRUD.
- ✅ Loyalty engine для type=`punchcard` и `prepaid`. Cashback — V2 (можно отложить, чтобы не растягивать).
- ✅ Notifications: transactional (after purchase, free unlocked), 1 daily reminder, 1 expiration warning. Без сегментирования.
- ✅ Audit log на всех staff actions.
- ✅ Idempotency, optimistic locking, FOR UPDATE на prepaid.
- ✅ Outbox + 1 queue (BullMQ).
- ✅ Backups daily + WAL.

Out of scope: A/B, ML, ClickHouse, sharding, SMS, multi-language (только ru/en), referral, gamification, в-боте оплата.

**Definition of done:**
- Real customer flow проходит end-to-end в течение 2 недель в одной кофейне (alpha).
- Метрики снимаются (DAU, transactions, redeems).
- Owner принимает product (UAT).

## 10.2 V2 (3–4 месяца после MVP)

- **Cashback** + wallet с FIFO expiration.
- **Bonus item / first purchase / birthday** кампании.
- **Multi-language** (ru/en/uz/kz/tr) с правильными plurals.
- **Notification builder в админке**, A/B шаблонов, frequency caps, quiet hours.
- **Segmentation** в админке (RFM, churn risk).
- **Analytics dashboard**: cohort retention, campaign incrementality, LTV.
- **In-bot Stripe / Click / Payme payment** для prepaid.
- **SMS fallback** через Twilio для не-linked клиентов.
- **Referral program** через deep-link.
- **Branded bots** (white-label, per-tenant Telegram bot).
- **Fraud signals UI** + simple velocity rules.
- **PostgreSQL read replica** + админка/боты на read-heavy путях читают replica.
- **Partitioning** transactions/audit_logs по месяцам.
- **Temporal.io** для expirations и долгих workflow.

## 10.3 V3 (advanced)

- **Tiered status** (Bronze/Silver/Gold) с visual progression.
- **Gamification:** streaks, achievements, secret menu.
- **POS integrations** (R-Keeper, iiko, Loyverse, Square) — push транзакций без бариста-бота.
- **ML send-time optimization** + churn prediction + recommendation product to upsell.
- **Owner mobile app** (React Native).
- **Open API** для tenant-ов (webhook + REST).
- **Marketplace кампаний** — готовые шаблоны для разных бизнес-целей.
- **Voice ordering** через Telegram voice (V3+, экспериментально).

## 10.4 Scaling phase (когда триггерить)

| Триггер | Действие |
|---|---|
| DB CPU > 70% sustained | Добавить read replicas, переключить read paths |
| Tx > 1k/sec | Партиционировать crucial tables |
| Tx > 10k/sec | Citus / sharding по `tenant_id` |
| Notification lag > 30s | Раздельные queues per tenant tier |
| Telegram rate limit blocked | Per-tenant bots |
| Admin queries slow | Вынести analytics в ClickHouse |
| Single AZ outage риск | Multi-AZ, async replication, RPO ≤ 1 min |
| Multiple regions | Per-region cluster + tenant routing |

## 10.5 Team composition

| Phase | Состав |
|---|---|
| MVP | 1 backend, 1 fullstack, 1 product/PM (часть-time дизайнер) |
| V2 | +1 backend, +1 frontend, +1 data/analyst |
| V3 / Scale | +DevOps/SRE, +ML engineer, +QA |

## 10.6 Ключевые риски и mitigation

| Риск | Mitigation |
|---|---|
| Бариста саботирует (не использует или фродит) | UX <1s выдача; PIN; fraud monitoring; обучение; KPI-завязка |
| Owner не настраивает кампании | Pre-built templates; onboarding wizard; CS поддержка |
| Telegram блок | Web PWA как backup (V2); SMS fallback |
| Notification fatigue | Frequency caps c day 1; opt-in честный |
| Промо съедает маржу | Лимиты на размер бесплатного; max-size правила; A/B |
| Дублирующиеся пользователи | Unique index + merge tool в админке |
| Race conditions | FOR UPDATE / version + load-test scenarios |
| Data loss | WAL + daily + restore drills |

---

# Приложение A. Acceptance criteria для MVP

- [ ] Можно завести клиента по телефону без его участия; покупки работают; при первом /start клиент автоматически связан.
- [ ] При параллельном начислении на двух кассах нет дублей stamps (load-test 100 RPS на одного клиента).
- [ ] Двойное нажатие «Начислить» → одна транзакция (idempotency proven).
- [ ] Refund корректно компенсирует stamps/cashback/prepaid.
- [ ] Notification отправляется в timezone клиента, не в quiet hours.
- [ ] Admin может всё откатить через audit (видна история «до/после»).
- [ ] RLS работает: tenant A не видит данных tenant B даже через прямой SQL приложения.
- [ ] Restore drill: восстановление БД из backup за <30 минут.

# Приложение B. Не делать в MVP (anti-scope)

- Не строить микросервисы.
- Не писать собственный feature-flag service.
- Не делать собственный billing — Stripe.
- Не оптимизировать преждевременно: не Citus, не Kafka, не CQRS.
- Не делать ML — эвристики.
- Не делать iOS/Android — только Telegram + web admin.
- Не поддерживать оффлайн на бариста-боте.
- Не строить «универсальный» constructor акций — 2 типа достаточно.

---

**Конец документа.** Дальнейший шаг — превратить разделы 4–5 в JIRA-эпики и начать с identity + transactions + punchcard как минимально цельной вертикали.
