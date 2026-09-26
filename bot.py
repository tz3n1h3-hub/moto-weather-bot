import json
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import requests
import telebot
from flask import Flask, jsonify, request
from telebot.apihelper import ApiTelegramException

from config import (
    BOT_TOKEN, MY_BOT_USERNAME,
    USERS_FILE, SUBSCRIBERS_FILE, UPDATERS_FILE, ADMIN_ID, MINSK_TZ,
    UPSTASH_URL, UPSTASH_TOKEN, OWM_API_KEY,
    BOT_VERSION, BOT_VERSION_DATE, BOT_VERSION_NOTIFY, BOT_CHANGELOG,
    MINSK_POINTS_ENABLED,
)
from weather import (
    get_weather, get_forecast_tomorrow,
    get_short_forecast, get_daylight_info, hpa_to_mmhg,
    merge_weather_data, get_twilight_state,
    get_astro_night_score,
)
from analyzer import (
    analyze_risks, get_short_verdict, get_rider_verdict,
    get_gear_short, get_tech_check, get_tip,
)
from keyboards import (
    get_main_keyboard, get_after_weather_keyboard, get_morning_keyboard,
    get_about_keyboard, get_subscribe_keyboard, get_unsubscribe_keyboard,
    get_feedback_blocks_keyboard, get_feedback_params_keyboard,
    get_feedback_direction_keyboard, get_feedback_skip_keyboard,
    get_feedback_cancel_keyboard,
)
import feedback as fb


def math_round(x, digits=0):
    if x is None:
        return None
    if digits == 0:
        if x >= 0:
            return int(x + 0.5)
        return int(x - 0.5)
    q = Decimal(10) ** -digits
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))


if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден!", flush=True)
    exit(1)

print(f"🏍️ MotoWeather v{BOT_VERSION} ({BOT_VERSION_DATE})", flush=True)

if UPSTASH_URL and UPSTASH_TOKEN:
    print("✅ Хранилище: Upstash Redis", flush=True)
else:
    print("⚠️ Хранилище: локальные файлы", flush=True)

if OWM_API_KEY:
    print("✅ Источники: METAR + Open-Meteo + wttr.in + OpenWeatherMap", flush=True)
else:
    print("⚠️ Источники: METAR + Open-Meteo + wttr.in (OWM отключён)", flush=True)


bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

NBSP = "\u00A0"
INDENT = "     "  # 5 пробелов

UPSTASH_ENABLED = bool(UPSTASH_URL and UPSTASH_TOKEN)

_user_last_weather = {}
ANTISPAM_SEC = 3
_feedback_state = {}


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


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО USERS ──────────────────────────────────────────
# ═══════════════════════════════════════════════════════════
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
# ─── КОНЕЦ USERS ────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО SUBSCRIBERS ────────────────────────────────────
# ═══════════════════════════════════════════════════════════
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
# ─── КОНЕЦ SUBSCRIBERS ─────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО UPDATERS ───────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def load_updaters():
    if UPSTASH_ENABLED:
        result = _redis("smembers", "updaters")
        if result is None:
            return []
        try:
            return [int(x) for x in result]
        except (ValueError, TypeError):
            return []
    if os.path.exists(UPDATERS_FILE):
        try:
            with open(UPDATERS_FILE) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_updater(user_id):
    if UPSTASH_ENABLED:
        _redis("sadd", "updaters", user_id)
        return
    ups = load_updaters()
    if user_id not in ups:
        ups.append(user_id)
        try:
            with open(UPDATERS_FILE, "w") as f:
                json.dump(ups, f)
        except Exception as e:
            print(f"⚠️ updater save: {e}", flush=True)


def remove_updater(user_id):
    if UPSTASH_ENABLED:
        _redis("srem", "updaters", user_id)
        return
    ups = load_updaters()
    if user_id in ups:
        ups.remove(user_id)
        try:
            with open(UPDATERS_FILE, "w") as f:
                json.dump(ups, f)
        except Exception as e:
            print(f"⚠️ updater remove: {e}", flush=True)


def is_updater(user_id):
    if UPSTASH_ENABLED:
        result = _redis("sismember", "updaters", user_id)
        return result == 1
    return user_id in load_updaters()


def get_updaters_count():
    if UPSTASH_ENABLED:
        result = _redis("scard", "updaters")
        return int(result) if result else 0
    return len(load_updaters())
# ─── КОНЕЦ UPDATERS ────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО MORNING_STATE ──────────────────────────────────
# ═══════════════════════════════════════════════════════════
LAST_MORNING_FILE = "last_morning.txt"


def get_last_morning_date():
    if UPSTASH_ENABLED:
        result = _redis("get", "last_morning_date")
        return result if result else None
    try:
        if os.path.exists(LAST_MORNING_FILE):
            with open(LAST_MORNING_FILE) as f:
                return f.read().strip() or None
    except Exception:
        pass
    return None


def set_last_morning_date(date_str):
    if UPSTASH_ENABLED:
        _redis("set", "last_morning_date", date_str)
    try:
        with open(LAST_MORNING_FILE, "w") as f:
            f.write(date_str)
    except Exception as e:
        print(f"⚠️ last_morning save: {e}", flush=True)


def get_last_bot_msg(chat_id):
    if UPSTASH_ENABLED:
        result = _redis("get", f"last_msg:{chat_id}")
        try:
            return int(result) if result else None
        except (ValueError, TypeError):
            return None
    return None


def set_last_bot_msg(chat_id, message_id):
    if UPSTASH_ENABLED:
        _redis("set", f"last_msg:{chat_id}", message_id)
# ─── КОНЕЦ MORNING_STATE ───────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО QUOTES ─────────────────────────────────────────
# ═══════════════════════════════════════════════════════════
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
# ─── КОНЕЦ QUOTES ──────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО FORMATTING ─────────────────────────────────────
# ═══════════════════════════════════════════════════════════
WEEKDAYS_RU = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"
]


def fmt_num(v):
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        return str(math_round(v, 0))
    return str(v)


def fmt_avg(values, unit=""):
    vals = [v for v in values if v is not None]
    if not vals:
        return f"—{NBSP}{unit}" if unit else "—"
    avg = sum(vals) / len(vals)
    s = str(math_round(avg, 0))
    return f"{s}{NBSP}{unit}" if unit else s


def format_visibility(v):
    if v is None:
        return "—"
    if v >= 10000:
        return f"10+{NBSP}км"
    if v >= 1000:
        km = v / 1000
        if km == int(km):
            return f"{int(km)}{NBSP}км"
        return f"{km:.1f}{NBSP}км".replace(".", ",")
    return f"{int(v)}{NBSP}м"


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


def classify_clouds(avg_cloud_pct, metar_text):
    if avg_cloud_pct is None:
        return metar_text or "—"
    if avg_cloud_pct >= 85:
        return "пасмурно"
    if avg_cloud_pct >= 70:
        return "облачно"
    if avg_cloud_pct >= 40:
        return "переменно"
    if avg_cloud_pct >= 15:
        return "малооблачно"
    return "ясно"


def build_risk_bar(score):
    score = max(0, min(10, score))
    if score == 0:
        return ""
    return "💀" * score


def avg_uv(live_values):
    vals = [v for v in live_values if v is not None]
    if not vals:
        return None
    return math_round(sum(vals) / len(vals), 0)


def uv_level(uv):
    if uv is None:
        return ""
    if uv <= 2:
        return "низкий"
    if uv <= 5:
        return "умеренный"
    if uv <= 7:
        return "высокий"
    if uv <= 10:
        return "очень высокий"
    return "экстремальный"


