import json
import os
import random
import threading
import time
from datetime import datetime

import requests
import telebot
from flask import Flask, jsonify
from telebot.apihelper import ApiTelegramException

from config import (
    BOT_TOKEN, MY_BOT_USERNAME,
    USERS_FILE, SUBSCRIBERS_FILE, ADMIN_ID, MINSK_TZ,
    UPSTASH_URL, UPSTASH_TOKEN,
)
from weather import (
    get_weather, get_forecast_tomorrow,
    get_short_forecast, get_daylight_info, hpa_to_mmhg,
)
from analyzer import (
    analyze_risks, get_short_verdict, get_rider_verdict,
    get_gear_short, get_tech_check, get_tip,
)
from keyboards import (
    get_main_keyboard, get_after_weather_keyboard, get_morning_keyboard,
    get_about_keyboard, get_subscribe_keyboard, get_unsubscribe_keyboard
)


# ============ ПРОВЕРКА КОНФИГА ============
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден!", flush=True)
    exit(1)

if UPSTASH_URL and UPSTASH_TOKEN:
    print("✅ Хранилище: Upstash Redis", flush=True)
else:
    print("⚠️ Хранилище: локальные файлы (Upstash не настроен)", flush=True)

print("✅ METAR + Open-Meteo (→ wttr.in fallback)", flush=True)


# ============ ИНИЦИАЛИЗАЦИЯ ============
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)


# ============ НЕВИДИМЫЕ ПРОБЕЛЫ ============
Z = "\u200b"
DEV_USERNAME = f"@{Z}Aleksandr_K8V"


# ============ UPSTASH REDIS ============
UPSTASH_ENABLED = bool(UPSTASH_URL and UPSTASH_TOKEN)


def _redis(cmd, *args):
    if not UPSTASH_ENABLED:
        return None
    try:
        url = f"{UPSTASH_URL}/{cmd}"
        if args:
            url += "/" + "/".join(str(a) for a in args)
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"},
            timeout=5
        )
        if r.status_code != 200:
            print(f"⚠️ Redis {cmd} → {r.status_code}", flush=True)
            return None
        return r.json().get("result")
    except Exception as e:
        print(f"⚠️ Redis {cmd}: {e}", flush=True)
        return None


# ============ ПОЛЬЗОВАТЕЛИ ============
def load_users():
    if UPSTASH_ENABLED:
        result = _redis("smembers", "users")
        if result is None:
            return []
        try:
            return [int(x) for x in result]
        except (ValueError, TypeError):
            return []

    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_user(user_id):
    if UPSTASH_ENABLED:
        _redis("sadd", "users", user_id)
        return
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        try:
            with open(USERS_FILE, "w") as f:
                json.dump(users, f)
        except Exception as e:
            print(f"⚠️ user save: {e}", flush=True)


def get_users_count():
    if UPSTASH_ENABLED:
        result = _redis("scard", "users")
        return int(result) if result else 0
    return len(load_users())


# ============ ПОДПИСЧИКИ ============
def load_subscribers():
    if UPSTASH_ENABLED:
        result = _redis("smembers", "subscribers")
        if result is None:
            return []
        try:
            return [int(x) for x in result]
        except (ValueError, TypeError):
            return []

    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_subscriber(user_id):
    if UPSTASH_ENABLED:
        _redis("sadd", "subscribers", user_id)
        return
    subs = load_subscribers()
    if user_id not in subs:
        subs.append(user_id)
        try:
            with open(SUBSCRIBERS_FILE, "w") as f:
                json.dump(subs, f)
        except Exception as e:
            print(f"⚠️ sub save: {e}", flush=True)


def remove_subscriber(user_id):
    if UPSTASH_ENABLED:
        _redis("srem", "subscribers", user_id)
        return
    subs = load_subscribers()
    if user_id in subs:
        subs.remove(user_id)
        try:
            with open(SUBSCRIBERS_FILE, "w") as f:
                json.dump(subs, f)
        except Exception as e:
            print(f"⚠️ sub remove: {e}", flush=True)


def is_subscribed(user_id):
    if UPSTASH_ENABLED:
        result = _redis("sismember", "subscribers", user_id)
        return result == 1
    return user_id in load_subscribers()


def get_subscribers_count():
    if UPSTASH_ENABLED:
        result = _redis("scard", "subscribers")
        return int(result) if result else 0
    return len(load_subscribers())


# ============ УТРЕННИЙ СТАТУС ============
def get_last_morning_date():
    if UPSTASH_ENABLED:
        result = _redis("get", "last_morning_date")
        return result if result else None
    return None


def set_last_morning_date(date_str):
    if UPSTASH_ENABLED:
        _redis("set", "last_morning_date", date_str)


# ============ ЦИТАТЫ ============
RIDER_QUOTES = [
    "«Дорога — лучший психотерапевт. И самый дешёвый.»",
    "«Райдер не тот, кто быстрее. Райдер — тот, кто дожил до дома.»",
    "«На мотоцикле ты не пассажир. Ты — сам за всё.»",
    "«Газ в пол — только если мозг в черепе.»",
    "«Лучший тюнинг — это прокладка между рулём и сиденьем.»",
    "«Ветер в лицо — единственная реклама, которая работает.»",
    "«Сезон длиной в жизнь — вот цель.»",
    "«На двух колёсах свобода, но и ответственность ×2.»",
    "«Резина цепляет асфальт. Голова — реальность.»",
    "«Холодный асфальт не прощает уверенности без опыта.»",
    "«Мотоцикл — это не транспорт. Это состояние.»",
    "«Едешь быстро — думай быстрее.»",
    "«Лучше приехать позже, чем не приехать вовсе.»",
    "«Соблюдай дистанцию — она спасает.»",
    "«Сначала тормоз, потом поворот.»",
    "«Ночью сова не ты — делай паузы.»",
    "«Не тот райдер, кто гонит. А тот, кто чувствует.»",
    "«Мокрый асфальт — не место для лихачества.»",
    "«На мотоцикле каждый выезд — экзамен.»",
    "«Свой мотоцикл знаешь лучше всех. Проверяй его сам.»",
]


