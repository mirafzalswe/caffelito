"""Customer-bot i18n. RU + UZ (Latin).

Two helpers used by handlers:
    t(key, lang, **fmt) -> str
    btn_set(key)        -> set[str]   # all known label variants for a button
"""

from __future__ import annotations

LANGUAGES = ("ru", "uz")
DEFAULT_LANG = "ru"

T: dict[str, dict[str, str]] = {
    "ru": {
        "welcome": (
            "Привет! ☕\n\n"
            "Это твоя цифровая карта лояльности. Поделись номером телефона — "
            "и я найду твои бонусы или создам новую карту."
        ),
        "share_btn": "📱 Поделиться номером",
        "linked_known": "Привет, {name}! Твоя карта снова с тобой.",
        "linked_new": "Готово! Твоя цифровая карта создана. Покупай и копи бонусы 🎉",
        "conflict": (
            "⚠️ Этот номер уже привязан к другому Telegram-аккаунту. "
            "Свяжись с поддержкой кофейни, чтобы решить."
        ),
        "invalid_phone": (
            "Не удалось распознать номер телефона. Поделись номером ещё раз "
            "через кнопку ниже."
        ),
        "wrong_contact": "Чтобы найти твою карту, поделись своим номером (кнопка ниже).",
        "generic_error": "Что-то пошло не так. Попробуй ещё раз позже.",

        "dashboard_tpl": (
            "☕ <b>Твоя карта</b>\n\n"
            "{progress}\n"
            "{stamps_line}\n"
            "{vip_block}"
            "\n"
            "🎁 Бесплатных кофе: <b>{free}</b>\n"
            "💰 Кэшбэк: <b>{cashback} {currency}</b>"
        ),
        "vip_line": "\n🛡 VIP −{pct}%: <b>{balance} {currency}</b> на балансе\n",
        "stamps_left": " — до бесплатного {n}!",
        "stamps_full": " — карта заполнена 🎉",
        "no_card": "ещё нет открытой карты",

        "btn.redeem":  "🎁 Использовать бесплатный кофе",
        "btn.history": "📜 История",
        "btn.refresh": "🔄 Обновить",
        "btn.lang":    "🌐 Язык",

        "no_free.no_card_head": "☕ <b>Пока нет бесплатного кофе.</b>",
        "no_free.no_card_body": "Купи первый кофе — и начнём копить штампы!\nКаждый кофе приближает тебя к бесплатному 🎁",
        "no_free.one":      "🔥 <b>Остался всего ОДИН штамп до бесплатного кофе!</b>",
        "no_free.one_tail": "Заглядывай скорее — он почти твой ☕",
        "no_free.few":      "☕ <b>До бесплатного кофе осталось всего {n} штампа!</b>",
        "no_free.few_tail": "Ещё пара чашек — и следующий кофе за наш счёт 🎁",
        "no_free.many":     "☕ <b>До бесплатного кофе ещё {n} штампов.</b>",
        "no_free.many_tail":"Накопи их — и следующий кофе мы подарим 🎁",

        "redeem.have":    "🎁 <b>У тебя {n} бесплатных кофе!</b>",
        "redeem.code":    "Покажи бариста этот код: <b>{code}</b>\n\nКод активен 5 минут. После использования он сгорает.",

        "history.empty":  "История пока пуста.",
        "history.header": "<b>Последние операции:</b>\n",
        "tx.purchase":    "Покупка",
        "tx.redeem_free": "Бесплатный кофе",
        "tx.prepaid":     "Из пакета",
        "tx.grant":       "Бонус",
        "tx.refund":      "Возврат",

        "lang.choose":    "Выбери язык / Tilni tanlang:",
        "lang.saved":     "Готово, теперь говорим по-русски ☕",
        "lang.btn.ru":    "🇷🇺 Русский",
        "lang.btn.uz":    "🇺🇿 Oʻzbekcha",

        # Push notifications
        "notify.purchase_header":"☕ <b>Спасибо за покупку!</b>",
        "notify.stamps":         "→ +{n} штамп(ов) в карту",
        "notify.cashback":       "→ 💰 +{amount} {currency} кэшбэк",
        "notify.free_unlocked":  "→ 🎁 Открыт бесплатный кофе! ×{n}",
        "notify.vip_charged":    "→ 🛡 −{charged} с VIP-баланса (остаток {balance} {currency})",
        "notify.vip_activated":  "🛡 <b>VIP-абонемент активирован!</b>\nСкидка −{pct}% · баланс {balance} {currency}",
        "notify.free_redeemed":  "🎁 Бесплатный кофе выдан. Осталось бесплатных: <b>{n}</b>",
        "notify.bonus_free":     "🎁 <b>Тебе подарили {n} бесплатных кофе!</b>",
        "notify.bonus_stamps":   "☕ <b>Тебе добавили {n} штампов!</b>",
        "notify.bonus_cashback": "💰 <b>Тебе подарили {amount} {currency} кэшбэка!</b>",
    },
    "uz": {
        "welcome": (
            "Salom! ☕\n\n"
            "Bu sizning raqamli loyalti kartangiz. Telefon raqamingizni "
            "yuboring — bonuslaringizni topaman yoki yangi karta ochaman."
        ),
        "share_btn": "📱 Raqamni yuborish",
        "linked_known": "Salom, {name}! Kartangiz qaytib keldi.",
        "linked_new": "Tayyor! Raqamli kartangiz yaratildi. Xarid qiling va bonus toʻplang 🎉",
        "conflict": (
            "⚠️ Bu raqam boshqa Telegram akkauntiga bogʻlangan. "
            "Hal qilish uchun kofexona qoʻllab-quvvatlash xizmati bilan bogʻlaning."
        ),
        "invalid_phone": (
            "Telefon raqamini aniqlay olmadim. Quyidagi tugma orqali "
            "raqamingizni qaytadan yuboring."
        ),
        "wrong_contact": "Kartangizni topish uchun oʻz raqamingizni yuboring (pastdagi tugma).",
        "generic_error": "Nimadir notoʻgʻri ketdi. Keyinroq qayta urinib koʻring.",

        "dashboard_tpl": (
            "☕ <b>Sizning kartangiz</b>\n\n"
            "{progress}\n"
            "{stamps_line}\n"
            "{vip_block}"
            "\n"
            "🎁 Bepul kofelar: <b>{free}</b>\n"
            "💰 Keshbek: <b>{cashback} {currency}</b>"
        ),
        "vip_line": "\n🛡 VIP −{pct}%: <b>{balance} {currency}</b> balansda\n",
        "stamps_left": " — bepulgacha {n}!",
        "stamps_full": " — karta toʻldi 🎉",
        "no_card": "hali ochiq karta yoʻq",

        "btn.redeem":  "🎁 Bepul kofeni olish",
        "btn.history": "📜 Tarix",
        "btn.refresh": "🔄 Yangilash",
        "btn.lang":    "🌐 Til",

        "no_free.no_card_head": "☕ <b>Hali bepul kofe yoʻq.</b>",
        "no_free.no_card_body": "Birinchi kofeni soting va shtamplar toʻplay boshlaymiz!\nHar bir kofe sizni bepulga yaqinlashtiradi 🎁",
        "no_free.one":      "🔥 <b>Bepulgacha atigi BITTA shtamp qoldi!</b>",
        "no_free.one_tail": "Tezroq keling — u deyarli sizniki ☕",
        "no_free.few":      "☕ <b>Bepul kofegacha atigi {n} ta shtamp qoldi!</b>",
        "no_free.few_tail": "Yana bir-ikki kosa — keyingisi bepul 🎁",
        "no_free.many":     "☕ <b>Bepul kofegacha {n} ta shtamp qoldi.</b>",
        "no_free.many_tail":"Toʻplab oling — keyingi kofe biz tomondan 🎁",

        "redeem.have":    "🎁 <b>Sizda {n} ta bepul kofe bor!</b>",
        "redeem.code":    "Baristaga bu kodni koʻrsating: <b>{code}</b>\n\nKod 5 daqiqa amal qiladi. Ishlatilgach yoʻq boʻladi.",

        "history.empty":  "Tarix hozircha boʻsh.",
        "history.header": "<b>Soʻnggi operatsiyalar:</b>\n",
        "tx.purchase":    "Xarid",
        "tx.redeem_free": "Bepul kofe",
        "tx.prepaid":     "Paketdan",
        "tx.grant":       "Bonus",
        "tx.refund":      "Qaytarish",

        "lang.choose":    "Выбери язык / Tilni tanlang:",
        "lang.saved":     "Tayyor, endi oʻzbek tilida gaplashamiz ☕",
        "lang.btn.ru":    "🇷🇺 Русский",
        "lang.btn.uz":    "🇺🇿 Oʻzbekcha",

        # Push notifications
        "notify.purchase_header":"☕ <b>Xaridingiz uchun rahmat!</b>",
        "notify.stamps":         "→ +{n} ta shtamp kartaga",
        "notify.cashback":       "→ 💰 +{amount} {currency} keshbek",
        "notify.free_unlocked":  "→ 🎁 Bepul kofe ochildi! ×{n}",
        "notify.vip_charged":    "→ 🛡 −{charged} VIP balansdan (qoldi {balance} {currency})",
        "notify.vip_activated":  "🛡 <b>VIP-obonement faollashtirildi!</b>\nChegirma −{pct}% · balans {balance} {currency}",
        "notify.free_redeemed":  "🎁 Bepul kofe berildi. Bepul kofelar qoldi: <b>{n}</b>",
        "notify.bonus_free":     "🎁 <b>Sizga {n} ta bepul kofe sovgʻa qilindi!</b>",
        "notify.bonus_stamps":   "☕ <b>Sizga {n} ta shtamp qoʻshildi!</b>",
        "notify.bonus_cashback": "💰 <b>Sizga {amount} {currency} keshbek sovgʻa qilindi!</b>",
    },
}


PROGRESS_FILLED = "🟦"
PROGRESS_EMPTY = "⬜"


def normalize_lang(value: str | None) -> str:
    if not value:
        return DEFAULT_LANG
    value = value.lower()[:2]
    return value if value in LANGUAGES else DEFAULT_LANG


def t(key: str, lang: str | None = None, **fmt) -> str:
    """Translate ``key`` into ``lang``. Fallback to RU then to the key itself."""
    lang = normalize_lang(lang)
    entry = T.get(lang) or T[DEFAULT_LANG]
    text = entry.get(key) or T[DEFAULT_LANG].get(key) or key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError):
            return text
    return text


def btn_set(key: str) -> set[str]:
    """All language variants of a button label — for ``F.text.in_(...)`` filters."""
    return {T[lang].get(key, "") for lang in LANGUAGES} - {""}
