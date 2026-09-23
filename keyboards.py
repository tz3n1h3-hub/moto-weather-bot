from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("— ПРОГНОЗ —", callback_data="weather")
    )
    return markup


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


# ============ ФИДБЭК-КЛАВИАТУРЫ ============
def get_feedback_params_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🌫️ Видимость", callback_data="feedback_param:visibility"),
        InlineKeyboardButton("💨 Ветер", callback_data="feedback_param:wind"),
    )
    markup.row(
        InlineKeyboardButton("🌧️ Осадки", callback_data="feedback_param:rain"),
        InlineKeyboardButton("🌡️ Температура", callback_data="feedback_param:temp"),
    )
    markup.row(
        InlineKeyboardButton("💧 Дорога", callback_data="feedback_param:road"),
        InlineKeyboardButton("🌫️ Туман (не показан)", callback_data="feedback_param:fog"),
    )
    markup.row(
        InlineKeyboardButton("❓ Другое", callback_data="feedback_param:other"),
    )
    markup.row(
        InlineKeyboardButton("❌ Отмена", callback_data="feedback_cancel"),
    )
    return markup


def get_feedback_direction_keyboard(param):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔽 Реально МЕНЬШЕ", callback_data=f"feedback_dir:{param}:less"),
        InlineKeyboardButton("🔼 Реально БОЛЬШЕ", callback_data=f"feedback_dir:{param}:more"),
    )
    markup.row(
        InlineKeyboardButton("❌ НЕ ПОКАЗАНО, а есть", callback_data=f"feedback_dir:{param}:not_shown"),
    )
    markup.row(
        InlineKeyboardButton("⚠️ Другое", callback_data=f"feedback_dir:{param}:wrong"),
    )
    markup.row(
        InlineKeyboardButton("↩️ Назад", callback_data="feedback_start"),
    )
    return markup


def get_feedback_skip_keyboard(param, direction):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("💬 Добавить комментарий", callback_data=f"feedback_comment:{param}:{direction}"),
    )
    markup.row(
        InlineKeyboardButton("✅ Отправить без комментария", callback_data=f"feedback_send:{param}:{direction}"),
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
