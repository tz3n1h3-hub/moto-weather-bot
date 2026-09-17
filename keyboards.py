from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def _subscribe_button(is_subscribed):
    """Универсальная кнопка подписки."""
    if is_subscribed:
        return None
    return InlineKeyboardButton("🌅 Подписка", callback_data="subscribe")


def get_main_keyboard(is_subscribed=False):
    """Клавиатура для /start."""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🏍️ СЕЙЧАС", callback_data="weather")
    )
    sub_btn = _subscribe_button(is_subscribed)
    if sub_btn:
        markup.row(
            sub_btn,
            InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
        )
    else:
        markup.row(
            InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
        )
    return markup


def get_after_weather_keyboard(is_subscribed=False):
    """Клавиатура после показа погоды."""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 ОБНОВИТЬ", callback_data="update")
    )
    sub_btn = _subscribe_button(is_subscribed)
    if sub_btn:
        markup.row(
            sub_btn,
            InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
        )
    else:
        markup.row(
            InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
        )
    return markup


def get_morning_keyboard():
    """Клавиатура для утренней рассылки — только ОБНОВИТЬ."""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 ОБНОВИТЬ", callback_data="update")
    )
    return markup


def get_about_keyboard():
    """Клавиатура для /about."""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🏍️ СЕЙЧАС", callback_data="weather")
    )
    markup.row(
        InlineKeyboardButton("✉️ Разработчику", url="https://t.me/Aleksandr_K8V")
    )
    return markup


def get_subscribe_keyboard():
    """Клавиатура подтверждения подписки."""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Подписаться", callback_data="subscribe_confirm")
    )
    markup.row(
        InlineKeyboardButton("❌ Отмена", callback_data="subscribe_cancel")
    )
    return markup


def get_unsubscribe_keyboard():
    """Клавиатура подтверждения отписки (вызывается командой /unsubscribe)."""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("❌ Да, отписаться", callback_data="unsubscribe_confirm")
    )
    markup.row(
        InlineKeyboardButton("↩️ Остаться", callback_data="unsubscribe_cancel")
    )
    return markup
