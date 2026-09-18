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
    avg_weather_data,
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
    v = int(v)
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
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return round((a + b) / 2, 1)


def fmt_num(v):
    if v is None:
        return "—"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def build_risk_bar(score):
    """🔴 Бар с черепами: 0/10 → 0 черепов, 10/10 → 10 черепов"""
    score = max(0, min(10, score))
    filled = "☠️" * score
    empty = "⬜️" * (10 - score)
    return f"{filled}{empty}"


def fmt_vis_alert(v):
    """⚠️ если видимость < 500м"""
    if v is None:
        return "—"
    s = format_visibility(v)
    if v < 500:
        return f"⚠️{s}"
    return s


def fmt_field(name, m_val, om_val, unit="", m_key="M", om_key="OM"):
    if m_val is None and om_val is None:
        return f"{name}: —"
    avg_val = avg(m_val, om_val)
    if unit:
        main = f"{fmt_num(avg_val)}{unit}"
    else:
        main = fmt_num(avg_val)
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
• Два риска: город и аэропорт
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
    try:
        bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=text, parse_mode="HTML", reply_markup=reply_markup
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
    try:
        bot.delete_message(chat_id, old_message_id)
    except Exception as e:
        print(f"⚠️ delete: {e}", flush=True)
    try:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        print(f"⚠️ send: {e}", flush=True)


