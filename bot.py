import json
import os
import random
import re
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
    UPSTASH_URL, UPSTASH_TOKEN, OWM_API_KEY,
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


# ============ ПРОВЕРКА КОНФИГА ============
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден!", flush=True)
    exit(1)

if UPSTASH_URL and UPSTASH_TOKEN:
    print("✅ Хранилище: Upstash Redis", flush=True)
else:
    print("⚠️ Хранилище: локальные файлы", flush=True)

if OWM_API_KEY:
    print("✅ Источники: METAR + Open-Meteo + wttr.in + OpenWeatherMap", flush=True)
else:
    print("⚠️ Источники: METAR + Open-Meteo + wttr.in (OWM отключён — нет ключа)", flush=True)


# ============ ИНИЦИАЛИЗАЦИЯ ============
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)


# ============ НЕВИДИМЫЕ ПРОБЕЛЫ ============
Z = "\u200b"
DEV_USERNAME = f"@{Z}Aleksandr_K8V"
NBSP = "\u00A0"


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


# ============ ХРАНЕНИЕ ID ПОСЛЕДНЕГО СООБЩЕНИЯ БОТА ============
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


def format_visibility(v):
    if v is None:
        return "—"
    v = int(v)
    if v >= 10000:
        return f"10+{NBSP}км"
    if v >= 1000:
        km = v / 1000
        if km == int(km):
            return f"{int(km)}{NBSP}км"
        return f"{km:.1f}{NBSP}км".replace(".", ",")
    return f"{v}{NBSP}м"


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


def fmt_num(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        s = f"{v:.1f}"
        s = s.replace(".", ",")
        if s.endswith(",0"):
            s = s[:-2]
        return s
    return str(v)


def build_risk_bar(score):
    score = max(0, min(10, score))
    if score == 0:
        return ""
    return "💀" * score


def fmt_range(values, unit=""):
    vals = [v for v in values if v is not None]
    if not vals:
        return f"—{NBSP}{unit}" if unit else "—"
    lo, hi = min(vals), max(vals)
    if lo == hi:
        s = fmt_num(lo)
    else:
        s = f"{fmt_num(lo)}–{fmt_num(hi)}"
    return f"{s}{NBSP}{unit}" if unit else s


def avg_uv(live_values):
    vals = [v for v in live_values if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals))


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


# ============ ТЕКСТЫ ============
START_TEXT = """🌤 <b>MOTOWEATHER · МИНСК</b>

<b>Что это?</b>
Погодный ориентир для райдеров Минска.
Не точный прогноз, а честная сводка:
ехать сегодня или нет.

<b>Откуда беру данные:</b>
• METAR аэропорта Минск (UMMS) — фактическая погода «здесь и сейчас». Аэропорт числится за Минском, но стоит на открытой равнине в 20 км от центра. Там всегда ветренее, а зимой холоднее, чем в городе. Поэтому я поправляю данные METAR под Минск — чтобы они были ближе к реальной погоде в городе.

• OpenWeatherMap, Open-Meteo и wttr — три прогнозных сервиса. Каждый показывает погоду не для твоей улицы, а для квадрата на карте. Размер этого квадрата у всех разный — иногда совсем маленький (меньше километра), а иногда больше десяти километров. Внутри квадрата погода может отличаться, но это не учитывается.

<b>Как считаю:</b>
1. Беру факт с аэропорта и поправляю под Минск (ветер, температура).
2. Сравниваю с тремя прогнозами и убираю явные выбросы — если один сервис врёт, он не портит общую картину.
3. Показываю диапазон, а не одно число: например, «ветер 3–5 м/с», а не «4 м/с».

<b>Что на выходе:</b>
• Погода сейчас — с поправкой на Минск.
• Прогноз на ближайшие часы.
• Вердикт: ехать или нет — по ветру, осадкам и температуре.

<b>Про точность:</b>
Честно: возможна погрешность примерно ±3 °C по температуре и ±3 м/с по ветру. Это ориентир, а не гарантия. Но если три сервиса из четырёх сходятся — доверия больше.

Нажми ПРОГНОЗ — и вперёд.

—
👨‍💻 Разработчик: @Aleksandr_K8V"""


ABOUT_TEXT = f"""🌤 <b>MOTOWEATHER · МИНСК</b>

Погода для райдеров.

<b>Собираю данные с 4 источников:</b>
• METAR аэропорта Минск;
• Open-Meteo;
• wttr;
• OpenWeatherMap.

<b>Как считаю:</b>
Анализирую полученные данные, убираю явные выбросы, вывожу средние показатели и выдаю вердикт: ехать или нет.

<b>Что на выходе:</b>
• Погода сейчас — с поправкой на Минск;
• Прогноз на ближайшее время;
• Вердикт: ехать или нет — по ветру, осадкам и температуре.

<b>Риск от 0 до 10 · экипировка · прогноз</b>

<b>Подписка:</b> /subscribe
<b>Отписка:</b> /unsubscribe

—
👨‍💻 Разработчик: {DEV_USERNAME}"""


SUBSCRIBE_TEXT = """🌅 <b>Подписка на утро</b>

Каждый день в <b>7:00</b>:
• погода в Минске;
• вердикт — ехать или нет;
• экипировка;
• прогноз на ближайшее время;
• цитата.

Подписаться?"""

SUBSCRIBE_CONFIRMED = """✅ <b>Подписка активирована</b>

Прогноз в 7:00 каждый день.

Отписаться: /unsubscribe"""

SUBSCRIBE_CANCELED = """❌ <b>Подписка отменена</b>

Жми «ПРОГНОЗ» чтобы вернуться."""

UNSUBSCRIBE_PROMPT = """❌ <b>Отписаться от рассылки?</b>

Перестанешь получать утренний прогноз в 7:00."""

UNSUBSCRIBED = """❌ <b>Отписан от рассылки</b>

Жми «ПРОГНОЗ» — и вперёд."""

UNSUBSCRIBE_CANCELED = """✅ <b>Остаёмся!</b>

Прогноз в 7:00 продолжит приходить."""

ALREADY_SUBSCRIBED = """ℹ️ <b>Ты уже подписан</b>

Отписаться: /unsubscribe"""


# ============ ЕДИНАЯ ТОЧКА ОТПРАВКИ ============
def send_or_edit(chat_id, text, reply_markup=None):
    """
    Удаляет последнее сообщение бота (если есть) и шлёт новое.
    Запоминает id нового сообщения — для следующего цикла.
    """
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


# ============ СБОРКА СООБЩЕНИЯ ============
def build_weather_message(w, a_city, short, f, is_morning=False):
    if not isinstance(short, dict):
        print(f"⚠️ short не dict: type={type(short).__name__}, value={short!r}", flush=True)
        short = {}

    now_dt = datetime.now(MINSK_TZ)
    m = w.get("m") or {}
    om = w.get("om") or {}
    ww = w.get("w") or {}
    ow = w.get("ow") or {}
    sources_live = w.get("sources_live", [])
    formula = w.get("formula", "")

    # Шапка
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

    # Легенда
    def src_marker(code):
        return code if code in sources_live else f"{code}*"

    legend_lines = ["📡 Источники:"]
    legend_lines.append(f"{src_marker('M')}{NBSP} — METAR (аэропорт Минск)")
    legend_lines.append(f"{src_marker('OM')} — Open-Meteo (Минск)")
    legend_lines.append(f"{src_marker('W')}{NBSP} — wttr (Минск)")
    legend_lines.append(f"{src_marker('OW')} — OpenWeatherMap (Минск)")
    legend_text = "\n".join(legend_lines)

    # Сбор значений
    def gather(key, sources_keys):
        return [src.get(key) for code, src in sources_keys if src]

    src_map = [("M", m), ("OM", om), ("W", ww), ("OW", ow)]

    weather_lines = []

    weather_lines.append(f"🌡️ Температура: {fmt_range(gather('temp', src_map), '°C')}")
    weather_lines.append(f"🤔 Ощущается: {fmt_range(gather('feels_like', src_map), '°C')}")

    soil = om.get("soil_temp") if om else None
    weather_lines.append(
        f"🌱 Почва: {fmt_num(soil)}{NBSP}°C" if soil is not None else "🌱 Почва: —"
    )

    wind_vals = gather("wind_speed", src_map)
    gust_vals = gather("wind_gust", src_map)

    wind_line = "💨 Ветер: "
    if any(v is not None for v in wind_vals):
        wind_line += fmt_range(wind_vals, "м/с")
        gmax = max([g for g in gust_vals if g is not None], default=None)
        if gmax is not None and gmax > (max([v for v in wind_vals if v is not None], default=0)):
            wind_line += f" (до {fmt_num(gmax)}{NBSP}м/с)"
        wind_dir = m.get("wind_direction") or om.get("wind_direction")
        if wind_dir and isinstance(wind_dir, str):
            dir_map = {
                "С": "северный", "СВ": "северо-восточный",
                "В": "восточный", "ЮВ": "юго-восточный",
                "Ю": "южный", "ЮЗ": "юго-западный",
                "З": "западный", "СЗ": "северо-западный",
                "переменный": "переменный", "штиль": "штиль",
            }
            short_dir = wind_dir.split(" ")[0]
            if short_dir in dir_map:
                wind_line += f", {dir_map[short_dir]}"
            else:
                wind_line += f", {wind_dir}"
    else:
        wind_line += "—"
    weather_lines.append(wind_line)

    vis_vals = [v for v in gather("visibility", src_map) if v is not None]
    if vis_vals:
        lo, hi = min(vis_vals), max(vis_vals)
        if hi >= 10000:
            vis_str = "10+" + NBSP + "км"
        elif lo == hi:
            vis_str = format_visibility(lo)
        else:
            vis_str = f"{format_visibility(lo)}–{format_visibility(hi)}"
        if lo < 500:
            vis_str = "⚠️" + vis_str
        weather_lines.append(f"👁️ Видимость: {vis_str}")
    else:
        weather_lines.append("👁️ Видимость: —")

    weather_lines.append(f"💧 Влажность: {fmt_range(gather('humidity', src_map), '%')}")
    weather_lines.append(f"💦 Точка росы: {fmt_range(gather('dew_point', src_map), '°C')}")

    cloud_text = shorten_cond(m.get("cloud_text")) if m.get("cloud_text") else None
    cloud_vals = [v for v in gather("clouds_pct", src_map) if v is not None]
    if cloud_vals:
        lo, hi = min(cloud_vals), max(cloud_vals)
        cloud_pct = f"{fmt_num(lo)}{NBSP}%" if lo == hi else f"{fmt_num(lo)}–{fmt_num(hi)}{NBSP}%"
        if cloud_text:
            weather_lines.append(f"🌥️ Облачность: {cloud_text} ({cloud_pct})")
        else:
            weather_lines.append(f"🌥️ Облачность: {cloud_pct}")
    elif cloud_text:
        weather_lines.append(f"🌥️ Облачность: {cloud_text}")
    else:
        weather_lines.append("🌥️ Облачность: —")

    precip_vals = [v for v in gather("precip_mm", src_map) if v is not None and v > 0]
    if precip_vals:
        lo, hi = min(precip_vals), max(precip_vals)
        if lo == hi:
            weather_lines.append(f"🌧️ Осадки: {fmt_num(lo)}{NBSP}мм")
        else:
            weather_lines.append(f"🌧️ Осадки: {fmt_num(lo)}–{fmt_num(hi)}{NBSP}мм")
    elif m.get("is_rain"):
        weather_lines.append(f"🌧️ Осадки: {m.get('weather_text') or 'дождь'}")

    weather_lines.append(f"📊 Давление: {fmt_range(gather('pressure_mmhg', src_map), 'мм рт. ст.')}")

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
        weather_lines.append(f"☀️ UV-индекс: {uv}{NBSP}({lvl})")

    weather_block = "\n".join(weather_lines)

    # Риск
    score = a_city["score"]
    verdict = get_rider_verdict(score)
    bar = build_risk_bar(score)

    risk_block = f"<b>{verdict}</b>\nРИСК: {score}/10"
    if bar:
        risk_block += f"\n{bar}"

    risk_factors = a_city["risks"][:4]
    risk_text = "\n".join(risk_factors) if risk_factors else "✅ Дорога чистая"

    # НА СЕБЯ
    gear = get_gear_short(
        a_city.get("feels_like", m.get("feels_like") or 0),
        m.get("is_rain", False) or ww.get("is_rain", False),
        w.get("is_night", False),
        (m.get("wind_speed") or om.get("wind_speed") or 0),
    )
    gear_block = "\n".join(gear)

    # ПЕРЕД ВЫЕЗДОМ
    tech = get_tech_check(
        a_city.get("feels_like", m.get("feels_like") or 0),
        w.get("is_night", False),
        m.get("is_rain", False) or ww.get("is_rain", False),
        m.get("humidity"), m.get("dew_point"),
    )
    tech_block = "\n".join(f"✅ {t}" for t in tech)

    # === ПРОГНОЗ ===
    next_period = short.get("next_period", "нет данных")
    next_period_title = short.get("next_period_title", "—")

    forecast_block = ""
    if next_period != "нет данных":
        period_data = {
            "temp": short.get("current_temp") or (m.get("temp") or 0),
            "feels_like": short.get("current_temp") or (m.get("temp") or 0),
            "wind_speed": (m.get("wind_speed") or om.get("wind_speed") or 0),
            "wind_gust": max([g for g in [m.get("wind_gust"), om.get("wind_gust"),
                                           ww.get("wind_gust"), ow.get("wind_gust")]
                              if g is not None], default=0),
            "is_rain": "дождь" in (next_period or "").lower() or m.get("is_rain", False),
            "is_thunder": m.get("is_thunder", False),
            "visibility": m.get("visibility") or 10000,
            "dew_point": m.get("dew_point"),
            "humidity": m.get("humidity"),
        }
        period_risk = analyze_risks(period_data)
        period_bar = build_risk_bar(period_risk["score"])
        period_verdict = get_rider_verdict(period_risk["score"])

        if period_bar:
            forecast_block = f"{next_period_title} | {period_bar}\n{next_period}\n{period_verdict}"
        else:
            forecast_block = f"{next_period_title}\n{next_period}\n{period_verdict}"

    # Сноска про осадки — только если вероятности ≥ 30 %
    precip_note = ""
    prob_now = re.search(r"дождь\s*(\d+)\s*%", next_period or "")
    prob_tomorrow = f.get("rain_prob") if f else None
    probs_found = []
    if prob_now and int(prob_now.group(1)) >= 30:
        probs_found.append(prob_now.group(1))
    if prob_tomorrow and prob_tomorrow >= 30:
        probs_found.append(str(prob_tomorrow))
    if probs_found:
        precip_note = f"❗ дождь {' % / '.join(probs_found)} % — вероятность, что дождь пойдёт"

    # === ЗАВТРА ===
    tomorrow_block = ""
    if f:
        fa = analyze_risks(f, is_forecast=True)
        fa_verdict = get_rider_verdict(fa["score"])
        cond_low = shorten_cond(f.get("condition_text", ""))
        emoji_short = f.get("condition_emoji", "")
        tomorrow_bar = build_risk_bar(fa["score"])

        tomorrow_line = (
            f"{f['temp_min']}–{f['temp_max']}{NBSP}°C · "
            f"{f['wind_speed']}{NBSP}м/с"
        )
        if f.get("wind_gust"):
            tomorrow_line += f" (до {fmt_num(f['wind_gust'])}{NBSP}м/с)"
        if f.get("rain_prob") and f["rain_prob"] > 30:
            tomorrow_line += f" · дождь {f['rain_prob']}{NBSP}%"
        else:
            tomorrow_line += f" · {cond_low} {emoji_short}".rstrip()

        if tomorrow_bar:
            tomorrow_block = f"\n\n📅 ЗАВТРА | {tomorrow_bar}\n{tomorrow_line}\n{fa_verdict}"
        else:
            tomorrow_block = f"\n\n📅 ЗАВТРА\n{tomorrow_line}\n{fa_verdict}"

    # Совет
    tip = get_tip(
        a_city.get("feels_like", m.get("feels_like") or 0),
        m.get("humidity"),
        m.get("is_rain", False) or ww.get("is_rain", False),
        w.get("is_night", False),
        (m.get("wind_speed") or om.get("wind_speed") or 0),
        m.get("is_thunder", False),
        m.get("visibility"),
        wind_gust=(max([g for g in [m.get("wind_gust"), om.get("wind_gust"),
                                    ww.get("wind_gust"), ow.get("wind_gust")]
                        if g is not None], default=0)),
        uv_index=(uv if uv is not None else 0),
    )

    msg = f"""{header_line1}
{header_line2}
—————
{legend_text}

{formula}
—————
{weather_block}
—————
{risk_block}
—————
<b>ЧТО НА ДОРОГЕ</b>
{risk_text}
—————
<b>НА СЕБЯ</b>
{gear_block}
—————
<b>ПЕРЕД ВЫЕЗДОМ</b>
{tech_block}
—————
{forecast_block.strip()}
{tomorrow_block.strip()}"""

    if precip_note:
        msg += f"\n\n{precip_note}"

    msg += f"""
—————
{tip}

🏍️ <b>Ровной дороги!</b>"""

    if is_morning:
        alcohol = get_alcohol_warning()
        quote = get_random_quote()
        msg += f"\n\n{alcohol}\n\n💬 <i>{quote}</i>"

    return msg


# ============ УТРЕННЯЯ РАССЫЛКА ============
def morning_broadcast_loop():
    print("⏰ Поток утренней рассылки запущен", flush=True)

    while True:
        try:
            now = datetime.now(MINSK_TZ)
            today_str = now.strftime("%Y-%m-%d")

            if now.hour == 7 and now.minute < 5:
                last_sent = get_last_morning_date()
                if last_sent == today_str:
                    time.sleep(60)
                    continue

                print(f"🌅 Утренняя рассылка ({today_str})", flush=True)

                subs = load_subscribers()
                if not subs:
                    set_last_morning_date(today_str)
                    continue

                w = get_weather()
                if not w or not w.get("m"):
                    set_last_morning_date(today_str)
                    continue

                avg_w = merge_weather_data(w)
                a_city = analyze_risks(avg_w)

                short = get_short_forecast()
                f = get_forecast_tomorrow()

                msg = build_weather_message(w, a_city, short, f, is_morning=True)

                sent = 0
                failed_403 = []

                for uid in subs:
                    try:
                        # Рассылка НЕ удаляет старое — иначе снесёт пользователю что-то
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

                print(f"✅ Рассылка: {sent} ок, {len(failed_403)} удалено", flush=True)

                for uid in failed_403:
                    remove_subscriber(uid)

                set_last_morning_date(today_str)

        except Exception as e:
            print(f"❌ Ошибка рассылки: {e}", flush=True)

        time.sleep(60)


# ============ ОТПРАВКА ПОГОДЫ ============
def send_weather(chat_id):
    """Собирает погоду и отправляет через send_or_edit (удаляет старое)."""
    try:
        w = get_weather()
        if not w or not w.get("m"):
            send_or_edit(chat_id, "❌ Небо молчит.", None)
            return

        avg_w = merge_weather_data(w)
        a_city = analyze_risks(avg_w)
        short = get_short_forecast()
        f = get_forecast_tomorrow()

        msg = build_weather_message(w, a_city, short, f, is_morning=False)
        send_or_edit(chat_id, msg, get_after_weather_keyboard(is_subscribed(chat_id)))
    except Exception as e:
        print(f"❌ send_weather: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()


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
        kb = get_about_keyboard(is_subscribed(m.chat.id))
        send_or_edit(m.chat.id, ABOUT_TEXT, kb)
    except Exception as e:
        print(f"❌ /about: {e}", flush=True)


@bot.message_handler(commands=['subscribe'])
def subscribe_cmd(m):
    try:
        save_user(m.chat.id)
        if is_subscribed(m.chat.id):
            kb = get_about_keyboard(is_subscribed=True)
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
            kb = get_about_keyboard(is_subscribed=False)
            send_or_edit(m.chat.id, "ℹ️ Ты не подписан.", kb)
            return
        send_or_edit(m.chat.id, UNSUBSCRIBE_PROMPT, get_unsubscribe_keyboard())
    except Exception as e:
        print(f"❌ /unsubscribe: {e}", flush=True)


@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    if not ADMIN_ID or m.chat.id != ADMIN_ID:
        bot.reply_to(m, "❌ Нет прав.")
        return
    bot.reply_to(
        m,
        f"📊 <b>Статистика</b>\n"
        f"👥 Юзеров: {get_users_count()}\n"
        f"🌅 Подписчиков: {get_subscribers_count()}\n"
        f"💾 Хранилище: {'Upstash' if UPSTASH_ENABLED else 'файлы'}\n"
        f"📅 {datetime.now(MINSK_TZ).strftime('%d.%m.%Y %H:%M')}",
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
            bot.answer_callback_query(call.id, "⏳ Смотрю...", cache_time=3)
            send_weather(chat_id)

        elif call.data == "update":
            bot.answer_callback_query(call.id, "🔄 Обновляю...", cache_time=3)
            send_weather(chat_id)

        elif call.data == "about":
            bot.answer_callback_query(call.id, "✅", cache_time=3)
            kb = get_about_keyboard(is_subscribed(chat_id))
            send_or_edit(chat_id, ABOUT_TEXT, kb)

        elif call.data == "subscribe":
            if is_subscribed(chat_id):
                bot.answer_callback_query(call.id, "ℹ️ Уже подписан", cache_time=3)
                kb = get_about_keyboard(is_subscribed=True)
                send_or_edit(chat_id, ALREADY_SUBSCRIBED, kb)
            else:
                bot.answer_callback_query(call.id, "🌅", cache_time=3)
                send_or_edit(chat_id, SUBSCRIBE_TEXT, get_subscribe_keyboard())

        elif call.data == "subscribe_confirm":
            save_subscriber(chat_id)
            bot.answer_callback_query(call.id, "✅ Подписка", cache_time=3)
            kb = get_about_keyboard(is_subscribed=True)
            send_or_edit(chat_id, SUBSCRIBE_CONFIRMED, kb)

        elif call.data == "subscribe_cancel":
            bot.answer_callback_query(call.id, "❌", cache_time=3)
            kb = get_about_keyboard(is_subscribed(chat_id))
            send_or_edit(chat_id, SUBSCRIBE_CANCELED, kb)

        elif call.data == "unsubscribe":
            if not is_subscribed(chat_id):
                bot.answer_callback_query(call.id, "ℹ️ Не подписан", cache_time=3)
                kb = get_about_keyboard(is_subscribed=False)
                send_or_edit(chat_id, "ℹ️ Ты не подписан.", kb)
            else:
                bot.answer_callback_query(call.id, "❌", cache_time=3)
                send_or_edit(chat_id, UNSUBSCRIBE_PROMPT, get_unsubscribe_keyboard())

        elif call.data == "unsubscribe_confirm":
            remove_subscriber(chat_id)
            bot.answer_callback_query(call.id, "❌ Отписан", cache_time=3)
            kb = get_about_keyboard(is_subscribed=False)
            send_or_edit(chat_id, UNSUBSCRIBED, kb)

        elif call.data == "unsubscribe_cancel":
            bot.answer_callback_query(call.id, "✅ Остаёмся", cache_time=3)
            kb = get_about_keyboard(is_subscribed=True)
            send_or_edit(chat_id, UNSUBSCRIBE_CANCELED, kb)

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
        "storage": "upstash" if UPSTASH_ENABLED else "files",
        "users": get_users_count(),
        "subscribers": get_subscribers_count(),
        "time": datetime.now(MINSK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    }), 200


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
