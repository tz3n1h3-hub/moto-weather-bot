from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО KB_MAIN ────────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def get_main_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("— ПРОГНОЗ —", callback_data="weather")
    )
    return markup
# ─── КОНЕЦ KB_MAIN ─────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО KB_AFTER_WEATHER ───────────────────────────────
# ═══════════════════════════════════════════════════════════
def get_after_weather_keyboard(is_subscribed=False):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 ОБНОВИТЬ ПРОГНОЗ", callback_data="weather")
    )
    markup.row(
        InlineKeyboardButton("❗️ ЧТО-ТО НЕ ТАК?", callback_data="feedback_start")
    )
    markup.row(
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup


def get_morning_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 ОБНОВИТЬ ПРОГНОЗ", callback_data="weather")
    )
    markup.row(
        InlineKeyboardButton("❗️ ЧТО-ТО НЕ ТАК?", callback_data="feedback_start")
    )
    markup.row(
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup
# ─── КОНЕЦ KB_AFTER_WEATHER ────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО KB_ABOUT ───────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def get_about_keyboard(is_subscribed=False, is_updater=False):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("— ПРОГНОЗ —", callback_data="weather")
    )
    if is_subscribed:
        markup.row(
            InlineKeyboardButton("❌ Отписаться от утра", callback_data="unsubscribe")
        )
    else:
        markup.row(
            InlineKeyboardButton("✅ Подписаться на утро", callback_data="subscribe")
        )
    if is_updater:
        markup.row(
            InlineKeyboardButton("🔕 Не уведомлять об обновлениях", callback_data="updates_off")
        )
    else:
        markup.row(
            InlineKeyboardButton("🔔 Уведомлять об обновлениях", callback_data="updates_on")
        )
    return markup
# ─── КОНЕЦ KB_ABOUT ────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО KB_SUBSCRIBE ───────────────────────────────────
# ═══════════════════════════════════════════════════════════
def get_subscribe_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Подписаться", callback_data="subscribe_confirm")
    )
    markup.row(
        InlineKeyboardButton("❌ Отмена", callback_data="subscribe_cancel")
    )
    return markup


def get_unsubscribe_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("❌ Да, отписаться", callback_data="unsubscribe_confirm")
    )
    markup.row(
        InlineKeyboardButton("↩️ Остаться", callback_data="unsubscribe_cancel")
    )
    return markup
# ─── КОНЕЦ KB_SUBSCRIBE ────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО KB_FEEDBACK ────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def get_feedback_blocks_keyboard():
    """
    Меню выбора БЛОКА (【A】–【K】) — первый шаг фидбэка.
    """
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("【A】 Шапка", callback_data="feedback_block:A"),
        InlineKeyboardButton("【B】 Вердикт", callback_data="feedback_block:B"),
    )
    markup.row(
        InlineKeyboardButton("【C】 Что на дороге", callback_data="feedback_block:C"),
        InlineKeyboardButton("【D】 На себя", callback_data="feedback_block:D"),
    )
    markup.row(
        InlineKeyboardButton("【E】 Перед выездом", callback_data="feedback_block:E"),
        InlineKeyboardButton("【F】 Погода", callback_data="feedback_block:F"),
    )
    markup.row(
        InlineKeyboardButton("【G】 Период", callback_data="feedback_block:G"),
        InlineKeyboardButton("【H】 Завтра", callback_data="feedback_block:H"),
    )
    markup.row(
        InlineKeyboardButton("【I】 Источники", callback_data="feedback_block:I"),
        InlineKeyboardButton("【J】 Совет", callback_data="feedback_block:J"),
    )
    markup.row(
        InlineKeyboardButton("【K】 Другое", callback_data="feedback_block:K"),
    )
    markup.row(
        InlineKeyboardButton("❌ Отмена", callback_data="feedback_cancel"),
    )
    return markup


def get_feedback_params_keyboard(block=""):
    """
    Меню параметров — второй шаг фидбэка (после выбора блока).
    """
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🌫️ Видимость", callback_data=f"feedback_param:{block}:visibility"),
        InlineKeyboardButton("💨 Ветер", callback_data=f"feedback_param:{block}:wind"),
    )
    markup.row(
        InlineKeyboardButton("🌧️ Осадки", callback_data=f"feedback_param:{block}:rain"),
        InlineKeyboardButton("🌡️ Температура", callback_data=f"feedback_param:{block}:temp"),
    )
    markup.row(
        InlineKeyboardButton("💧 Дорога", callback_data=f"feedback_param:{block}:road"),
        InlineKeyboardButton("🌫️ Туман (не показан)", callback_data=f"feedback_param:{block}:fog"),
    )
    markup.row(
        InlineKeyboardButton("❓ Другое", callback_data=f"feedback_param:{block}:other"),
    )
    markup.row(
        InlineKeyboardButton("↩️ Назад", callback_data="feedback_start"),
    )
    return markup


def get_feedback_direction_keyboard(block, param):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔽 Реально МЕНЬШЕ", callback_data=f"feedback_dir:{block}:{param}:less"),
        InlineKeyboardButton("🔼 Реально БОЛЬШЕ", callback_data=f"feedback_dir:{block}:{param}:more"),
    )
    markup.row(
        InlineKeyboardButton("❌ НЕ ПОКАЗАНО, а есть", callback_data=f"feedback_dir:{block}:{param}:not_shown"),
    )
    markup.row(
        InlineKeyboardButton("⚠️ Другое", callback_data=f"feedback_dir:{block}:{param}:wrong"),
    )
    markup.row(
        InlineKeyboardButton("↩️ Назад", callback_data=f"feedback_block:{block}"),
    )
    return markup


def get_feedback_skip_keyboard(block, param, direction):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("💬 Добавить комментарий", callback_data=f"feedback_comment:{block}:{param}:{direction}"),
    )
    markup.row(
        InlineKeyboardButton("✅ Отправить без комментария", callback_data=f"feedback_send:{block}:{param}:{direction}"),
    )
    markup.row(
        InlineKeyboardButton("❌ Отмена", callback_data="feedback_cancel"),
    )
    return markup


def get_feedback_cancel_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("❌ Отмена", callback_data="feedback_cancel"),
    )
    return markup
# ─── КОНЕЦ KB_FEEDBACK ─────────────────────────────────────
