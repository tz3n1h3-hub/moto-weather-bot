from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🏍️ Сейчас", callback_data="weather"),
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup


def get_after_weather_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 Обновить", callback_data="update"),
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup
