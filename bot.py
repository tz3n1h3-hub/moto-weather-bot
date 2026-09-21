import json
import os
import random
import re
import threading
import time
from datetime import datetime
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
)
from weather import (
    get_weather, get_forecast_tomorrow,
    get_short_forecast, get_daylight_info, hpa_to_mmhg,
    merge_weather_data, get_twilight_state,
)
from analyzer import (
    analyze_risks, get_short_verdict, get_rider_verdict,
    get_gear_short, get_tech_check, get_tip,
)
from keyboards import (
    get_main_keyboard, get_after_weather_keyboard, get_morning_keyboard,
    get_about_keyboard, get_subscribe_keyboard, get_unsubscribe_keyboard
)


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

UPSTASH_ENABLED = bool(UPSTASH_URL and UPSTASH_TOKEN)

# Анти-спам: 3 секунды — только защита от случайного двойного тапа
_user_last_weather = {}
ANTISPAM_SEC = 3


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


# ============ ПОДПИСЧИКИ НА УТРО ============
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


# ============ ПОДПИСЧИКИ НА ОБНОВЛЕНИЯ ============
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


# ============ УТРЕННИЙ СТАТУС ============
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


def _time_to_min(hhmm):
    try:
        h, m = map(int, hhmm.split(":"))
        return h * 60 + m
    except Exception:
        return None


def night_score_for_period(title, sunrise, sunset):
    if title == "🌙 НОЧЬЮ":
        return 2

    period_ranges = {
        "🌅 УТРОМ":   (6 * 60,  12 * 60),
        "☀️ ДНЁМ":     (12 * 60, 18 * 60),
        "🌆 ВЕЧЕРОМ": (18 * 60, 22 * 60),
    }

    rng = period_ranges.get(title)
    if not rng:
        return 0

    start, end = rng
    period_len = end - start
    if period_len <= 0:
        return 0

    sr_min = _time_to_min(sunrise) if sunrise else None
    ss_min = _time_to_min(sunset) if sunset else None

    if sr_min is None or ss_min is None:
        return 0

    dark_intervals = [(0, sr_min), (ss_min, 1440)]

    dark_minutes = 0
    for d_start, d_end in dark_intervals:
        lo = max(start, d_start)
        hi = min(end, d_end)
        if hi > lo:
            dark_minutes += (hi - lo)

    ratio = dark_minutes / period_len

    if ratio >= 0.75:
        return 2
    elif ratio >= 0.25:
        return 1
    else:
        return 0


# ============ ТЕКСТЫ ============
START_TEXT = f"""🌤 <b>MOTOWEATHER · МИНСК</b>

<b>Что это?</b>
Погодный ориентир для райдеров Минска.
Не точный прогноз, а честная сводка:
ехать сегодня или нет.

<b>Откуда беру данные:</b>
• METAR аэропорта Минск (UMMS) — фактическая погода «здесь и сейчас». Аэропорт стоит на открытой равнине в 20 км от центра — там ветренее и холоднее, чем в городе. Поэтому данные METAR учитываю как один из источников, а не как истину.

• Open-Meteo, OpenWeatherMap и wttr — три прогнозных сервиса. Каждый показывает погоду не для твоей улицы, а для квадрата на карте. Размер квадрата у всех разный — иногда меньше километра, иногда больше десяти. Внутри квадрата погода может отличаться, но это не учитывается.

<b>Как считаю:</b>
1. Собираю данные со всех четырёх источников.
2. Убираю выбросы: если один источник сильно отличается от остальных — не учитываю его.
3. Показываю среднее значение по живым источникам.
4. Если хоть один источник видит дождь — показываю факт осадков.

<b>Что на выходе:</b>
• Погода сейчас — средняя по источникам.
• Прогноз на ближайшие часы.
• Вердикт: ехать или нет — по 6 параметрам:
  – ветер (скорость и порывы);
  – осадки (дождь, снег, гроза, град);
  – видимость (туман, дымка, мгла);
  – температура (ощущаемая);
  – влажность и точка росы;
  – время суток.

<b>Про точность:</b>
Всё зависит от согласия источников. Если три-четыре сервиса дают близкие значения — доверия больше. Если расходятся — показываю среднее и предупреждаю.

<b>Подписки:</b>
• 🌅 Утро — прогноз в 7:00 каждый день (кнопка ниже).
• 🔔 Обновления — уведомления о новых версиях бота.

Нажми ПРОГНОЗ — и вперёд.

—
👨‍💻 Разработчик: <a href="https://t.me/Aleksandr_K8V">@Aleksandr_K8V</a>
🏍️ v{BOT_VERSION}"""


SUBSCRIBE_TEXT = """🌅 <b>Подписка на утро</b>

Каждый день в <b>7:00</b>:
• погода в Минске;
• вердикт — ехать или нет;
• экипировка;
• прогноз на ближайшее время;
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

Теперь ты будешь получать сообщения о новых версиях MotoWeather — что добавили, что поправили.

Отключить можно в «О проекте»."""

UPDATES_OFF_TEXT = """🔕 <b>Уведомления отключены</b>

Больше не будем присылать обновления. Включить обратно — в «О проекте»."""


# ============ ЕДИНАЯ ТОЧКА ОТПРАВКИ ============
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


# ============ РАЗБРОС (≥2 параметра) ============
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


# ============ ФИЛЬТР РИСКОВ ОТ ОСАДКОВ ============
def filter_rain_risks(risks):
    if not risks:
        return []
    keywords = ("дождь", "осадк", "морось", "ливн")
    return [
        r for r in risks
        if not any(kw in r.lower() for kw in keywords)
    ]


# ============ СБОРКА БЛОКА ПЕРИОДА ============
def build_period_block(title, verdict, score, line1, rain_line, risks_text):
    bar = build_risk_bar(score)
    parts = [f"<b>{title}</b>"]
    parts.append(f"<b>{verdict}</b>")
    parts.append(f"РИСК: {score}/10")
    if bar:
        parts.append(bar)
    if line1:
        parts.append(line1)

    risk_lines = []
    if rain_line:
        risk_lines.append(rain_line.lstrip("\n"))
    if risks_text:
        risk_lines.append(risks_text)

    if risk_lines:
        parts.append("<b>ЧТО НА ДОРОГЕ</b>")
        parts.extend(risk_lines)

    return "\n".join(parts)


# ============ СБОРКА СООБЩЕНИЯ ============
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

    header_line1 = f"{header_icon} <b>MOTOWEATHER · МИНСК</b>"
    header_line2 = f"{weekday} · {date_str} · {time_str}"

    score = a_city["score"]
    verdict = get_rider_verdict(score, now_dt.month)
    bar = build_risk_bar(score)

    verdict_block = f"СЕЙЧАС <b>{verdict}!</b>\nРИСК: {score}/10"
    if bar:
        verdict_block += f"\n{bar}"

    risk_factors = a_city["risks"][:4]
    risk_text = "\n".join(risk_factors) if risk_factors else "✅ Дорога чистая"

    recs = a_city.get("recommendations", [])
    rec_text = ""
    if score >= 3 and recs:
        rec_text = "\n\n<i>" + "\n".join(recs[:3]) + "</i>"

    gear = get_gear_short(
        a_city.get("feels_like", m.get("feels_like") or 0),
        avg_w.get("is_rain", False) or m.get("is_rain", False) or ww.get("is_rain", False),
        w.get("is_night", False),
        (m.get("wind_speed") or om.get("wind_speed") or 0),
    )
    gear_block = "\n".join(gear)

    tech = get_tech_check(
        a_city.get("feels_like", m.get("feels_like") or 0),
        w.get("is_night", False),
        avg_w.get("is_rain", False) or m.get("is_rain", False) or ww.get("is_rain", False),
        m.get("humidity"), m.get("dew_point"),
    )
    tech_block = "\n".join(f"✅ {t}" for t in tech)

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

    vis_vals = [v for v in gather("visibility", src_map) if v is not None and v > 0]
    if vis_vals:
        avg_vis_m = sum(vis_vals) / len(vis_vals)
        if avg_vis_m >= 1000:
            km_int = math_round(avg_vis_m / 1000, 0)
            vis_str = f"{km_int}{NBSP}км"
        else:
            vis_str = f"{math_round(avg_vis_m, 0)}{NBSP}м"
        if min(vis_vals) < 500:
            vis_str = "⚠️" + vis_str
        weather_lines.append(f"👁️ Видимость: {vis_str}")
    else:
        weather_lines.append("👁️ Видимость: —")

    weather_lines.append(f"💧 Влажность: {fmt_avg(gather('humidity', src_map), '%')}")
    weather_lines.append(f"💦 Точка росы: {fmt_avg(gather('dew_point', src_map), '°C')}")

    cloud_text = shorten_cond(m.get("cloud_text")) if m.get("cloud_text") else None
    cloud_vals = [v for v in gather("clouds_pct", src_map) if v is not None]
    if cloud_vals:
        avg_cloud = math_round(sum(cloud_vals) / len(cloud_vals), 0)
        if avg_cloud >= 70:
            weather_lines.append(f"🌥️ Облачность: {avg_cloud}{NBSP}%")
        elif cloud_text:
            weather_lines.append(f"🌥️ Облачность: {cloud_text} ({avg_cloud}{NBSP}%)")
        else:
            weather_lines.append(f"🌥️ Облачность: {avg_cloud}{NBSP}%")
    elif cloud_text:
        weather_lines.append(f"🌥️ Облачность: {cloud_text}")
    else:
        weather_lines.append("🌥️ Облачность: —")

    precip_vals = [v for v in gather("precip_mm", src_map) if v is not None and v > 0]
    rain_prob_now = w.get("rain_prob_now")
    is_rain_anywhere = w.get("is_rain_anywhere", False)
    rain_sources = w.get("rain_sources", [])

    src_note = f" [{', '.join(rain_sources[:2])}]" if rain_sources else ""

    if is_rain_anywhere and not precip_vals:
        weather_lines.append(f"☔️ Осадки: идёт дождь{src_note}")
    elif precip_vals:
        avg_precip = sum(precip_vals) / len(precip_vals)
        if avg_precip < 0.1 and is_rain_anywhere:
            weather_lines.append(f"☔️ Осадки: слабый дождь{src_note}")
        else:
            precip_line = f"🌧️ Осадки: {math_round(avg_precip, 0)}{NBSP}мм"
            if rain_prob_now and rain_prob_now >= 30:
                precip_line += f" · вероятность {rain_prob_now}{NBSP}%"
            weather_lines.append(precip_line)
    elif rain_prob_now and rain_prob_now >= 40:
        weather_lines.append(f"🌦️ Осадки: 0{NBSP}мм · вероятность {rain_prob_now}{NBSP}%")
    elif m.get("is_rain"):
        weather_lines.append(f"🌧️ Осадки: {m.get('weather_text') or 'дождь'}")

    weather_lines.append(f"📊 Давление: {fmt_avg(gather('pressure_mmhg', src_map), 'мм рт. ст.')}")

    twilight = get_twilight_state(w.get("sunrise"), w.get("sunset"))
    weather_lines.append(f"🌇 На улице: {twilight}")

    sunrise = w.get("sunrise")
    sunset = w.get("sunset")
    if sunrise and sunset:
        weather_lines.append(f"🌅 Рассвет: {sunrise} · 🌇 Закат: {sunset}")

    uv = avg_uv([m.get("uv_index"), om.get("uv_index"),
                 ww.get("uv_index"), ow.get("uv_index")])
    if uv is not None:
        lvl = uv_level(uv)
        advice = uv_advice(uv)
        weather_lines.append(f"☀️ UV-индекс: {uv}{NBSP}({lvl}) — {advice}")

    weather_block = "\n".join(weather_lines)

    next_period = short.get("next_period", "нет данных")
    next_period_title = short.get("next_period_title", "—")
    period_rain_prob = short.get("rain_prob")

    forecast_block = ""
    if next_period != "нет данных":
        period_night_score = night_score_for_period(
            next_period_title,
            w.get("sunrise"),
            w.get("sunset"),
        )

        period_data = {
            "temp": avg_w.get("temp") or (m.get("temp") or 0),
            "feels_like": avg_w.get("feels_like") or (m.get("feels_like") or 0),
            "wind_speed": avg_w.get("wind_speed") or (m.get("wind_speed") or 0),
            "wind_gust": avg_w.get("wind_gust") or 0,
            "is_rain": "дождь" in (next_period or "").lower() or avg_w.get("is_rain", False),
            "rain_prob_now": period_rain_prob,
            "rain_total": short.get("rain_total") or 0,
            "precip_mm": short.get("precip_mm") or 0,
            "is_thunder": avg_w.get("is_thunder", False),
            "is_hail": avg_w.get("is_hail", False),
            "visibility": avg_w.get("visibility") or 10000,
            "dew_point": avg_w.get("dew_point"),
            "humidity": avg_w.get("humidity"),
            "soil_temp": avg_w.get("soil_temp"),
            "night_score": period_night_score,
        }
        period_risk = analyze_risks(period_data, is_forecast=True)
        period_verdict = get_rider_verdict(period_risk["score"], now_dt.month)

        period_risks = period_risk["risks"][:4]

        rain_line = ""
        if period_rain_prob and period_rain_prob >= 30:
            if period_rain_prob >= 80:
                rain_line = f"☔️ Дождь почти наверняка: {period_rain_prob}{NBSP}%"
            elif period_rain_prob >= 50:
                rain_line = f"🌧️ Вероятен дождь: {period_rain_prob}{NBSP}%"
            else:
                rain_line = f"🌦️ Возможен дождь: {period_rain_prob}{NBSP}%"

        if rain_line:
            period_risks = filter_rain_risks(period_risks)

        period_risks_text = "\n".join(period_risks) if period_risks else ""

        forecast_block = build_period_block(
            title=next_period_title,
            verdict=period_verdict,
            score=period_risk["score"],
            line1=next_period,
            rain_line=rain_line,
            risks_text=period_risks_text,
        )

    tomorrow_block = ""
    if f:
        f["night_score"] = 0

        fa = analyze_risks(f, is_forecast=True)
        fa_verdict = get_rider_verdict(fa["score"], now_dt.month)
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

        rain_line_tomorrow = ""
        if f.get("rain_prob") and f["rain_prob"] >= 30:
            rp = f["rain_prob"]
            rain_sum = f.get("rain_sum") or 0
            if rp >= 80:
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

        tomorrow_block = build_period_block(
            title="📅 ЗАВТРА",
            verdict=fa_verdict,
            score=fa["score"],
            line1=tomorrow_line,
            rain_line=rain_line_tomorrow,
            risks_text=tomorrow_risks_text,
        )

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
    )

    def src_marker(code):
        return code if code in sources_live else f"{code}*"

    legend_lines = ["📡 Источники:"]
    legend_lines.append(f"{src_marker('M')}{NBSP} — METAR (аэропорт Минск)")
    legend_lines.append(f"{src_marker('OM')} — Open-Meteo (Минск)")
    legend_lines.append(f"{src_marker('W')}{NBSP} — wttr (Минск)")
    legend_lines.append(f"{src_marker('OW')} — OpenWeatherMap (Минск)")
    legend_text = "\n".join(legend_lines)

    agreement = a_city.get("agreement") if isinstance(a_city, dict) else None
    agree_values = a_city.get("agree_values") if isinstance(a_city, dict) else None

    formula_line = formula
    agreement_line = ""
    values_line = ""

    if agreement:
        agreement_line = f"Согласие источников: <b>{agreement.upper()}</b>"
    if agree_values:
        values_line = fmt_spread(agree_values) or ""

    msg = f"""{header_line1}
{header_line2}

—————
{verdict_block}

<b>ЧТО НА ДОРОГЕ</b>
{risk_text}{rec_text}

<b>НА СЕБЯ</b>
{gear_block}

<b>ПЕРЕД ВЫЕЗДОМ</b>
{tech_block}

—————
🟢 <b>ТЕКУЩАЯ ПОГОДА:</b>
{weather_block}"""

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
{legend_text}

