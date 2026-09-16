from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🏍️ Сейчас", callback_data="weather"),
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    markup.row(
        InlineKeyboardButton("🌅 Подписка на утро", callback_data="subscribe")
    )
    return markup


def get_after_weather_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 Обновить", callback_data="update"),
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup


def get_about_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🏍️ Сейчас", callback_data="weather"),
        InlineKeyboardButton("🌅 Подписка", callback_data="subscribe")
    )
    markup.row(
        InlineKeyboardButton("✉️ Написать разработчику", url="https://t.me/Aleksandr_K8V")
    )
    return markup


def get_subscribe_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Подписаться", callback_data="subscribe_confirm"),
        InlineKeyboardButton("❌ Отмена", callback_data="subscribe_cancel")
    )
    return markup
