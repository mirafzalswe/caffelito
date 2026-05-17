"""Lightweight i18n for the admin panel and bots.

Flat key→translation dict per language. Keys are short ASCII codes
(eg. ``nav.customers``); values are the localised strings.

Usage:
    from app.core.i18n import t
    t("nav.customers", lang="uz")  # → "Mijozlar"

Uzbek is the modern Latin script (Oʻzbek tili / lotin).
"""

from __future__ import annotations

LANGUAGES = ("ru", "uz")
DEFAULT_LANG = "ru"


T: dict[str, dict[str, str]] = {
    # ── Navigation / sidebar ────────────────────────────────────────────
    "nav.dashboard":   {"ru": "Дашборд",      "uz": "Boshqaruv paneli"},
    "nav.customers":   {"ru": "Клиенты",      "uz": "Mijozlar"},
    "nav.campaigns":   {"ru": "Акции",        "uz": "Aksiyalar"},
    "nav.products":    {"ru": "Продукты",     "uz": "Mahsulotlar"},
    "nav.branches":    {"ru": "Точки",        "uz": "Filiallar"},
    "nav.staff":       {"ru": "Сотрудники",   "uz": "Xodimlar"},
    "nav.transactions":{"ru": "Транзакции",   "uz": "Tranzaksiyalar"},
    "nav.audit":       {"ru": "Аудит",        "uz": "Audit"},
    "nav.broadcasts": {"ru": "Рассылки",      "uz": "Yangiliklar"},
    "nav.group.shop":  {"ru": "Магазин",      "uz": "Doʻkon"},
    "nav.group.history":{"ru": "История",     "uz": "Tarix"},
    "nav.logout":      {"ru": "выйти",        "uz": "chiqish"},

    # ── Common ──────────────────────────────────────────────────────────
    "common.create":   {"ru": "Создать",      "uz": "Yaratish"},
    "common.add":      {"ru": "Добавить",     "uz": "Qoʻshish"},
    "common.cancel":   {"ru": "Отмена",       "uz": "Bekor qilish"},
    "common.save":     {"ru": "Сохранить",    "uz": "Saqlash"},
    "common.apply":    {"ru": "Применить",    "uz": "Qoʻllash"},
    "common.search":   {"ru": "Поиск",        "uz": "Qidiruv"},
    "common.find":     {"ru": "Найти",        "uz": "Topish"},
    "common.open":     {"ru": "Открыть",      "uz": "Ochish"},
    "common.reset":    {"ru": "Сбросить",     "uz": "Tozalash"},
    "common.yes":      {"ru": "да",           "uz": "ha"},
    "common.no":       {"ru": "нет",          "uz": "yoʻq"},
    "common.back":     {"ru": "Назад",        "uz": "Orqaga"},
    "common.next":     {"ru": "Вперёд",       "uz": "Keyingi"},
    "common.prev":     {"ru": "Назад",        "uz": "Oldingi"},
    "common.page":     {"ru": "Страница",     "uz": "Sahifa"},
    "common.none":     {"ru": "нет",          "uz": "yoʻq"},
    "common.dash":     {"ru": "—",            "uz": "—"},
    "common.empty":    {"ru": "пусто",        "uz": "boʻsh"},
    "common.on":       {"ru": "Вкл",          "uz": "Yoq"},
    "common.off":      {"ru": "Выкл",         "uz": "Oʻchir"},
    "common.required": {"ru": "обязательно",  "uz": "majburiy"},

    # ── Status ──────────────────────────────────────────────────────────
    "status.active":   {"ru": "Активен",      "uz": "Faol"},
    "status.blocked":  {"ru": "Заблокирован", "uz": "Bloklangan"},
    "status.active.fem":{"ru":"Активна",      "uz": "Faol"},
    "status.inactive": {"ru": "Неактивен",    "uz": "Nofaol"},
    "status.paused":   {"ru": "На паузе",     "uz": "Toʻxtatilgan"},
    "status.draft":    {"ru": "Черновик",     "uz": "Qoralama"},
    "status.archived": {"ru": "Архив",        "uz": "Arxiv"},

    # ── Customer list ────────────────────────────────────────────────────
    "cust.title.list":  {"ru": "Клиенты",     "uz": "Mijozlar"},
    "cust.new":         {"ru": "Новый клиент","uz": "Yangi mijoz"},
    "cust.no_match":    {"ru": "Никого не нашлось.", "uz": "Hech kim topilmadi."},
    "cust.search_ph":   {"ru": "Поиск по имени или цифрам телефона…",
                         "uz": "Ism yoki telefon raqami boʻyicha qidirish…"},
    "cust.col.name":    {"ru": "Имя",         "uz": "Ism"},
    "cust.col.phone":   {"ru": "Телефон",     "uz": "Telefon"},
    "cust.col.status":  {"ru": "Статус",      "uz": "Holat"},
    "cust.col.created": {"ru": "Создан",      "uz": "Yaratilgan"},
    "cust.no_name":     {"ru": "Без имени",   "uz": "Ismsiz"},
    "cust.created_at":  {"ru": "создан",      "uz": "yaratildi"},
    "cust.block":       {"ru": "Заблокировать","uz": "Bloklash"},
    "cust.unblock":     {"ru": "Разблокировать","uz": "Blokdan chiqarish"},
    "cust.block_confirm":{"ru": "Заблокировать клиента?","uz": "Mijozni bloklaymizmi?"},
    "cust.blocked_warn":{"ru": "Клиент заблокирован — разблокируй в шапке, чтобы начислять покупки и бонусы.",
                         "uz": "Mijoz bloklangan — xaridlar va bonuslar uchun yuqorida blokdan chiqaring."},

    # KPI
    "kpi.punchcard":    {"ru": "штамп-карта", "uz": "shtamp-karta"},
    "kpi.free":         {"ru": "бесплатные кофе","uz": "bepul kofelar"},
    "kpi.ready":        {"ru": "готов",       "uz": "tayyor"},
    "kpi.ready.many":   {"ru": "готово",      "uz": "tayyor"},
    "kpi.cashback":     {"ru": "кэшбэк",      "uz": "keshbek"},
    "kpi.prepaid":      {"ru": "в пакете",    "uz": "paketda"},
    "kpi.total_received":{"ru":"всего получил","uz": "jami oldi"},
    "kpi.last_visit":   {"ru": "был",         "uz": "oxirgi tashrif"},
    "kpi.no_visits":    {"ru": "первая встреча","uz": "birinchi marta"},
    "kpi.spent":        {"ru": "всего потратил","uz": "jami sarfladi"},
    "kpi.lifetime":     {"ru": "за всё время","uz": "umumiy"},

    # Actions
    "act.title":        {"ru": "Что делаем?", "uz": "Nima qilamiz?"},
    "act.branch":       {"ru": "Точка",       "uz": "Filial"},
    "act.tab.purchase": {"ru": "Покупка",     "uz": "Xarid"},
    "act.tab.bonus":    {"ru": "Подарок",     "uz": "Sovgʻa"},
    "act.tab.prepaid":  {"ru": "Пакет",       "uz": "Paket"},
    "act.tab.vip":      {"ru": "VIP-абонемент","uz": "VIP-obonement"},
    "act.btn.activate_vip":{"ru":"Активировать VIP","uz":"VIP-ni faollashtirish"},
    "act.vip.no_camps": {"ru":"Нет акций типа «VIP-абонемент». Создай в разделе Акции.",
                         "uz":"VIP-obonement turidagi aksiyalar yoʻq. Aksiyalar boʻlimida yarating."},
    "act.vip.amount":   {"ru":"Сумма оплаты","uz":"Toʻlov summasi"},
    "act.vip.amount_hint":{"ru":"≥ минимальной суммы, указанной в акции","uz":"≥ aksiyada koʻrsatilgan minimal summa"},
    "act.vip.has_active":{"ru":"У клиента уже активен абонемент — дождись окончания.",
                          "uz":"Mijozda allaqachon faol obonement bor — tugashini kuting."},
    "kpi.vip":          {"ru":"VIP-скидка",  "uz":"VIP-chegirma"},
    "kpi.vip_until":    {"ru":"до {dt}",     "uz":"{dt} gacha"},
    "camp.tile.tier.title":{"ru":"VIP-абонемент","uz":"VIP-obonement"},
    "camp.tile.tier.desc":{"ru":"Клиент платит сумму → получает скидку % на N дней.",
                           "uz":"Mijoz pul toʻlaydi → N kun davomida % chegirma oladi."},
    "camp.tier.entry":  {"ru":"Минимальная сумма активации","uz":"Faollashtirish uchun minimal summa"},
    "camp.tier.discount":{"ru":"Размер скидки (%)","uz":"Chegirma miqdori (%)"},
    "camp.tier.duration":{"ru":"Срок действия (дней)","uz":"Amal qilish muddati (kun)"},
    "act.product":      {"ru": "Продукт",     "uz": "Mahsulot"},
    "act.qty":          {"ru": "Количество",  "uz": "Miqdor"},
    "act.amount":       {"ru": "Сумма",       "uz": "Summa"},
    "act.reason":       {"ru": "Причина",     "uz": "Sabab"},
    "act.campaign":     {"ru": "Акция",       "uz": "Aksiya"},
    "act.campaign_auto":{"ru": "Акция (по умолчанию — авто)",
                         "uz": "Aksiya (standart — avto)"},
    "act.auto_option":  {"ru": "Авто — система выберет по приоритету",
                         "uz": "Avto — tizim ustuvorlik boʻyicha tanlaydi"},
    "act.what_to_gift": {"ru": "Что подарить", "uz": "Nimani sovgʻa qilamiz"},
    "act.gift_free":    {"ru": "Готовый бесплатный кофе",
                         "uz": "Tayyor bepul kofe"},
    "act.gift_stamps":  {"ru": "Штампы в карту","uz": "Kartaga shtamp(lar)"},
    "act.btn.purchase": {"ru": "Начислить покупку","uz": "Xaridni qoʻshish"},
    "act.btn.gift":     {"ru": "Подарить",    "uz": "Sovgʻa qilish"},
    "act.btn.open_pack":{"ru": "Открыть пакет","uz": "Paket ochish"},
    "act.btn.redeem":   {"ru": "Выдать бесплатный кофе",
                         "uz": "Bepul kofe berish"},
    "act.kind_hint":    {"ru": "Тип акции определяет, что именно подарим.",
                         "uz": "Aksiya turi sovgʻani belgilaydi."},
    "act.no_camps":     {"ru": "Нет активных акций.","uz": "Faol aksiyalar yoʻq."},
    "act.create_first": {"ru": "Создать первую","uz": "Birinchisini yaratish"},
    "act.no_branch":    {"ru": "Сначала создай хотя бы одну точку.",
                         "uz": "Avval kamida bitta filial yarating."},
    "act.no_products":  {"ru": "Нет активных продуктов.","uz": "Faol mahsulotlar yoʻq."},
    "act.reason_ph":    {"ru": "Извинение / маркетинговая акция",
                         "uz": "Uzr / marketing aksiyasi"},
    "act.qty_pack":     {"ru": "Сколько кофе в пакете","uz": "Paketda nechta kofe"},
    "act.qty_gift":     {"ru": "Сколько",     "uz": "Qancha"},
    "act.exclusive":    {"ru": "(эксклюзивная)","uz": "(eksklyuziv)"},

    # Active cards/packages
    "cards.title":      {"ru": "Активные карты и пакеты","uz": "Faol kartalar va paketlar"},
    "cards.status.go":  {"ru": "готов",       "uz": "tayyor"},
    "cards.status.wip": {"ru": "копится",     "uz": "yigʻilmoqda"},
    "cards.pack_left":  {"ru": "осталось {n} порций",
                         "uz": "{n} porsiya qoldi"},
    "cards.pack_until": {"ru": "до {dt}",     "uz": "{dt} gacha"},
    "cards.pack_no_exp":{"ru": "без срока",   "uz": "muddatsiz"},
    "cards.redeem_confirm":{"ru":"Выдать бесплатный кофе по акции «{name}»?",
                            "uz": "«{name}» aksiyasi boʻyicha bepul kofe berilsinmi?"},

    # History
    "hist.title":       {"ru": "История",     "uz": "Tarix"},
    "hist.empty":       {"ru": "Ещё не было операций.","uz": "Hozircha operatsiyalar yoʻq."},
    "hist.purchase":    {"ru": "Покупка",     "uz": "Xarid"},
    "hist.free":        {"ru": "Бесплатный кофе","uz": "Bepul kofe"},
    "hist.prepaid":     {"ru": "Списано из пакета","uz": "Paketdan yozildi"},
    "hist.grant":       {"ru": "Ручной бонус","uz": "Qoʻlda bonus"},
    "hist.refund":      {"ru": "Возврат",     "uz": "Qaytarish"},

    # Redeem dialog
    "dlg.redeem.title": {"ru": "Выдать бесплатный кофе","uz": "Bepul kofe berish"},
    "dlg.redeem.hint1": {"ru": "Списать бесплатный кофе с накопленной карты клиента?",
                         "uz": "Mijozning tayyor kartasidan bepul kofe yozilsinmi?"},
    "dlg.redeem.hintN": {"ru": "У клиента {n} готовых карт — выбери с какой списать:",
                         "uz": "Mijozda {n} ta tayyor karta — qaysi biridan yozish kerakligini tanlang:"},
    "dlg.redeem.completed":{"ru":"завершена","uz": "tugatildi"},
    "dlg.redeem.submit":{"ru": "Выдать",      "uz": "Berish"},

    # ── Campaigns ──────────────────────────────────────────────────────
    "camp.title.list":  {"ru": "Кампании",    "uz": "Kampaniyalar"},
    "camp.title.new":   {"ru": "Новая акция", "uz": "Yangi aksiya"},
    "camp.col.name":    {"ru": "Название",    "uz": "Nomi"},
    "camp.col.type":    {"ru": "Тип",         "uz": "Turi"},
    "camp.col.status":  {"ru": "Статус",      "uz": "Holat"},
    "camp.col.priority":{"ru": "Приоритет",   "uz": "Ustuvorlik"},
    "camp.col.stack":   {"ru": "Совместима",  "uz": "Birlashadi"},
    "camp.empty":       {"ru": "Кампаний пока нет.","uz": "Hozircha kampaniyalar yoʻq."},
    "camp.type.punchcard":{"ru":"штамп-карта","uz": "shtamp-karta"},
    "camp.type.cashback":{"ru":"кэшбэк",      "uz": "keshbek"},
    "camp.type.prepaid":{"ru":"пакет",        "uz": "paket"},
    "camp.exclusive":   {"ru": "эксклюзивная","uz": "eksklyuziv"},
    "camp.name":        {"ru": "Название",    "uz": "Nomi"},
    "camp.priority":    {"ru": "Приоритет",   "uz": "Ustuvorlik"},
    "camp.priority_hint":{"ru":"Чем больше, тем раньше применяется при пересечении нескольких акций.",
                          "uz": "Raqam katta boʻlsa, bir nechta aksiya kesishganda erta qoʻllaniladi."},
    "camp.stackable":   {"ru": "Совместима с другими акциями",
                         "uz": "Boshqa aksiyalar bilan birlasha oladi"},
    "camp.stackable_hint":{"ru":"Если выключено — при пересечении побеждает одна акция по приоритету.",
                           "uz":"Oʻchirilgan boʻlsa — kesishganda ustuvorlik boʻyicha bittasi gʻolib boʻladi."},
    "camp.branches":    {"ru": "Точки",       "uz": "Filiallar"},
    "camp.no_branch_link":{"ru":"Сначала создай точку.","uz":"Avval filial yarating."},
    "camp.type.label":  {"ru": "Тип акции",   "uz": "Aksiya turi"},
    "camp.type.fixed":  {"ru": "меняется только пересозданием.",
                         "uz": "faqat qayta yaratish orqali oʻzgaradi."},
    "camp.tile.pc.title":{"ru":"Штамп-карта","uz":"Shtamp-karta"},
    "camp.tile.pc.desc": {"ru":"Купи N → получи 1 бесплатно.",
                          "uz":"N ta sotib ol → 1 ta bepul ol."},
    "camp.tile.cb.title":{"ru":"Кэшбэк %",   "uz":"Keshbek %"},
    "camp.tile.cb.desc": {"ru":"% от покупки возвращается клиенту.",
                          "uz":"Xarid summasining % qismi mijozga qaytadi."},
    "camp.tile.pp.title":{"ru":"Пакет авансом","uz":"Oldindan toʻlovli paket"},
    "camp.tile.pp.desc": {"ru":"Клиент платит вперёд за N порций.",
                          "uz":"Mijoz oldindan N porsiya uchun toʻlaydi."},
    "camp.pc.stamps":   {"ru":"Сколько штампов до бесплатного",
                         "uz":"Bepulgacha nechta shtamp"},
    "camp.pc.category": {"ru":"На какие товары","uz":"Qaysi mahsulotlarga"},
    "camp.pc.cat.coffee":{"ru":"только кофе","uz":"faqat kofe"},
    "camp.pc.cat.tea":  {"ru":"только чай",  "uz":"faqat choy"},
    "camp.pc.cat.food": {"ru":"еда",         "uz":"taom"},
    "camp.pc.cat.any":  {"ru":"любые товары","uz":"barcha mahsulotlar"},
    "camp.pc.expires":  {"ru":"Срок жизни карты (дней)",
                         "uz":"Karta amal qilish muddati (kun)"},
    "camp.pc.cooldown": {"ru":"Кулдаун между штампами (мин)",
                         "uz":"Shtamp orasidagi pauza (min)"},
    "camp.pc.cooldown_hint":{"ru":"0 = без ограничения. 5–10 защищает от двойного нажатия.",
                             "uz":"0 = cheklov yoʻq. 5–10 — ikki marta bosishdan himoya."},
    "camp.cb.percent":  {"ru":"Процент кэшбэка","uz":"Keshbek foizi"},
    "camp.cb.percent_hint":{"ru":"5 = 5% от суммы.","uz":"5 = summadan 5%."},
    "camp.cb.min":      {"ru":"Минимальная сумма покупки",
                         "uz":"Minimal xarid summasi"},
    "camp.cb.min_hint": {"ru":"0 = без ограничения.","uz":"0 = cheklov yoʻq."},
    "camp.cb.expires":  {"ru":"Срок жизни кэшбэка (дней)",
                         "uz":"Keshbek amal qilish muddati (kun)"},
    "camp.pp.qty":      {"ru":"Сколько порций в пакете","uz":"Paketda nechta porsiya"},
    "camp.pp.price":    {"ru":"Цена пакета","uz":"Paket narxi"},
    "camp.pp.expires":  {"ru":"Срок жизни пакета (дней)",
                         "uz":"Paket amal qilish muddati (kun)"},
    "camp.cat.any":     {"ru":"любые","uz":"barchasi"},
    "camp.cat.coffee":  {"ru":"только кофе","uz":"faqat kofe"},
    "camp.cat.tea":     {"ru":"только чай","uz":"faqat choy"},
    "camp.cat.food":    {"ru":"только еда","uz":"faqat taom"},

    # ── Dashboard ──────────────────────────────────────────────────────
    "dash.title":       {"ru":"Дашборд",       "uz":"Boshqaruv paneli"},
    "dash.kpi.customers":{"ru":"Всего клиентов","uz":"Jami mijozlar"},
    "dash.kpi.active30":{"ru":"Активны за 30 дн","uz":"30 kun ichida faol"},
    "dash.kpi.tx_today":{"ru":"Транзакций сегодня","uz":"Bugungi tranzaksiyalar"},
    "dash.kpi.rev7":    {"ru":"Выручка 7 дн","uz":"7 kunlik tushum"},
    "dash.kpi.free7":   {"ru":"Бесплатных за 7 дн","uz":"7 kunda bepul"},
    "dash.kpi.prepaid7":{"ru":"Списано из пакетов 7 дн","uz":"7 kunda paketdan"},
    "dash.kpi.branches":{"ru":"Активных точек","uz":"Faol filiallar"},
    "dash.kpi.vip_count":{"ru":"Активных VIP","uz":"Faol VIP"},
    "dash.kpi.vip_liability":{"ru":"VIP-обязательства","uz":"VIP-majburiyatlar"},
    "dash.feed.title":  {"ru":"Лента транзакций","uz":"Tranzaksiyalar oqimi"},
    "dash.feed.subtitle":{"ru":"обновляется каждые 5 сек","uz":"har 5 sekundda yangilanadi"},
    "dash.feed.loading":{"ru":"Загружаем…","uz":"Yuklanmoqda…"},

    # ── Products ───────────────────────────────────────────────────────
    "prod.title":       {"ru":"Продукты",     "uz":"Mahsulotlar"},
    "prod.empty":       {"ru":"Пока нет продуктов.","uz":"Hozircha mahsulotlar yoʻq."},
    "prod.col.name":    {"ru":"Название",     "uz":"Nomi"},
    "prod.col.sku":     {"ru":"SKU",          "uz":"SKU"},
    "prod.col.category":{"ru":"Категория",    "uz":"Kategoriya"},
    "prod.col.size":    {"ru":"Размер",       "uz":"Hajmi"},
    "prod.col.price":   {"ru":"Цена",         "uz":"Narxi"},
    "prod.col.loyalty": {"ru":"Лояльность",   "uz":"Loyalti"},
    "prod.col.status":  {"ru":"Статус",       "uz":"Holat"},
    "prod.new":         {"ru":"Добавить продукт","uz":"Mahsulot qoʻshish"},
    "prod.loyalty_hint":{"ru":"Участвует в loyalty (накапливаются штампы)",
                         "uz":"Loyaltida qatnashadi (shtamp toʻplanadi)"},

    # ── Branches ───────────────────────────────────────────────────────
    "br.title":         {"ru":"Точки",        "uz":"Filiallar"},
    "br.empty":         {"ru":"Точек нет.",   "uz":"Filiallar yoʻq."},
    "br.col.name":      {"ru":"Название",     "uz":"Nomi"},
    "br.col.address":   {"ru":"Адрес",        "uz":"Manzil"},
    "br.col.tz":        {"ru":"Часовой пояс", "uz":"Vaqt mintaqasi"},
    "br.col.status":    {"ru":"Статус",       "uz":"Holat"},
    "br.new":           {"ru":"Добавить точку","uz":"Filial qoʻshish"},

    # ── Staff ──────────────────────────────────────────────────────────
    "staff.title":      {"ru":"Сотрудники",   "uz":"Xodimlar"},
    "staff.empty":      {"ru":"Никого нет.",  "uz":"Hech kim yoʻq."},
    "staff.col.name":   {"ru":"Имя",          "uz":"Ism"},
    "staff.col.email":  {"ru":"Email",        "uz":"Email"},
    "staff.col.role":   {"ru":"Роль",         "uz":"Rol"},
    "staff.col.status": {"ru":"Статус",       "uz":"Holat"},
    "staff.col.tg":     {"ru":"Telegram",     "uz":"Telegram"},
    "staff.col.created":{"ru":"Создан",       "uz":"Yaratilgan"},
    "staff.new":        {"ru":"Добавить сотрудника","uz":"Xodim qoʻshish"},
    "staff.role.barista":{"ru":"бариста (PIN, работает в Telegram)",
                          "uz":"barista (PIN, Telegramda ishlaydi)"},
    "staff.role.owner": {"ru":"владелец (web admin)",
                         "uz":"egasi (web admin)"},
    "staff.pin":        {"ru":"PIN (4–6 цифр)","uz":"PIN (4–6 raqam)"},
    "staff.password":   {"ru":"Пароль",       "uz":"Parol"},
    "staff.tg.linked":  {"ru":"связан",       "uz":"bogʻlangan"},

    # ── Transactions ───────────────────────────────────────────────────
    "tx.title":         {"ru":"Транзакции",   "uz":"Tranzaksiyalar"},
    "tx.filter.all":    {"ru":"Все типы",     "uz":"Barcha turlar"},
    "tx.filter.purchase":{"ru":"Покупки",     "uz":"Xaridlar"},
    "tx.filter.free":   {"ru":"Бесплатный кофе","uz":"Bepul kofe"},
    "tx.filter.prepaid":{"ru":"Из пакета",    "uz":"Paketdan"},
    "tx.filter.refund": {"ru":"Возвраты",     "uz":"Qaytarishlar"},
    "tx.empty":         {"ru":"Транзакций нет.","uz":"Tranzaksiyalar yoʻq."},
    "tx.col.when":      {"ru":"Когда",        "uz":"Qachon"},
    "tx.col.type":      {"ru":"Тип",          "uz":"Turi"},
    "tx.col.customer":  {"ru":"Клиент",       "uz":"Mijoz"},
    "tx.col.amount":    {"ru":"Сумма",        "uz":"Summa"},
    "tx.col.branch":    {"ru":"Точка",        "uz":"Filial"},
    "tx.col.staff":     {"ru":"Сотрудник",    "uz":"Xodim"},
    "tx.detail.title":  {"ru":"Транзакция",   "uz":"Tranzaksiya"},
    "tx.detail.params": {"ru":"Параметры",    "uz":"Parametrlar"},
    "tx.detail.items":  {"ru":"Позиции",      "uz":"Pozitsiyalar"},
    "tx.detail.ledger": {"ru":"Записи леджера","uz":"Ledger yozuvlari"},
    "tx.detail.source": {"ru":"Источник",     "uz":"Manba"},

    # ── Audit ──────────────────────────────────────────────────────────
    "audit.title":      {"ru":"Аудит-лог",    "uz":"Audit jurnali"},
    "audit.empty":      {"ru":"Записей нет.", "uz":"Yozuvlar yoʻq."},
    "audit.col.when":   {"ru":"Когда",        "uz":"Qachon"},
    "audit.col.actor":  {"ru":"Кто",          "uz":"Kim"},
    "audit.col.action": {"ru":"Действие",     "uz":"Harakat"},
    "audit.col.target": {"ru":"Цель",         "uz":"Maqsad"},
    "audit.col.reason": {"ru":"Причина",      "uz":"Sabab"},

    # ── Broadcasts ─────────────────────────────────────────────────────
    "bc.title":         {"ru":"Рассылки",         "uz":"Yangiliklar"},
    "bc.new":           {"ru":"Новая рассылка",   "uz":"Yangi xabar"},
    "bc.empty":         {"ru":"Рассылок ещё нет.","uz":"Hozircha xabarlar yoʻq."},
    "bc.recipients":    {"ru":"Подписчиков в боте","uz":"Botdagi obunachilar"},
    "bc.recipients_hint":{"ru":"клиенты со связанным Telegram","uz":"Telegram bilan bogʻlangan mijozlar"},
    "bc.will_reach":    {"ru":"Сообщение получат","uz":"Xabarni shu kishilar oladi:"},
    "bc.linked_customers":{"ru":"клиентов","uz":"mijoz"},
    "bc.body":          {"ru":"Текст сообщения","uz":"Xabar matni"},
    "bc.body_ph":       {"ru":"Например: Завтра в 10:00 — открытие новой точки! Заходите 🎉","uz":"Masalan: Ertaga soat 10:00 — yangi filial ochilishi! Kelishingizni kutamiz 🎉"},
    "bc.body_hint":     {"ru":"Можно использовать HTML: <b>жирный</b>, <i>курсив</i>, ссылки.","uz":"HTML ishlatish mumkin: <b>qalin</b>, <i>kursiv</i>, havolalar."},
    "bc.media":         {"ru":"Фото или видео (необязательно)","uz":"Surat yoki video (ixtiyoriy)"},
    "bc.media_hint":    {"ru":"JPG/PNG/WebP до 10 МБ, MP4/MOV до 50 МБ. Текст становится подписью под медиа.","uz":"JPG/PNG/WebP — 10 MB gacha, MP4/MOV — 50 MB gacha. Matn media ostida sarlavha boʻladi."},
    "bc.send_now":      {"ru":"Отправить ({n})", "uz":"Yuborish ({n})"},
    "bc.col.when":      {"ru":"Когда",            "uz":"Qachon"},
    "bc.col.preview":   {"ru":"Текст",            "uz":"Matn"},
    "bc.col.media":     {"ru":"Медиа",            "uz":"Media"},
    "bc.col.status":    {"ru":"Статус",           "uz":"Holat"},
    "bc.col.progress":  {"ru":"Отправлено",       "uz":"Yuborildi"},
    "bc.detail.title":  {"ru":"Рассылка",         "uz":"Xabar"},
    "bc.detail.sent_at":{"ru":"Завершено",        "uz":"Tugatildi"},
    "bc.detail.error":  {"ru":"Ошибка",           "uz":"Xato"},
    "bc.detail.body":   {"ru":"Текст",            "uz":"Matn"},
    "bc.preview":       {"ru":"Превью",           "uz":"Koʻrinishi"},
    "bc.preview_empty": {"ru":"Начни писать — увидишь как сообщение появится у клиента", "uz":"Yozishni boshlang — xabar mijozda qanday koʻrinishini koʻrasiz"},
    "bc.fmt.bold":      {"ru":"Жирный (Ctrl+B)", "uz":"Qalin (Ctrl+B)"},
    "bc.fmt.italic":    {"ru":"Курсив (Ctrl+I)", "uz":"Kursiv (Ctrl+I)"},
    "bc.fmt.underline": {"ru":"Подчёркнутый (Ctrl+U)","uz":"Tagiga chizilgan (Ctrl+U)"},
    "bc.fmt.strike":    {"ru":"Зачёркнутый",    "uz":"Chizilgan"},
    "bc.fmt.code":      {"ru":"Моноширинный код","uz":"Kod"},
    "bc.fmt.link":      {"ru":"Ссылка",          "uz":"Havola"},
    "bc.fmt.link_prompt":{"ru":"Введи URL ссылки","uz":"Havola URL manzilini kiriting"},
    "bc.fmt.emoji":     {"ru":"Вставить эмодзи", "uz":"Emoji qoʻshish"},

    # ── Login ──────────────────────────────────────────────────────────
    "login.title":      {"ru":"Вход",         "uz":"Kirish"},
    "login.subtitle":   {"ru":"Админ-панель", "uz":"Admin panel"},
    "login.email":      {"ru":"Логин",        "uz":"Login"},
    "login.password":   {"ru":"Пароль",       "uz":"Parol"},
    "login.submit":     {"ru":"Войти",        "uz":"Kirish"},
    "login.invalid":    {"ru":"Неверный email или пароль.",
                         "uz":"Email yoki parol notoʻgʻri."},
}


def t(key: str, lang: str | None = None, **fmt) -> str:
    """Translate ``key`` into ``lang``. Falls back to ``DEFAULT_LANG`` then key.

    ``**fmt`` is applied via ``str.format``; any KeyError is swallowed and the
    raw template is returned so a missing placeholder never crashes a page.
    """
    if not lang:
        lang = DEFAULT_LANG
    entry = T.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError):
            return text
    return text


def normalize_lang(value: str | None) -> str:
    if not value:
        return DEFAULT_LANG
    value = value.lower()
    if value not in LANGUAGES:
        return DEFAULT_LANG
    return value