def uv_advice(uv):
    if uv is None:
        return ""
    if uv <= 2:
        return "можно без крема"
    if uv <= 5:
        return "крем не помешает"
    if uv <= 7:
        return "закрой шею и руки"
    if uv <= 10:
        return "минимум открытой кожи"
    return "лучше не выезжать днём"


def wind_dir_short(full):
    if not full or not isinstance(full, str):
        return None
    m = {
        "С": "С", "СВ": "С-В", "В": "В", "ЮВ": "Ю-В",
        "Ю": "Ю", "ЮЗ": "Ю-З", "З": "З", "СЗ": "С-З",
    }
    part = full.split(" ")[0]
    if part in m:
        return m[part]
    if part == "переменный":
        return "перем."
    if part == "штиль":
        return "штиль"
    return None


def indent_multiline(text, indent=INDENT):
    """Каждую строку текста сдвигает на indent."""
    if not text:
        return ""
    lines = text.split("\n")
    return "\n".join(f"{indent}{line}" for line in lines)
# ─── КОНЕЦ FORMATTING ──────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО TEXTS (START_TEXT и др.) ───────────────────────
# ═══════════════════════════════════════════════════════════
START_TEXT = f"""🌤 <b>MOTOWEATHER · МИНСК</b>

<b>Что это?</b>
Погодный ориентир для райдеров Минска.
Не точный прогноз, а честная сводка:
ехать сегодня или нет.

<b>Откуда беру данные:</b>
• METAR аэропорта Минск (UMMS) — фактическая погода. Аэропорт в 20 км от центра, поэтому это лишь один из источников.
• Open-Meteo (5 точек Минска), OpenWeatherMap, wttr — прогнозные сервисы.

<b>Как считаю:</b>
1. Собираю данные со всех источников.
2. Убираю выбросы.
3. Осадки — голосование источников (wttr один — не верю).
4. Видимость — минимум, но с проверкой на разброс (аэропорт отдельно).
5. Многоточечный прогноз OM — 5 районов Минска.

<b>Периоды дня — по Солнцу:</b>
• 🌙 НОЧЬ — от темноты до рассвета
• 🌄 РАССВЕТ — от первых лучей до восхода
• 🌅 УТРО — от восхода до полудня
• ☀️ ДЕНЬ — от полудня до сумерек (за 60 мин до заката)
• 🌆 ВЕЧЕР — от сумерек до темноты

<b>Блоки сообщения 【A】–【J】</b>
Можно ссылаться на блок при жалобе: «блок 【B】 неверно».

<b>Заметили ошибку?</b>
Жмите «❗️ ЧТО-ТО НЕ ТАК?» — выберите блок и параметр.

—
👨‍💻 Разработчик: <a href="https://t.me/Aleksandr_K8V">@Aleksandr_K8V</a>
🏍️ v{BOT_VERSION}"""


SUBSCRIBE_TEXT = """🌅 <b>Подписка на утро</b>

Каждый день в <b>7:00</b>:
• погода в Минске;
• вердикт — ехать или нет;
• экипировка;
• прогноз;
• цитата.

Подписаться?"""

SUBSCRIBE_CONFIRMED = """✅ <b>Подписка активирована</b>

Прогноз в 7:00 каждый день."""

SUBSCRIBE_CANCELED = """❌ <b>Подписка отменена</b>

Жми «ПРОГНОЗ» чтобы вернуться."""

UNSUBSCRIBE_PROMPT = """❌ <b>Отписаться от рассылки?</b>

Перестанешь получать утренний прогноз в 7:00."""

UNSUBSCRIBED = """❌ <b>Отписан от рассылки</b>

Жми «ПРОГНОЗ» — и вперёд."""

UNSUBSCRIBE_CANCELED = """✅ <b>Остаёмся!</b>

Прогноз в 7:00 продолжит приходить."""

ALREADY_SUBSCRIBED = """ℹ️ <b>Ты уже подписан</b>

Отписаться можно в «О проекте»."""

UPDATES_ON_TEXT = """🔔 <b>Уведомления об обновлениях</b>

Будешь получать сообщения о новых версиях.

Отключить можно в «О проекте»."""

UPDATES_OFF_TEXT = """🔕 <b>Уведомления отключены</b>

Включить обратно — в «О проекте»."""
# ─── КОНЕЦ TEXTS ───────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО SEND_OR_EDIT ───────────────────────────────────
# ═══════════════════════════════════════════════════════════
def send_or_edit(chat_id, text, reply_markup=None):
    last_id = get_last_bot_msg(chat_id)
    if last_id:
        try:
            bot.delete_message(chat_id, last_id)
        except Exception as e:
            print(f"⚠️ delete last_msg {last_id}: {e}", flush=True)
    try:
        sent = bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
        set_last_bot_msg(chat_id, sent.message_id)
        return sent.message_id
    except Exception as e:
        print(f"⚠️ send_or_edit: {e}", flush=True)
        return None


def fmt_spread(agree_values):
    if not agree_values:
        return None
    filtered = [(v, u) for v, u in agree_values if v and v >= 2]
    if len(filtered) < 2:
        return None
    parts = []
    for v, unit in filtered:
        v_str = str(math_round(v, 0)) if v == int(v) else f"{v:.1f}".replace(".", ",")
        parts.append(f"±{v_str}{NBSP}{unit}")
    return "📊 Разброс: " + " · ".join(parts)


def filter_rain_risks(risks):
    if not risks:
        return []
    keywords = ("дождь", "осадк", "морось", "ливн", "влажн", "мокро")
    return [
        r for r in risks
        if not any(kw in r.lower() for kw in keywords)
    ]
