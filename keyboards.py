from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def _subscribe_button(is_subscribed):
    """Универсальная кнопка подписки/отписки."""
    if is_subscribed:
        return InlineKeyboardButton("❌ Отписаться", callback_data="unsubscribe_prompt")
    return InlineKeyboardButton("🌅 Подписка", callback_data="subscribe")


def get_main_keyboard(is_subscribed=False):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🏍️ СЕЙЧАС", callback_data="weather")
    )
    markup.row(
        _subscribe_button(is_subscribed),
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup


def get_after_weather_keyboard(is_subscribed=False):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 ОБНОВИТЬ", callback_data="update")
    )
    markup.row(
        _subscribe_button(is_subscribed),
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup


def get_about_keyboard(is_subscribed=False):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🏍️ СЕЙЧАС", callback_data="weather")
    )
    markup.row(
        _subscribe_button(is_subscribed),
        InlineKeyboardButton("✉️ Разработчику", url="https://t.me/Aleksandr_K8V")
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