# ============ СБОРКА СООБЩЕНИЯ ============
def build_weather_message(w, a_city, a_airport, short, f, is_morning=False):
    """
    w — словарь {"m": METAR, "om": Open-Meteo, ...}
    a_city — риск по усреднённому (город)
    a_airport — риск по METAR (аэропорт)
    """
    now_dt = datetime.now(MINSK_TZ)
    m = w.get("m") or {}
    om = w.get("om") or {}
    forecast_src = w.get("forecast_source", "none")

    om_label = "W" if forecast_src == "wttr.in" else "OM"

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
    legend_lines = ["Источники:"]
    if m:
        legend_lines.append("M  — METAR (аэропорт Минск)")
    if om and forecast_src == "Open-Meteo":
        legend_lines.append("OM — Open-Meteo (Минск)")
    if om and forecast_src == "wttr.in":
        legend_lines.append("W  — wttr.in (Минск)")
    legend_text = "\n".join(legend_lines)

    # Данные
    m_temp = m.get("temp")
    om_temp = om.get("temp")
    m_dew = m.get("dew_point")
    om_dew = om.get("dew_point")
    m_hum = m.get("humidity")
    om_hum = om.get("humidity")
    m_feels = m.get("feels_like")
    om_feels = om.get("feels_like")
    m_wind = m.get("wind_speed")
    om_wind = om.get("wind_speed")
    m_vis = m.get("visibility")
    om_vis = om.get("visibility")
    m_press = m.get("pressure_mmhg")
    om_press = om.get("pressure_mmhg")
    m_cloud = shorten_cond(m.get("cloud_text"))

    weather_lines = []
    weather_lines.append(fmt_field("🌡️ Температура", m_temp, om_temp, "°C", "M", om_label))
    weather_lines.append(fmt_field("🤔 Ощущается", m_feels, om_feels, "°C", "M", om_label))
    weather_lines.append(fmt_field("💧 Влажность", m_hum, om_hum, "%", "M", om_label))
    weather_lines.append(fmt_field("💦 Точка росы", m_dew, om_dew, "°C", "M", om_label))
    weather_lines.append(fmt_field("💨 Ветер", m_wind, om_wind, "м/с", "M", om_label))

    # Видимость с ⚠️
    if m_vis is not None and om_vis is not None:
        avg_vis = int((m_vis + om_vis) / 2)
        weather_lines.append(
            f"👁️ Видимость: {format_visibility(avg_vis)} "
            f"(M{fmt_vis_alert(m_vis)}|{om_label}{fmt_vis_alert(om_vis)})"
        )
    elif m_vis is not None:
        weather_lines.append(f"👁️ Видимость: {fmt_vis_alert(m_vis)} (M)")
    elif om_vis is not None:
        weather_lines.append(f"👁️ Видимость: {fmt_vis_alert(om_vis)} ({om_label})")
    else:
        weather_lines.append("👁️ Видимость: —")

    weather_lines.append(f"☁️ Облачность: {m_cloud} (M|{om_label})" if m_cloud else "☁️ Облачность: —")
    weather_lines.append(fmt_field("📊 Давление", m_press, om_press, "мм рт.ст.", "M", om_label))

    # Тренд
    trend = m.get("trend")
    if trend:
        if trend.get("type") == "NOSIG":
            weather_lines.append("⏱️ Через 2 часа: Без изменений (M)")
        else:
            weather_lines.append(f"⏱️ Через 2 часа: {trend.get('text')} (M)")
    else:
        weather_lines.append("⏱️ Через 2 часа: — (M)")

    light_str = "темно" if w.get("is_night") else "светло"
    weather_lines.append(f"🌇 Свет: {light_str}")

    weather_block = "\n".join(weather_lines)

    # ============ ДВА БЛОКА РИСКА ============
    city_score = a_city["score"]
    airport_score = a_airport["score"]
    city_verdict = get_rider_verdict(city_score)
    airport_verdict = get_rider_verdict(airport_score)
    city_bar = build_risk_bar(city_score)
    airport_bar = build_risk_bar(airport_score)

    if city_score == airport_score:
        # Объединённый блок
        risk_block = (
            f"🏙️ ГОРОД · ✈️ АЭРОПОРТ · Риск:{city_score}/10\n"
            f"{city_bar}\n"
            f"{city_verdict}"
        )
    else:
        risk_block = (
            f"🏙️ <b>ГОРОД</b> · Риск:{city_score}/10\n"
            f"{city_bar}\n"
            f"{city_verdict}\n\n"
            f"✈️ <b>АЭРОПОРТ</b> · Риск:{airport_score}/10\n"
            f"{airport_bar}\n"
            f"{airport_verdict}"
        )

    # ЧТО НА ДОРОГЕ — объединяем риски города и аэропорта
    all_risks = []
    for r in a_city["risks"] + a_airport["risks"]:
        if r not in all_risks:
            all_risks.append(r)
    risk_factors = all_risks[:4]
    risk_text = "\n".join(risk_factors) if risk_factors else "✅ Дорога чистая"

    # НА СЕБЯ — по городу
    gear = get_gear_short(
        a_city.get("feels_like", m_feels or 0),
        m.get("is_rain", False),
        w.get("is_night", False),
        m_wind or 0,
    )
    gear_block = "\n".join(gear)

    # ПЕРЕД ВЫЕЗДОМ — по городу
    tech = get_tech_check(
        a_city.get("feels_like", m_feels or 0),
        w.get("is_night", False),
        m.get("is_rain", False),
        m_hum, m_dew,
    )
    tech_block = "\n".join(f"✅ {t}" for t in tech)

    # ПРОГНОЗ
    next_period = short.get("next_period", "нет данных")
    next_period_title = short.get("next_period_title", "—")

    forecast_block = ""
    if next_period != "нет данных":
        period_clean = next_period
        for cap in ["Переменная облачность", "Пасмурно", "Ясно", "Облачно", "Малооблачно", "Дождь", "Снег", "Туман"]:
            period_clean = period_clean.replace(cap, cap.lower())
        forecast_block = f"\n<b>{next_period_title}</b>\n{period_clean} ({om_label})\n"

    tomorrow_block = ""
    if f:
        fa = analyze_risks(f, is_forecast=True)
        fa_short = get_short_verdict(fa["score"])
        cond_low = shorten_cond(f.get("condition_text", ""))
        emoji_short = f.get("condition_emoji", "")
        tomorrow_block = (
            f"\n<b>📅 ЗАВТРА</b>\n"
            f"{f['temp_min']}–{f['temp_max']}°C, {cond_low} · {f['wind_speed']}м/с {emoji_short}\n"
            f"{fa_short} ({fa['score']}/10) ({om_label})\n"
            f"{build_risk_bar(fa['score'])}"
        )

    # Совет
    tip = get_tip(
        a_city.get("feels_like", m_feels or 0),
        m_hum, m.get("is_rain", False),
        w.get("is_night", False), m_wind or 0,
        m.get("is_thunder", False), m_vis,
    )

    msg = f"""{header_line1}
{header_line2}
—————
{legend_text}
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
{tomorrow_block.strip()}
—————
💡 <i>{tip}</i>"""

    if is_morning:
        alcohol = get_alcohol_warning()
        quote = get_random_quote()
        msg += f"\n\n{alcohol}\n\n💬 <i>{quote}</i>"

    msg += "\n\n🏍️ <b>Ровной дороги!</b>"

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

                # Риск по городу
                avg_w = avg_weather_data(w)
                a_city = analyze_risks(avg_w)

                # Риск по аэропорту
                m_w = dict(w["m"])
                m_w["_airport_visibility"] = w["m"].get("visibility")
                m_w["is_night"] = w.get("is_night", False)
                a_airport = analyze_risks(m_w)

                short = get_short_forecast()
                f = get_forecast_tomorrow()

                msg = build_weather_message(w, a_city, a_airport, short, f, is_morning=True)

                sent = 0
                failed_403 = []

                for uid in subs:
                    try:
                        bot.send_message(
                            uid, msg, parse_mode="HTML",
                            reply_markup=get_morning_keyboard()
                        )
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


# ============ КОМАНДЫ ============
@bot.message_handler(commands=['start'])
def start(message):
    try:
        save_user(message.chat.id)
        info = bot.get_me()

        if info.username != MY_BOT_USERNAME:
            bot.send_message(
                message.chat.id,
                f"⚠️ <b>Это поддельный бот!</b>\nНастоящий: @{MY_BOT_USERNAME}",
                parse_mode="HTML"
            )
            return

        sub_status = is_subscribed(message.chat.id)
        bot.send_message(
            message.chat.id,
            "🏍️ <b>MOTOWEATHER · МИНСК</b>\n"
            "погода для райдеров\n\n"
            "Проверяю аэропорт Минск — говорю прямо: ехать или нет.\n\n"
            "<b>Жми «СЕЙЧАС» — и вперёд.</b>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(is_subscribed=sub_status)
        )
    except Exception as e:
        print(f"❌ /start: {e}", flush=True)


@bot.message_handler(commands=['weather'])
def weather_cmd(m):
    try:
        save_user(m.chat.id)
        loading = bot.send_message(m.chat.id, "⏳ Смотрю на небо...")
        send_weather(m.chat.id, old_message_id=loading.message_id)
    except Exception as e:
        print(f"❌ /weather: {e}", flush=True)


@bot.message_handler(commands=['about'])
def about_cmd(m):
    try:
        save_user(m.chat.id)
        bot.send_message(m.chat.id, ABOUT_TEXT, parse_mode="HTML",
                         reply_markup=get_about_keyboard())
    except Exception as e:
        print(f"❌ /about: {e}", flush=True)


@bot.message_handler(commands=['subscribe'])
def subscribe_cmd(m):
    try:
        save_user(m.chat.id)
        if is_subscribed(m.chat.id):
            bot.send_message(m.chat.id, ALREADY_SUBSCRIBED, parse_mode="HTML",
                             reply_markup=get_main_keyboard(is_subscribed=True))
            return
        bot.send_message(m.chat.id, SUBSCRIBE_TEXT, parse_mode="HTML",
                         reply_markup=get_subscribe_keyboard())
    except Exception as e:
        print(f"❌ /subscribe: {e}", flush=True)