# ─── КОНЕЦ SEND_OR_EDIT ────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО BUILD_WEATHER_MESSAGE ──────────────────────────
# ═══════════════════════════════════════════════════════════
def build_weather_message(w, a_city, short, f, is_morning=False):
    if not isinstance(short, dict):
        print(f"⚠️ short не dict: type={type(short).__name__}", flush=True)
        short = {}

    now_dt = datetime.now(MINSK_TZ)
    m = w.get("m") or {}
    om = w.get("om") or {}
    ww = w.get("w") or {}
    ow = w.get("ow") or {}
    sources_live = w.get("sources_live", [])
    formula = w.get("formula", "")

    sunrise = w.get("sunrise")
    sunset = w.get("sunset")

    avg_w = a_city.get("avg_w") if isinstance(a_city, dict) else None
    if not avg_w:
        avg_w = {}

    weekday = WEEKDAYS_RU[now_dt.weekday()]
    date_str = f"{now_dt.day} {MONTHS_RU[now_dt.month - 1]}"
    time_str = now_dt.strftime("%H:%M")

    header_icon = m.get("weather_emoji") or "🌤"
    if w.get("is_night") and header_icon in ("☀️", "🌤️", ""):
        header_icon = "🌙"
    if is_morning:
        header_icon = "🌅"

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_A — Шапка ────────────────────────────────
    # ═══════════════════════════════════════════════════════════
    block_a = f"""【A】{header_icon} <b>MOTOWEATHER · МИНСК</b>
{INDENT}{weekday} · {date_str} · {time_str}"""
    # ─── КОНЕЦ BLOCK_A ──────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_B — Вердикт ──────────────────────────────
    # ═══════════════════════════════════════════════════════════
    score = a_city["score"]
    verdict = get_rider_verdict(score, now_dt.month)
    bar = build_risk_bar(score)

    verdict_lines = [f"СЕЙЧАС <b>{verdict}!</b>", f"РИСК: {score}/10"]
    if bar:
        verdict_lines.append(bar)
    block_b = "【B】" + f"\n{INDENT}".join(verdict_lines)
    # ─── КОНЕЦ BLOCK_B ──────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_C — Что на дороге ────────────────────────
    # ═══════════════════════════════════════════════════════════
    risk_factors = a_city["risks"][:4]
    risk_text = "\n".join(risk_factors) if risk_factors else "✅ Дорога чистая"

    block_c = f"""【C】<b>ЧТО НА ДОРОГЕ</b>
{indent_multiline(risk_text)}"""

    recs = a_city.get("recommendations", [])
    if score >= 3 and recs:
        rec_lines = recs[:3]
        recs_text = "➡️ " + "\n➡️ ".join(rec_lines)
        block_c += "\n<i>" + indent_multiline(recs_text) + "</i>"
    # ─── КОНЕЦ BLOCK_C ──────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_D — На себя ──────────────────────────────
    # ═══════════════════════════════════════════════════════════
    gear = get_gear_short(
        a_city.get("feels_like", m.get("feels_like") or 0),
        avg_w.get("is_rain", False) or m.get("is_rain", False) or ww.get("is_rain", False),
        w.get("is_night", False),
        (m.get("wind_speed") or om.get("wind_speed") or 0),
    )
    gear_block = "\n".join(gear)
    block_d = f"""【D】<b>НА СЕБЯ</b>
{indent_multiline(gear_block)}"""
    # ─── КОНЕЦ BLOCK_D ──────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_E — Перед выездом ────────────────────────
    # ═══════════════════════════════════════════════════════════
    tech = get_tech_check(
        a_city.get("feels_like", m.get("feels_like") or 0),
        w.get("is_night", False),
        avg_w.get("is_rain", False) or m.get("is_rain", False) or ww.get("is_rain", False),
        m.get("humidity"), m.get("dew_point"),
    )
    tech_block = "\n".join(f"✅ {t}" for t in tech)
    block_e = f"""【E】<b>ПЕРЕД ВЫЕЗДОМ</b>
{indent_multiline(tech_block)}"""
    # ─── КОНЕЦ BLOCK_E ──────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_F — Текущая погода ───────────────────────
    # ═══════════════════════════════════════════════════════════
    def gather(key, sources_keys):
        return [src.get(key) for code, src in sources_keys if src]

    src_map = [("M", m), ("OM", om), ("W", ww), ("OW", ow)]

    weather_lines = []
    weather_lines.append(f"🌡️ Температура: {fmt_avg(gather('temp', src_map), '°C')}")
    weather_lines.append(f"🤔 Ощущается: {fmt_avg(gather('feels_like', src_map), '°C')}")

    soil = om.get("soil_temp") if om else None
    if soil is not None:
        weather_lines.append(f"🌱 Почва: {fmt_num(soil)}{NBSP}°C")

    wind_vals = [v for v in gather("wind_speed", src_map) if v is not None]
    gust_vals = [g for g in gather("wind_gust", src_map) if g is not None]
    wind_avg = math_round(sum(wind_vals) / len(wind_vals), 0) if wind_vals else None
    gust_avg = math_round(sum(gust_vals) / len(gust_vals), 0) if gust_vals else None

    wind_line = "💨 Ветер: "
    if wind_avg is not None:
        wind_line += f"{wind_avg}{NBSP}м/с"
        if gust_avg is not None and gust_avg > wind_avg:
            wind_line += f" (до {gust_avg}{NBSP}м/с)"
        wind_dir_raw = m.get("wind_direction") or om.get("wind_direction")
        short_dir = wind_dir_short(wind_dir_raw) if isinstance(wind_dir_raw, str) else None
        if short_dir:
            wind_line += f", {short_dir}"
    else:
        wind_line += "—"
    weather_lines.append(wind_line)

          # --- Видимость ---
    vis_vals = [v for v in gather("visibility", src_map) if v is not None and v > 0]
    if vis_vals:
        min_vis_m = min(vis_vals)
        max_vis_m = max(vis_vals)
        big_spread = (max_vis_m > 0 and min_vis_m > 0 and max_vis_m / min_vis_m >= 5.0)

        if big_spread:
            shown_vis = math_round(sum(vis_vals) / len(vis_vals), 0)
            if min_vis_m >= 1000:
                ap_str = f"{int(min_vis_m / 1000)} км"
            else:
                ap_str = f"{int(min_vis_m)} м"
            suffix = f" · в аэропорту {ap_str}"
        else:
            shown_vis = min_vis_m
            suffix = ""

        # Пометка "дымка" при 5-8 км и высокой влажности + точке росы близко
        humidity_now = avg_w.get("humidity") or m.get("humidity")
        dew_now = avg_w.get("dew_point")
        temp_now = avg_w.get("temp") or m.get("temp")
        haze_suffix = ""
        if shown_vis < 8000 and humidity_now and humidity_now >= 90:
            if dew_now is not None and temp_now is not None and (temp_now - dew_now) <= 2:
                haze_suffix = " · дымка"

        if shown_vis >= 10000:
            vis_str = f"10+{NBSP}км"
        elif shown_vis >= 1000:
            km_int = math_round(shown_vis / 1000, 0)
            vis_str = f"{km_int}{NBSP}км"
        else:
            vis_str = f"{int(shown_vis)}{NBSP}м"

        if shown_vis < 500:
            vis_str = "⚠️" + vis_str

        weather_lines.append(f"👁️ Видимость: {vis_str}{suffix}{haze_suffix}")
    else:
        weather_lines.append("👁️ Видимость: —")

    weather_lines.append(f"💧 Влажность: {fmt_avg(gather('humidity', src_map), '%')}")
    weather_lines.append(f"💦 Точка росы: {fmt_avg(gather('dew_point', src_map), '°C')}")

    # --- Облачность ---
    cloud_vals = [v for v in gather("clouds_pct", src_map) if v is not None]
    metar_cloud = m.get("cloud_text") if m.get("cloud_text") else None

    if cloud_vals:
        avg_cloud = math_round(sum(cloud_vals) / len(cloud_vals), 0)
        cloud_label = classify_clouds(avg_cloud, metar_cloud)
        if avg_cloud >= 70:
            weather_lines.append(f"🌥️ Облачность: {avg_cloud}{NBSP}%")
        else:
            weather_lines.append(f"🌥️ Облачность: {cloud_label} ({avg_cloud}{NBSP}%)")
    elif metar_cloud:
        weather_lines.append(f"🌥️ Облачность: {metar_cloud}")
    else:
        weather_lines.append("🌥️ Облачность: —")

    # --- Осадки (ФИКС 1.8.3) ---
      precip_vals = [v for v in gather("precip_mm", src_map) if v is not None and v > 0]
    rain_prob_now = w.get("rain_prob_now")
    is_rain_anywhere = w.get("is_rain_anywhere", False)
    is_drizzle_anywhere = w.get("is_drizzle_anywhere", False)

    avg_precip = (sum(precip_vals) / len(precip_vals)) if precip_vals else 0.0

    if is_rain_anywhere and avg_precip < 0.5:
        precip_line = "☔️ Осадки: слабый дождь"
        if rain_prob_now and rain_prob_now >= 30:
            precip_line += f" · {rain_prob_now}{NBSP}%"
        weather_lines.append(precip_line)
    elif is_rain_anywhere and avg_precip >= 0.5:
        precip_str = f"{avg_precip:.1f}".replace(".", ",")
        precip_line = f"🌧️ Осадки: {precip_str}{NBSP}мм"
        if rain_prob_now and rain_prob_now >= 30:
            precip_line += f" · вероятность {rain_prob_now}{NBSP}%"
        weather_lines.append(precip_line)
    elif is_drizzle_anywhere:
        weather_lines.append("🌦️ Осадки: морось")
    elif rain_prob_now and rain_prob_now >= 40:
        weather_lines.append(f"🌦️ Осадки: 0{NBSP}мм · вероятность {rain_prob_now}{NBSP}%")
    elif m.get("is_rain"):
        weather_lines.append(f"🌧️ Осадки: {m.get('weather_text') or 'дождь'}")

    weather_lines.append(f"📊 Давление: {fmt_avg(gather('pressure_mmhg', src_map), 'мм рт. ст.')}")

    twilight = get_twilight_state(sunrise, sunset)
    weather_lines.append(f"🌇 На улице: {twilight}")

    if sunrise and sunset:
        weather_lines.append(f"🌅 Рассвет: {sunrise} · 🌇 Закат: {sunset}")

    uv = avg_uv([m.get("uv_index"), om.get("uv_index"),
                 ww.get("uv_index"), ow.get("uv_index")])
    if uv is not None:
        lvl = uv_level(uv)
        advice = uv_advice(uv)
        weather_lines.append(f"☀️ UV-индекс: {uv}{NBSP}({lvl}) — {advice}")

    weather_block = "\n".join(weather_lines)
    block_f = f"""【F】🟢 <b>ТЕКУЩАЯ ПОГОДА:</b>
{indent_multiline(weather_block)}"""
    # ─── КОНЕЦ BLOCK_F ──────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_F2 — Осадки + видимость по районам ───────
    # ═══════════════════════════════════════════════════════════
    districts = w.get("precipitation_by_districts", [])
    districts_block = ""
    if districts:
        # Осадки по районам
        max_precip = max((d.get("precip_mm", 0) or 0) for d in districts)
        precip_lines = []
        if max_precip >= 0.3:
            for d in districts:
                p = d.get("precip_mm", 0) or 0
                name = d.get("name", "?")
                if p >= 0.3:
                    p_str = f"{p:.1f}".replace(".", ",")
                    precip_lines.append(f"• {name}: {p_str} мм 🌧️")
                else:
                    p_str = f"{p:.1f}".replace(".", ",") if p > 0 else "0"
                    precip_lines.append(f"• {name}: {p_str} мм")

        # Видимость по районам (показываем, если есть данные)
        vis_lines = []
        vis_values = [d.get("visibility") for d in districts if d.get("visibility") is not None]
        if vis_values:
            min_vis = min(vis_values)
            max_vis = max(vis_values)
            # Показываем, если есть заметный разброс (≥2x) или где-то < 5 км
            show_vis = (max_vis / min_vis >= 2.0) if min_vis > 0 else False
            if show_vis or min_vis < 5000:
                for d in districts:
                    v = d.get("visibility")
                    name = d.get("name", "?")
                    if v is None:
                        vis_lines.append(f"• {name}: —")
                    elif v >= 10000:
                        vis_lines.append(f"• {name}: 10+ км")
                    elif v >= 1000:
                        km = math_round(v / 1000, 0)
                        marker = " 🌫️" if v < 5000 else ""
                        vis_lines.append(f"• {name}: {km} км{marker}")
                    else:
                        vis_lines.append(f"• {name}: {int(v)} м 🌫️")

        # Собираем блок
        f2_parts = []
        if precip_lines:
            f2_parts.append("🌧️ <b>ОСАДКИ ПО РАЙОНАМ:</b>\n" + indent_multiline("\n".join(precip_lines)))
        if vis_lines:
            f2_parts.append("👁️ <b>ВИДИМОСТЬ ПО РАЙОНАМ:</b>\n" + indent_multiline("\n".join(vis_lines)))

        if f2_parts:
            districts_block = "【F2】" + "\n".join(f2_parts)
    # ─── КОНЕЦ BLOCK_F2 ─────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_G — Ближайший период ─────────────────────
    # ═══════════════════════════════════════════════════════════
    next_period = short.get("next_period", "нет данных")
    next_period_title = short.get("next_period_title", "—")
    next_period_range = short.get("next_period_range", "")
    period_rain_prob = short.get("rain_prob")

    forecast_block = ""
    if next_period != "нет данных":
        period_night_score = get_astro_night_score(
            now_dt.hour, now_dt.minute, sunrise, sunset
        )

        period_data = {
            "temp": avg_w.get("temp") or (m.get("temp") or 0),
            "feels_like": avg_w.get("feels_like") or (m.get("feels_like") or 0),
            "wind_speed": avg_w.get("wind_speed") or (m.get("wind_speed") or 0),
            "wind_gust": avg_w.get("wind_gust") or 0,
            "is_rain": avg_w.get("is_rain", False),
            "is_drizzle": avg_w.get("is_drizzle", False),
            "rain_prob_now": period_rain_prob,
            "rain_prob_day": period_rain_prob,
            "rain_total": short.get("rain_total") or 0,
            "precip_mm": short.get("precip_mm") or 0,
            "is_thunder": avg_w.get("is_thunder", False),
            "is_hail": avg_w.get("is_hail", False),
            "visibility": avg_w.get("visibility") or 10000,
            "visibility_min": avg_w.get("visibility_min"),
            "visibility_max": avg_w.get("visibility_max"),
            "visibility_big_spread": avg_w.get("visibility_big_spread", False),
            "dew_point": avg_w.get("dew_point"),
            "humidity": avg_w.get("humidity"),
            "clouds_pct": avg_w.get("clouds_pct"),
            "soil_temp": avg_w.get("soil_temp"),
            "night_score": period_night_score,
            "twilight": twilight,
        }
        period_risk = analyze_risks(period_data, is_forecast=True)
        period_verdict = get_rider_verdict(period_risk["score"], now_dt.month)

        period_risks = period_risk["risks"][:4]

        rain_line = ""
        if period_rain_prob and period_rain_prob >= 30:
            if period_rain_prob >= 95:
                rain_line = f"🌧️ Дождь идёт: {period_rain_prob}{NBSP}%"
            elif period_rain_prob >= 80:
                rain_line = f"☔️ Дождь почти наверняка: {period_rain_prob}{NBSP}%"
            elif period_rain_prob >= 50:
                rain_line = f"🌧️ Вероятен дождь: {period_rain_prob}{NBSP}%"
            else:
                rain_line = f"🌦️ Возможен дождь: {period_rain_prob}{NBSP}%"

        if rain_line:
            period_risks = filter_rain_risks(period_risks)

        period_risks_text = "\n".join(period_risks) if period_risks else ""

        period_bar = build_risk_bar(period_risk["score"])
        title_line = f"{next_period_title} ({next_period_range})" if next_period_range else next_period_title

        # Фикс 1.8.2: если глобально идёт дождь, а OM говорит "ясно" — подменяем
        shown_period = next_period
        if avg_w.get("is_rain") and "· ясно" in shown_period:
            shown_period = shown_period.replace("· ясно", "· дождь")
        elif avg_w.get("is_drizzle") and "· ясно" in shown_period:
            shown_period = shown_period.replace("· ясно", "· морось")

        p_inner = [f"<b>{period_verdict}</b>", f"РИСК: {period_risk['score']}/10"]
        if period_bar:
            p_inner.append(period_bar)
        p_inner.append(shown_period)
        if rain_line:
            p_inner.append(rain_line)
        if period_risks_text:
            p_inner.append("<b>ЧТО НА ДОРОГЕ</b>")
            p_inner.append(period_risks_text)

        forecast_block = f"【G】{title_line}\n" + indent_multiline("\n".join(p_inner))
    # ─── КОНЕЦ BLOCK_G ──────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_H — Завтра ───────────────────────────────
    # ═══════════════════════════════════════════════════════════
    tomorrow_block = ""
    if f:
        f["night_score"] = 0
        f["rain_prob_now"] = f.get("rain_prob")
        f["rain_prob_day"] = f.get("rain_prob")

        fa = analyze_risks(f, is_forecast=True)
        fa_verdict = get_rider_verdict(fa["score"], now_dt.month, is_tomorrow=True)
        cond_low = shorten_cond(f.get("condition_text", ""))
        emoji_short = f.get("condition_emoji", "")

        tomorrow_risks = fa["risks"][:4]

        tomorrow_line = (
            f"{f['temp_min']}–{f['temp_max']}{NBSP}°C · "
            f"{f['wind_speed']}{NBSP}м/с"
        )
        if f.get("wind_gust"):
            tomorrow_line += f" (до {f['wind_gust']}{NBSP}м/с)"
        if f.get("rain_prob") and f["rain_prob"] > 30:
            tomorrow_line += f" · дождь {f['rain_prob']}{NBSP}%"
        else:
            tomorrow_line += f" · {cond_low} {emoji_short}".rstrip()
            # Фикс 1.8.3: явно помечаем "без осадков", если их нет
            rain_sum_t = f.get("rain_sum") or 0
            if rain_sum_t < 0.3:
                tomorrow_line += " · без осадков"

        rain_line_tomorrow = ""
        if f.get("rain_prob") and f["rain_prob"] >= 30:
            rp = f["rain_prob"]
            rain_sum = f.get("rain_sum") or 0
            if rp >= 95:
                rain_line_tomorrow = f"🌧️ Дождь идёт: {rp}{NBSP}%"
            elif rp >= 80:
                rain_line_tomorrow = f"☔️ Дождь почти наверняка: {rp}{NBSP}%"
            elif rp >= 50:
                rain_line_tomorrow = f"🌧️ Вероятен дождь: {rp}{NBSP}%"
            else:
                rain_line_tomorrow = f"🌦️ Возможен дождь: {rp}{NBSP}%"
            if rain_sum > 0:
                rain_line_tomorrow += f" · {rain_sum}{NBSP}мм"

        if rain_line_tomorrow:
            tomorrow_risks = filter_rain_risks(tomorrow_risks)

        tomorrow_risks_text = "\n".join(tomorrow_risks) if tomorrow_risks else ""

        tomorrow_bar = build_risk_bar(fa["score"])
        title_t = f"ЗАВТРА ({f.get('day_range', '')})" if f.get("day_range") else "ЗАВТРА"

        t_inner = [f"<b>{fa_verdict}</b>", f"РИСК: {fa['score']}/10"]
        if tomorrow_bar:
            t_inner.append(tomorrow_bar)
        t_inner.append(tomorrow_line)
        if rain_line_tomorrow:
            t_inner.append(rain_line_tomorrow)
        if tomorrow_risks_text:
            t_inner.append("<b>ЧТО НА ДОРОГЕ</b>")
            t_inner.append(tomorrow_risks_text)

        tomorrow_block = f"【H】📅 {title_t}\n" + indent_multiline("\n".join(t_inner))
    # ─── КОНЕЦ BLOCK_H ──────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_I — Источники ────────────────────────────
    # ═══════════════════════════════════════════════════════════
    def src_marker(code):
        return code if code in sources_live else f"{code}*"

    legend_lines = [f"{src_marker('M')}{NBSP} — METAR (аэропорт Минск)"]
    legend_lines.append(f"{src_marker('OM')} — Open-Meteo (5 точек Минска)")
    legend_lines.append(f"{src_marker('W')}{NBSP} — wttr (Минск)")
    legend_lines.append(f"{src_marker('OW')} — OpenWeatherMap (Минск)")

    agreement = a_city.get("agreement") if isinstance(a_city, dict) else None
    agree_values = a_city.get("agree_values") if isinstance(a_city, dict) else None

    i_inner = ["📡 Источники:"] + legend_lines + [f"Формула: {formula}"]
    if agreement:
        i_inner.append(f"Согласие источников: <b>{agreement.upper()}</b>")
    if agree_values:
        vs = fmt_spread(agree_values)
        if vs:
            i_inner.append(vs)

    block_i = "【I】" + indent_multiline("\n".join(i_inner))
    # ─── КОНЕЦ BLOCK_I ──────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_J — Совет ────────────────────────────────
    # ═══════════════════════════════════════════════════════════
    tip = get_tip(
        a_city.get("feels_like", m.get("feels_like") or 0),
        avg_w.get("humidity") or m.get("humidity"),
        avg_w.get("is_rain", False) or m.get("is_rain", False),
        w.get("is_night", False),
        avg_w.get("wind_speed") or m.get("wind_speed") or 0,
        m.get("is_thunder", False),
        avg_w.get("visibility") or m.get("visibility"),
        wind_gust=(avg_w.get("wind_gust") or 0),
        uv_index=(uv if uv is not None else 0),
        is_drizzle=(avg_w.get("is_drizzle", False) or m.get("is_drizzle", False)),
    )

    j_lines = [tip, "🏍️ <b>Ровной дороги!</b>", f"<i>v{BOT_VERSION}</i>"]
    if is_morning:
        j_lines.append(get_alcohol_warning())
        j_lines.append(f"💬 <i>{get_random_quote()}</i>")
    block_j = "【J】" + indent_multiline("\n".join(j_lines))
    # ─── КОНЕЦ BLOCK_J ──────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════
    # ─── НАЧАЛО BLOCK_BUILD — Финальная сборка ─────────────────
    # ═══════════════════════════════════════════════════════════
    msg = f"""{block_a}

—————
{block_b}

{block_c}

{block_d}

{block_e}

—————
{block_f}"""

    if districts_block:
        msg += f"""

{districts_block}"""

    if forecast_block:
        msg += f"""

—————
{forecast_block}"""

    if tomorrow_block:
        msg += f"""

—————
{tomorrow_block}"""

    msg += f"""

—————
{block_i}

—————
{block_j}"""

    return msg
    # ─── КОНЕЦ BLOCK_BUILD ──────────────────────────────────────
