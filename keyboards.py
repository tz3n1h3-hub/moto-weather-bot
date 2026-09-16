from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_keyboard(is_subscribed=False):
    """Главное меню. Если подписан — кнопка 'Отписаться', иначе 'Подписка'."""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🏍️ СЕЙЧАС", callback_data="weather")
    )
    sub_btn = (
        InlineKeyboardButton("❌ Отписаться", callback_data="unsubscribe_prompt")
        if is_subscribed
        else InlineKeyboardButton("🌅 Подписка", callback_data="subscribe")
    )
    markup.row(
        sub_btn,
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup


def get_after_weather_keyboard(is_subscribed=False):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 ОБНОВИТЬ", callback_data="update")
    )
    sub_btn = (
        InlineKeyboardButton("❌ Отписаться", callback_data="unsubscribe_prompt")
        if is_subscribed
        else InlineKeyboardButton("🌅 Подписка", callback_data="subscribe")
    )
    markup.row(
        sub_btn,
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup


def get_about_keyboard(is_subscribed=False):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🏍️ СЕЙЧАС", callback_data="weather")
    )
    sub_btn = (
        InlineKeyboardButton("❌ Отписаться", callback_data="unsubscribe_prompt")
        if is_subscribed
        else InlineKeyboardButton("🌅 Подписка", callback_data="subscribe")
    )
    markup.row(
        sub_btn,
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