def get_random_quote():
    return random.choice(RIDER_QUOTES)


def get_alcohol_warning():
    now = datetime.now(MINSK_TZ)
    weekday = now.weekday()

    if weekday == 4:
        return "🍺 Пятница. За рулём — трезвый. Иначе — такси."
    elif weekday == 5:
        return "🍻 Суббота. Пил вчера? За руль не садись."
    elif weekday == 6:
        return "🍷 Воскресенье. Реакция ещё не та — не рискуй."
    else:
        return "🚫 За рулём — трезвый. Алкоголь = реакция ×3 хуже."


# ============ ФОРМАТИРОВАНИЕ ============
WEEKDAYS_RU = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"
]


def format_visibility(v):
    if v is None:
        return "—"
    if v >= 10000:
        return "10+км"
    if v >= 1000:
        km = v / 1000
        if km == int(km):
            return f"{int(km)}км"
        return f"{km:.1f}км"
    return f"{v}м"


def shorten_cond(cond):
    if not cond:
        return "—"
    cond_lower = cond.lower()
    replacements = {
        "преимущественно ясно": "ясно",
        "переменная облачность": "переменно",
        "значительная облачность": "облачно",
        "облачно с прояснениями": "прояснения",
        "преимущественно облачно": "облачно",
    }
    for k, v in replacements.items():
        if k in cond_lower:
            return v
    return cond_lower


def avg(a, b):
    """Среднее двух чисел с округлением до 1 знака. Пропускает None."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return round((a + b) / 2, 1)


def fmt_num(v):
    """Форматирует число: 11.0 → 11, 11.5 → 11.5"""
    if v is None:
        return "—"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def build_risk_bar(score):
    """Строит бар риска из 10 квадратов."""
    score = max(0, min(10, score))
    if score >= 9:
        color = "🟪"
    elif score >= 7:
        color = "🟥"
    elif score >= 5:
        color = "🟧"
    elif score >= 3:
        color = "🟨"
    else:
        color = "🟩"
    filled = color * score
    empty = "⬜️" * (10 - score)
    return f"{filled}{empty}"


def fmt_field(name, m_val, om_val, unit="", m_key="M", om_key="OM"):
    """
    Формат: 🌡️ Температура: 11.5°C (M11|OM12)
    """
    if m_val is None and om_val is None:
        return f"{name}: —"

    avg_val = avg(m_val, om_val)

    # Основное значение
    if unit:
        main = f"{fmt_num(avg_val)}{unit}"
    else:
        main = fmt_num(avg_val)

    # Источники в скобках
    m_str = fmt_num(m_val) if m_val is not None else "—"
    om_str = fmt_num(om_val) if om_val is not None else "—"

    return f"{name}: {main} ({m_key}{m_str}|{om_key}{om_str})"


# ============ ТЕКСТЫ ============
ABOUT_TEXT = f"""🏍️ <b>MOTOWEATHER · МИНСК</b>

<b>Источники:</b>
M  — METAR (аэропорт Минск, UMMS)
OM — Open-Meteo (Минск)
W  — wttr.in (Минск)

<b>Что показывает:</b>
• Погода сейчас (усреднение M+OM)
• Риск 0-10 для райдера
• Экипировка и подготовка
• Прогноз на ночь и завтра

<b>Подписка на утро:</b>
Прогноз каждый день в 7:00

<b>Отписка:</b> /unsubscribe

<b>👨‍💻 Разработчик:</b> {DEV_USERNAME}"""


SUBSCRIBE_TEXT = """🌅 <b>Подписка на утро</b>

Каждый день в <b>7:00</b>:
Погода в Минске
Вердикт
Экипировка
Прогноз
Цитата

Подписаться?"""

SUBSCRIBE_CONFIRMED = """✅ <b>Подписка активирована</b>

Прогноз в 7:00 каждый день.

Отписаться: /unsubscribe"""

SUBSCRIBE_CANCELED = """❌ <b>Подписка отменена</b>

Жми «🌅 Подписка» чтобы вернуться."""

UNSUBSCRIBE_PROMPT = """❌ <b>Отписаться от рассылки?</b>

Перестанешь получать утренний прогноз в 7:00."""

UNSUBSCRIBED = """❌ <b>Отписан от рассылки</b>

Жми «🌅 Подписка» чтобы вернуться."""

UNSUBSCRIBE_CANCELED = """✅ <b>Остаёмся!</b>

Прогноз в 7:00 продолжит приходить."""

ALREADY_SUBSCRIBED = """ℹ️ <b>Ты уже подписан</b>

Отписаться: /unsubscribe"""


# ============ ХЕЛПЕР ============
def edit_or_send(chat_id, message_id, text, reply_markup):
    """Для /start, /about, подписки — редактирование."""
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return True
    except Exception as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return True
        try:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e2:
            print(f"⚠️ edit_or_send: {e2}", flush=True)
        return False


def delete_and_send(chat_id, old_message_id, text, reply_markup):
    """Для обновления погоды — удалить старое + отправить новое (курсор вверх)."""
    try:
        bot.delete_message(chat_id, old_message_id)
    except Exception as e:
        print(f"⚠️ delete: {e}", flush=True)
    try:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        print(f"⚠️ send: {e}", flush=True)