# ─── КОНЕЦ BUILD_WEATHER_MESSAGE ───────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО MORNING_BROADCAST ──────────────────────────────
# ═══════════════════════════════════════════════════════════
def run_morning_broadcast(force=False):
    now = datetime.now(MINSK_TZ)
    today_str = now.strftime("%Y-%m-%d")

    if not force and get_last_morning_date() == today_str:
        return {"skipped": "already_sent_today"}

    set_last_morning_date(today_str)

    subs = load_subscribers()
    if not subs:
        return {"skipped": "no_subscribers", "date": today_str}

    try:
        w = get_weather()
        if not w or not w.get("m"):
            return {"error": "weather_unavailable", "date": today_str}

        avg_w = merge_weather_data(w)
        if not avg_w:
            return {"error": "merge_failed", "date": today_str}

        a_city = analyze_risks(avg_w)
        a_city["agreement"] = avg_w.get("agreement")
        a_city["agree_values"] = avg_w.get("agree_values")
        a_city["avg_w"] = avg_w

        short = get_short_forecast()
        f = get_forecast_tomorrow()

        msg = build_weather_message(w, a_city, short, f, is_morning=True)

        sent, failed_403 = 0, []
        for uid in subs:
            try:
                sent_msg = bot.send_message(
                    uid, msg, parse_mode="HTML",
                    reply_markup=get_morning_keyboard()
                )
                set_last_bot_msg(uid, sent_msg.message_id)
                sent += 1
                time.sleep(0.05)
            except ApiTelegramException as e:
                if e.error_code == 403:
                    failed_403.append(uid)
            except Exception:
                pass

        for uid in failed_403:
            remove_subscriber(uid)

        print(f"✅ Рассылка {today_str}: {sent} ок, {len(failed_403)} удалено", flush=True)
        return {"sent": sent, "deleted": len(failed_403), "date": today_str}

    except Exception as e:
        print(f"❌ run_morning_broadcast: {type(e).__name__}: {e}", flush=True)
        return {"error": str(e), "date": today_str}


