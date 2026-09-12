from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📊 Сейчас", callback_data="weather"),
        InlineKeyboardButton("📅 Завтра", callback_data="forecast")
    )
    markup.row(
        InlineKeyboardButton("📆 Неделя", callback_data="weekly"),
        InlineKeyboardButton("🏍️ Советы", callback_data="tips")
    )
    markup.row(InlineKeyboardButton("ℹ️ О проекте", callback_data="about"))
    return markup


def get_after_weather_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 Сейчас", callback_data="update"),
        InlineKeyboardButton("📅 Завтра", callback_data="forecast")
    )
    markup.row(
        InlineKeyboardButton("📆 Неделя", callback_data="weekly"),
        InlineKeyboardButton("🏍️ Советы", callback_data="tips")
    )
    markup.row(InlineKeyboardButton("ℹ️ О проекте", callback_data="about"))
    return markup