@bot.message_handler(commands=['unsubscribe'])
def unsubscribe_cmd(m):
    try:
        save_user(m.chat.id)
        if not is_subscribed(m.chat.id):
            bot.send_message(m.chat.id, "ℹ️ Ты не подписан.", parse_mode="HTML",
                             reply_markup=get_main_keyboard(is_subscribed=False))
            return
        bot.send_message(m.chat.id, UNSUBSCRIBE_PROMPT, parse_mode="HTML",
                         reply_markup=get_unsubscribe_keyboard())
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
        msg_id = call.message.message_id

        if call.data in ("weather", "update"):
            if call.data == "update":
                bot.answer_callback_query(call.id, "🔄 Обновляю...", cache_time=3)
            else:
                bot.answer_callback_query(call.id, "⏳ Смотрю...", cache_time=3)
            send_weather(chat_id, old_message_id=msg_id)

        elif call.data == "about":
            bot.answer_callback_query(call.id, "✅", cache_time=3)
            edit_or_send(chat_id, msg_id, ABOUT_TEXT, get_about_keyboard())

        elif call.data == "subscribe":
            if is_subscribed(chat_id):
                bot.answer_callback_query(call.id, "ℹ️ Уже подписан", cache_time=3)
                edit_or_send(chat_id, msg_id, ALREADY_SUBSCRIBED,
                             get_main_keyboard(is_subscribed=True))
            else:
                bot.answer_callback_query(call.id, "🌅", cache_time=3)
                edit_or_send(chat_id, msg_id, SUBSCRIBE_TEXT, get_subscribe_keyboard())

        elif call.data == "subscribe_confirm":
            save_subscriber(chat_id)
            bot.answer_callback_query(call.id, "✅ Подписка", cache_time=3)
            edit_or_send(chat_id, msg_id, SUBSCRIBE_CONFIRMED,
                         get_main_keyboard(is_subscribed=True))

        elif call.data == "subscribe_cancel":
            bot.answer_callback_query(call.id, "❌", cache_time=3)
            sub_status = is_subscribed(chat_id)
            edit_or_send(chat_id, msg_id, SUBSCRIBE_CANCELED,
                         get_main_keyboard(is_subscribed=sub_status))

        elif call.data == "unsubscribe_confirm":
            remove_subscriber(chat_id)
            bot.answer_callback_query(call.id, "❌ Отписан", cache_time=3)
            edit_or_send(chat_id, msg_id, UNSUBSCRIBED,
                         get_main_keyboard(is_subscribed=False))

        elif call.data == "unsubscribe_cancel":
            bot.answer_callback_query(call.id, "✅ Остаёмся", cache_time=3)
            edit_or_send(chat_id, msg_id, UNSUBSCRIBE_CANCELED,
                         get_main_keyboard(is_subscribed=True))

        else:
            bot.answer_callback_query(call.id, "❓", cache_time=3)

    except Exception as e:
        print(f"❌ callback: {type(e).__name__}: {e}", flush=True)


# ============ ОТПРАВКА ПОГОДЫ ============
def send_weather(chat_id, old_message_id=None):
    try:
        w = get_weather()
        if not w or not w.get("m"):
            if old_message_id:
                try:
                    bot.delete_message(chat_id, old_message_id)
                except Exception:
                    pass
            bot.send_message(chat_id, "❌ Небо молчит.")
            return

        # Риск по городу
        avg_w = avg_weather_data(w)
        a_city = analyze_risks(avg_w)

        # Риск по аэропорту
        m_w = dict(w["m"])
        m_w["_airport_visibility"] = w["m"].get("visibility")
        m_w["is_night"] = w.get("is_night", False)
        a_airport = analyze_risks(m_w)

        short = get_short_forecast()
        f = get_forecast_tomorrow()

        msg = build_weather_message(w, a_city, a_airport, short, f, is_morning=False)
        sub_status = is_subscribed(chat_id)

        if old_message_id:
            delete_and_send(chat_id, old_message_id, msg,
                            get_after_weather_keyboard(is_subscribed=sub_status))
        else:
            bot.send_message(chat_id, msg, parse_mode="HTML",
                             reply_markup=get_after_weather_keyboard(is_subscribed=sub_status))

    except Exception as e:
        print(f"❌ send_weather: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()


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