def morning_broadcast_loop():
    print("⏰ Поток утренней рассылки запущен", flush=True)
    while True:
        try:
            now = datetime.now(MINSK_TZ)
            today_str = now.strftime("%Y-%m-%d")

            if now.hour == 7 and now.minute < 10:
                if get_last_morning_date() != today_str:
                    print(f"🌅 Утренняя рассылка ({today_str})", flush=True)
                    run_morning_broadcast()
        except Exception as e:
            print(f"❌ Ошибка рассылки: {e}", flush=True)

        time.sleep(60)
# ─── КОНЕЦ MORNING_BROADCAST ───────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО NOTIFY_VERSION ─────────────────────────────────
# ═══════════════════════════════════════════════════════════
def notify_version_update(force=False):
    if not UPSTASH_ENABLED and not force:
        return {"skipped": "no_redis"}

    if not BOT_VERSION_NOTIFY and not force:
        return {"skipped": "notify_disabled"}

    last_notified = _redis("get", "last_notified_version") if UPSTASH_ENABLED else None
    if last_notified == BOT_VERSION and not force:
        return {"skipped": "already_notified", "version": BOT_VERSION}

    desc = ""
    for item in BOT_CHANGELOG:
        if item[0] == BOT_VERSION:
            desc = item[2]
            break

    updaters = load_updaters()
    if not updaters:
        if UPSTASH_ENABLED:
            _redis("set", "last_notified_version", BOT_VERSION)
        return {"skipped": "no_updaters", "version": BOT_VERSION}

    text = (
        f"🎉 <b>MotoWeather обновился до v{BOT_VERSION}</b>\n\n"
        f"<b>Что нового:</b>\n{desc}\n\n"
        f"<i>Отключить уведомления — /about → «🔕 Не уведомлять»</i>\n"
        f"<i>Посмотреть прогноз — /start</i>"
    )

    sent, failed_403 = 0, []
    for uid in updaters:
        try:
            bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
            time.sleep(0.05)
        except ApiTelegramException as e:
            if e.error_code == 403:
                failed_403.append(uid)
        except Exception:
            pass

    for uid in failed_403:
        remove_updater(uid)

    if UPSTASH_ENABLED:
        _redis("set", "last_notified_version", BOT_VERSION)

    print(f"📢 Уведомление v{BOT_VERSION}: {sent} ок, {len(failed_403)} удалено", flush=True)
    return {"sent": sent, "deleted": len(failed_403), "version": BOT_VERSION}
