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
        InlineKeyboardButton("🔄 ОБНОВИТЬ", callback_data="update")
    )
    markup.row(
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup


def get_morning_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 ОБНОВИТЬ", callback_data="update")
    )
    markup.row(
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup


def get_about_keyboard(is_subscribed=False):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("— ПРОГНОЗ —", callback_data="weather")
    )
    if is_subscribed:
        markup.row(
            InlineKeyboardButton("❌ Отписаться", callback_data="unsubscribe")
        )
    else:
        markup.row(
            InlineKeyboardButton("✅ Подписаться", callback_data="subscribe")
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