Формула: {formula_line}"""

    if agreement_line:
        msg += f"\n{agreement_line}"
    if values_line:
        msg += f"\n{values_line}"

    msg += f"""

—————
{tip}

🏍️ <b>Ровной дороги!</b>
<i>v{BOT_VERSION}</i>"""

    if is_morning:
        alcohol = get_alcohol_warning()
        quote = get_random_quote()
        msg += f"\n\n{alcohol}\n\n💬 <i>{quote}</i>"

    return msg


# ============ УТРЕННЯЯ РАССЫЛКА ============
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


# ============ РАССЫЛКА ОБНОВЛЕНИЙ ============
def notify_version_update(force=False):
    if not UPSTASH_ENABLED and not force:
        return {"skipped": "no_redis"}

    if not BOT_VERSION_NOTIFY and not force:
        return {"skipped": "notify_disabled"}

    last_notified = _redis("get", "last_notified_version") if UPSTASH_ENABLED else None
    if last_notified == BOT_VERSION and not force:
        return {"skipped": "already_notified", "version": BOT_VERSION}

    desc = ""
    date = BOT_VERSION_DATE
    for item in BOT_CHANGELOG:
        if item[0] == BOT_VERSION:
            date = item[1]
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


# ============ ОТПРАВКА ПОГОДЫ (анти-спам 3 сек) ============
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
        return "ok"
    except Exception as e:
        print(f"❌ send_weather: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return "error"


# ============ КОМАНДЫ ============
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
            kb = get_about_keyboard(
                is_subscribed=True,
                is_updater=is_updater(m.chat.id),
            )
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
            kb = get_about_keyboard(
                is_subscribed=False,
                is_updater=is_updater(m.chat.id),
            )
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
    for item in BOT_CHANGELOG[:5]:
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
        f"📅 {datetime.now(MINSK_TZ).strftime('%d.%m.%Y %H:%M')}\n\n"
        f"<b>История версий:</b>\n{changelog_text}",
        parse_mode="HTML"
    )


# ============ CALLBACK ============
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

        elif call.data == "update":
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

        else:
            bot.answer_callback_query(call.id, "❓", cache_time=3)

    except Exception as e:
        print(f"❌ callback: {type(e).__name__}: {e}", flush=True)


# ============ FLASK ============
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


# ============ ЗАПУСК ============
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