# ─── КОНЕЦ NOTIFY_VERSION ──────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО SEND_WEATHER ───────────────────────────────────
# ═══════════════════════════════════════════════════════════
def send_weather(chat_id):
    now = time.time()
    last = _user_last_weather.get(chat_id, 0)

    if now - last < ANTISPAM_SEC:
        remaining = ANTISPAM_SEC - (now - last)
        print(f"⏸️ {chat_id}: защита от дабл-клика ({remaining:.1f} сек)", flush=True)
        return ("antispam", int(remaining) + 1)

    _user_last_weather[chat_id] = now

    try:
        try:
            bot.send_chat_action(chat_id, 'typing')
        except Exception:
            pass

        w = get_weather()
        if not w or not w.get("m"):
            send_or_edit(chat_id, "❌ Небо молчит.", None)
            return "error"

        avg_w = merge_weather_data(w)
        if not avg_w:
            send_or_edit(chat_id, "❌ Небо молчит.", None)
            return "error"

        a_city = analyze_risks(avg_w)
        a_city["agreement"] = avg_w.get("agreement")
        a_city["agree_values"] = avg_w.get("agree_values")
        a_city["avg_w"] = avg_w

        short = get_short_forecast()
        f = get_forecast_tomorrow()

        msg = build_weather_message(w, a_city, short, f, is_morning=False)
        send_or_edit(chat_id, msg, get_after_weather_keyboard(is_subscribed(chat_id)))

        _feedback_state[chat_id] = {
            "weather_snapshot": fb.build_weather_snapshot(w, a_city),
        }
        return "ok"
    except Exception as e:
        print(f"❌ send_weather: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return "error"
# ─── КОНЕЦ SEND_WEATHER ────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО COMMANDS ───────────────────────────────────────
# ═══════════════════════════════════════════════════════════
@bot.message_handler(commands=['start'])
def start(message):
    try:
        save_user(message.chat.id)
        info = bot.get_me()

        if info.username != MY_BOT_USERNAME:
            send_or_edit(
                message.chat.id,
                f"⚠️ <b>Это поддельный бот!</b>\nНастоящий: @{MY_BOT_USERNAME}",
                None
            )
            return

        send_or_edit(message.chat.id, START_TEXT, get_main_keyboard())
    except Exception as e:
        print(f"❌ /start: {e}", flush=True)


@bot.message_handler(commands=['weather'])
def weather_cmd(m):
    try:
        save_user(m.chat.id)
        send_weather(m.chat.id)
    except Exception as e:
        print(f"❌ /weather: {e}", flush=True)


@bot.message_handler(commands=['about'])
def about_cmd(m):
    try:
        save_user(m.chat.id)
        kb = get_about_keyboard(
            is_subscribed=is_subscribed(m.chat.id),
            is_updater=is_updater(m.chat.id),
        )
        send_or_edit(m.chat.id, START_TEXT, kb)
    except Exception as e:
        print(f"❌ /about: {e}", flush=True)


@bot.message_handler(commands=['subscribe'])
def subscribe_cmd(m):
    try:
        save_user(m.chat.id)
        if is_subscribed(m.chat.id):
            kb = get_about_keyboard(is_subscribed=True, is_updater=is_updater(m.chat.id))
            send_or_edit(m.chat.id, ALREADY_SUBSCRIBED, kb)
            return
        send_or_edit(m.chat.id, SUBSCRIBE_TEXT, get_subscribe_keyboard())
    except Exception as e:
        print(f"❌ /subscribe: {e}", flush=True)


@bot.message_handler(commands=['unsubscribe'])
def unsubscribe_cmd(m):
    try:
        save_user(m.chat.id)
        if not is_subscribed(m.chat.id):
            kb = get_about_keyboard(is_subscribed=False, is_updater=is_updater(m.chat.id))
            send_or_edit(m.chat.id, "ℹ️ Ты не подписан.", kb)
            return
        send_or_edit(m.chat.id, UNSUBSCRIBE_PROMPT, get_unsubscribe_keyboard())
    except Exception as e:
        print(f"❌ /unsubscribe: {e}", flush=True)


@bot.message_handler(commands=['updates'])
def updates_cmd(m):
    try:
        save_user(m.chat.id)
        if is_updater(m.chat.id):
            remove_updater(m.chat.id)
            text = UPDATES_OFF_TEXT
        else:
            save_updater(m.chat.id)
            text = UPDATES_ON_TEXT

        kb = get_about_keyboard(
            is_subscribed=is_subscribed(m.chat.id),
            is_updater=is_updater(m.chat.id),
        )
        send_or_edit(m.chat.id, text, kb)
    except Exception as e:
        print(f"❌ /updates: {e}", flush=True)


@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    if not ADMIN_ID or m.chat.id != ADMIN_ID:
        bot.reply_to(m, "❌ Нет прав.")
        return

    changelog_lines = []
    for item in BOT_CHANGELOG[:6]:
        ver, date, desc = item[0], item[1], item[2]
        marker = "▶️" if ver == BOT_VERSION else "  "
        changelog_lines.append(f"{marker} <b>v{ver}</b> ({date}) — {desc}")
    changelog_text = "\n".join(changelog_lines)

    bot.reply_to(
        m,
        f"📊 <b>Статистика MotoWeather</b>\n"
        f"🏍️ Версия: <b>v{BOT_VERSION}</b> ({BOT_VERSION_DATE})\n\n"
        f"👥 Юзеров: {get_users_count()}\n"
        f"🌅 Подписчиков на утро: {get_subscribers_count()}\n"
        f"🔔 Подписчиков на обновления: {get_updaters_count()}\n"
        f"💾 Хранилище: {'Upstash' if UPSTASH_ENABLED else 'файлы'}\n"
        f"📍 Многоточечный OM: {'вкл' if MINSK_POINTS_ENABLED else 'выкл'}\n"
        f"📅 {datetime.now(MINSK_TZ).strftime('%d.%m.%Y %H:%M')}\n\n"
        f"<b>История версий:</b>\n{changelog_text}",
        parse_mode="HTML"
    )


@bot.message_handler(commands=['feedback'])
def feedback_cmd(m):
    if not ADMIN_ID or m.chat.id != ADMIN_ID:
        bot.reply_to(m, "❌ Нет прав.")
        return
    report = fb.format_feedback_report(days=7, limit=5)
    bot.reply_to(m, report, parse_mode="HTML")


@bot.message_handler(commands=['feedback_detail'])
def feedback_detail_cmd(m):
    if not ADMIN_ID or m.chat.id != ADMIN_ID:
        bot.reply_to(m, "❌ Нет прав.")
        return
    try:
        parts = m.text.split()
        if len(parts) < 2:
            bot.reply_to(m, "Использование: /feedback_detail <user_id>")
            return
        uid = int(parts[1])
        detail = fb.format_feedback_detail(uid)
        bot.reply_to(m, detail, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(m, f"⚠️ Ошибка: {e}")
# ─── КОНЕЦ COMMANDS ────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО CALLBACK ───────────────────────────────────────
# ═══════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    try:
        print(f"📩 {call.data} от {call.message.chat.id}", flush=True)
        try:
            save_user(call.message.chat.id)
        except Exception:
            pass

        chat_id = call.message.chat.id

        if call.data == "weather":
            try:
                bot.answer_callback_query(call.id, "⏳ Смотрю...", cache_time=1)
            except Exception as e:
                print(f"⚠️ answer_callback: {e}", flush=True)

            result = send_weather(chat_id)

            if isinstance(result, tuple) and result[0] == "antispam":
                try:
                    bot.answer_callback_query(
                        call.id,
                        f"⏳ Подожди {result[1]} сек",
                        show_alert=False,
                        cache_time=1
                    )
                except Exception:
                    pass

        elif call.data == "about":
            bot.answer_callback_query(call.id, "✅", cache_time=3)
            kb = get_about_keyboard(
                is_subscribed=is_subscribed(chat_id),
                is_updater=is_updater(chat_id),
            )
            send_or_edit(chat_id, START_TEXT, kb)

        elif call.data == "subscribe":
            if is_subscribed(chat_id):
                bot.answer_callback_query(call.id, "ℹ️ Уже подписан", cache_time=3)
                kb = get_about_keyboard(is_subscribed=True, is_updater=is_updater(chat_id))
                send_or_edit(chat_id, ALREADY_SUBSCRIBED, kb)
            else:
                bot.answer_callback_query(call.id, "✅", cache_time=3)
                send_or_edit(chat_id, SUBSCRIBE_TEXT, get_subscribe_keyboard())

        elif call.data == "subscribe_confirm":
            save_subscriber(chat_id)
            bot.answer_callback_query(call.id, "✅ Подписка", cache_time=3)
            kb = get_about_keyboard(is_subscribed=True, is_updater=is_updater(chat_id))
            send_or_edit(chat_id, SUBSCRIBE_CONFIRMED, kb)

        elif call.data == "subscribe_cancel":
            bot.answer_callback_query(call.id, "❌", cache_time=3)
            kb = get_about_keyboard(is_subscribed=is_subscribed(chat_id), is_updater=is_updater(chat_id))
            send_or_edit(chat_id, SUBSCRIBE_CANCELED, kb)

        elif call.data == "unsubscribe":
            if not is_subscribed(chat_id):
                bot.answer_callback_query(call.id, "ℹ️ Не подписан", cache_time=3)
                kb = get_about_keyboard(is_subscribed=False, is_updater=is_updater(chat_id))
                send_or_edit(chat_id, "ℹ️ Ты не подписан.", kb)
            else:
                bot.answer_callback_query(call.id, "❌", cache_time=3)
                send_or_edit(chat_id, UNSUBSCRIBE_PROMPT, get_unsubscribe_keyboard())

        elif call.data == "unsubscribe_confirm":
            remove_subscriber(chat_id)
            bot.answer_callback_query(call.id, "❌ Отписан", cache_time=3)
            kb = get_about_keyboard(is_subscribed=False, is_updater=is_updater(chat_id))
            send_or_edit(chat_id, UNSUBSCRIBED, kb)

        elif call.data == "unsubscribe_cancel":
            bot.answer_callback_query(call.id, "✅ Остаёмся", cache_time=3)
            kb = get_about_keyboard(is_subscribed=True, is_updater=is_updater(chat_id))
            send_or_edit(chat_id, UNSUBSCRIBE_CANCELED, kb)

        elif call.data == "updates_on":
            save_updater(chat_id)
            bot.answer_callback_query(call.id, "🔔 Включено", cache_time=3)
            kb = get_about_keyboard(is_subscribed=is_subscribed(chat_id), is_updater=True)
            send_or_edit(chat_id, UPDATES_ON_TEXT, kb)

        elif call.data == "updates_off":
            remove_updater(chat_id)
            bot.answer_callback_query(call.id, "🔕 Отключено", cache_time=3)
            kb = get_about_keyboard(is_subscribed=is_subscribed(chat_id), is_updater=False)
            send_or_edit(chat_id, UPDATES_OFF_TEXT, kb)

        # ═══════════════════════════════════════════════════════════
        # ─── НАЧАЛО CALLBACK_FEEDBACK ──────────────────────────────
        # ═══════════════════════════════════════════════════════════
        elif call.data == "feedback_start":
            can, remaining = fb.check_antispam(chat_id)
            if not can:
                bot.answer_callback_query(
                    call.id,
                    f"⏳ Подожди {remaining // 60} мин",
                    show_alert=True,
                    cache_time=1
                )
                return
            bot.answer_callback_query(call.id, "Выбери блок", cache_time=3)
            send_or_edit(
                chat_id,
                "❓ <b>Что неверно в прогнозе?</b>\n\n"
                "Сначала выбери <b>БЛОК</b> сообщения (【A】–【K】):",
                get_feedback_blocks_keyboard()
            )

        elif call.data.startswith("feedback_block:"):
            block = call.data.split(":", 1)[1]
            meta = fb.FEEDBACK_BLOCKS.get(block, {"emoji": "【?】", "label": "?"})

            state = _feedback_state.get(chat_id, {})
            state["block"] = block
            _feedback_state[chat_id] = state

            bot.answer_callback_query(call.id, f"{meta['emoji']} {meta['label']}", cache_time=3)
            send_or_edit(
                chat_id,
                f"【{block}】 <b>{meta['label']}</b>\n\n"
                f"Что именно не так?",
                get_feedback_params_keyboard(block)
            )

        elif call.data.startswith("feedback_param:"):
            parts = call.data.split(":", 2)
            block = parts[1] if len(parts) > 1 else ""
            param = parts[2] if len(parts) > 2 else "other"

            meta = fb.FEEDBACK_PARAMS.get(param, {"emoji": "❓", "label": param})

            state = _feedback_state.get(chat_id, {})
            state["block"] = block
            state["param"] = param
            _feedback_state[chat_id] = state

            bot.answer_callback_query(call.id, f"{meta['emoji']} {meta['label']}", cache_time=3)
            send_or_edit(
                chat_id,
                f"【{block}】 {meta['emoji']} <b>{meta['label']}</b>\n\n"
                f"Как на самом деле?",
                get_feedback_direction_keyboard(block, param)
            )

        elif call.data.startswith("feedback_dir:"):
            parts = call.data.split(":", 3)
            block = parts[1] if len(parts) > 1 else ""
            param = parts[2] if len(parts) > 2 else "other"
            direction = parts[3] if len(parts) > 3 else "wrong"

            state = _feedback_state.get(chat_id, {})
            state["block"] = block
            state["param"] = param
            state["direction"] = direction
            _feedback_state[chat_id] = state

            meta = fb.FEEDBACK_PARAMS.get(param, {"emoji": "❓", "label": param})
            dir_meta = fb.FEEDBACK_DIRECTIONS.get(direction, {"emoji": "?", "label": "?"})

            bot.answer_callback_query(call.id, f"{dir_meta['emoji']} {dir_meta['label']}", cache_time=3)
            send_or_edit(
                chat_id,
                f"✅ Записал:\n"
                f"【{block}】 {meta['emoji']} {meta['label']} — {dir_meta['emoji']} {dir_meta['label']}\n\n"
                f"Добавить комментарий?",
                get_feedback_skip_keyboard(block, param, direction)
            )

        elif call.data.startswith("feedback_send:"):
            parts = call.data.split(":", 3)
            block = parts[1] if len(parts) > 1 else ""
            param = parts[2] if len(parts) > 2 else "other"
            direction = parts[3] if len(parts) > 3 else "wrong"

            state = _feedback_state.get(chat_id, {})
            snapshot = state.get("weather_snapshot", {})

            ok = fb.save_feedback(
                user_id=chat_id,
                param=param,
                direction=direction,
                user_comment="",
                weather_snapshot=snapshot,
                shown_value="",
                block=block,
            )

            bot.answer_callback_query(call.id, "✅ Спасибо!", cache_time=3)
            _feedback_state.pop(chat_id, None)

            if ok:
                send_or_edit(
                    chat_id,
                    "✅ <b>Спасибо за жалобу!</b>\n\n"
                    "Мы сохранили данные и учтём это для улучшения. 🙏",
                    get_after_weather_keyboard(is_subscribed(chat_id))
                )
            else:
                send_or_edit(
                    chat_id,
                    "⚠️ Не удалось сохранить. Попробуй позже.",
                    get_after_weather_keyboard(is_subscribed(chat_id))
                )

        elif call.data.startswith("feedback_comment:"):
            parts = call.data.split(":", 3)
            block = parts[1] if len(parts) > 1 else ""
            param = parts[2] if len(parts) > 2 else "other"
            direction = parts[3] if len(parts) > 3 else "wrong"

            state = _feedback_state.get(chat_id, {})
            state["block"] = block
            state["param"] = param
            state["direction"] = direction
            state["awaiting_comment"] = True
            _feedback_state[chat_id] = state

            bot.answer_callback_query(call.id, "💬 Напиши комментарий", cache_time=3)

            msg = bot.send_message(
                chat_id,
                "💬 Напиши комментарий одним сообщением:",
                reply_markup=get_feedback_cancel_keyboard()
            )
            bot.register_next_step_handler(msg, handle_feedback_comment)

        elif call.data == "feedback_cancel":
            _feedback_state.pop(chat_id, None)
            bot.answer_callback_query(call.id, "❌ Отменено", cache_time=3)
            send_or_edit(
                chat_id,
                "❌ Отменено. Если что-то ещё — жми «🔄 ОБНОВИТЬ ПРОГНОЗ».",
                get_after_weather_keyboard(is_subscribed(chat_id))
            )
        # ─── КОНЕЦ CALLBACK_FEEDBACK ───────────────────────────────

        else:
            bot.answer_callback_query(call.id, "❓", cache_time=3)

    except Exception as e:
        print(f"❌ callback: {type(e).__name__}: {e}", flush=True)


def handle_feedback_comment(message):
    chat_id = message.chat.id
    state = _feedback_state.get(chat_id, {})

    if not state.get("awaiting_comment"):
        return

    block = state.get("block", "") or "K"
    param = state.get("param", "other")
    direction = state.get("direction", "wrong")
    comment = (message.text or "")[:200]
    snapshot = state.get("weather_snapshot", {})

    ok = fb.save_feedback(
        user_id=chat_id,
        param=param,
        direction=direction,
        user_comment=comment,
        weather_snapshot=snapshot,
        shown_value="",
        block=block,
    )

    _feedback_state.pop(chat_id, None)

    if ok:
        send_or_edit(
            chat_id,
            f"✅ <b>Спасибо!</b>\n\n"
            f"【{block}】 Записал: {comment}\n\n"
            f"Учтём для улучшения прогноза. 🙏",
            get_after_weather_keyboard(is_subscribed(chat_id))
        )
    else:
        send_or_edit(
            chat_id,
            "⚠️ Не удалось сохранить. Попробуй позже.",
            get_after_weather_keyboard(is_subscribed(chat_id))
        )
# ─── КОНЕЦ CALLBACK ────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО FLASK_ROUTES ───────────────────────────────────
# ═══════════════════════════════════════════════════════════
@app.route("/")
def home():
    return "🏍️ MotoWeather Bot is running!", 200


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/apple-touch-icon-precomposed.png")
def apple_icon():
    return "", 204


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "bot": "MotoWeather Minsk",
        "version": BOT_VERSION,
        "version_date": BOT_VERSION_DATE,
        "storage": "upstash" if UPSTASH_ENABLED else "files",
        "users": get_users_count(),
        "subscribers": get_subscribers_count(),
        "updaters": get_updaters_count(),
        "time": datetime.now(MINSK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    }), 200


@app.route("/cron/morning")
def cron_morning():
    secret = os.getenv("CRON_SECRET", "")
    if not secret:
        return jsonify({"error": "CRON_SECRET not configured"}), 500
    if request.args.get("secret") != secret:
        return jsonify({"error": "forbidden"}), 403

    result = run_morning_broadcast(force=True)
    return jsonify(result), 200


@app.route("/cron/version")
def cron_version():
    secret = os.getenv("CRON_SECRET", "")
    if not secret:
        return jsonify({"error": "CRON_SECRET not configured"}), 500
    if request.args.get("secret") != secret:
        return jsonify({"error": "forbidden"}), 403

    result = notify_version_update(force=True)
    return jsonify(result), 200


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
# ─── КОНЕЦ FLASK_ROUTES ────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО MAIN ───────────────────────────────────────────
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🏍️ MotoWeather Бот запущен!", flush=True)

    try:
        bot.remove_webhook()
        print("✅ Webhook сброшен", flush=True)
    except Exception as e:
        print(f"⚠️ remove_webhook: {e}", flush=True)

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=morning_broadcast_loop, daemon=True).start()

    try:
        notify_version_update()
    except Exception as e:
        print(f"⚠️ notify_version_update: {e}", flush=True)

    print("🔄 Polling...", flush=True)
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            err_str = str(e)
            if "409" in err_str:
                print("⚠️ 409. Жду 20 сек...", flush=True)
                time.sleep(20)
            else:
                print(f"⚠️ Polling упал: {e}", flush=True)
                time.sleep(10)
# ─── КОНЕЦ MAIN ────────────────────────────────────────────
