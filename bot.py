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
    MINSK_POINTS_ENABLED, LINKS_DATA,
)
from weather import (
    get_weather, get_forecast_tomorrow,
    get_short_forecast, get_daylight_info, hpa_to_mmhg,
    merge_weather_data, get_twilight_state,
    get_astro_night_score, get_next_period, get_next_period_hours,
    get_period_title, get_period_range, min_to_time,
)
from analyzer import (
    analyze_risks, get_short_verdict, get_rider_verdict,
    get_gear_dynamic, get_tech_check_dynamic, get_tip,
    temp_label, wind_label, rain_label,
)
from keyboards import (
    get_main_keyboard, get_after_weather_keyboard, get_morning_keyboard,
    get_about_keyboard, get_subscribe_keyboard, get_unsubscribe_keyboard,
    get_base_back_keyboard, get_links_keyboard,
    get_feedback_blocks_keyboard, get_feedback_params_keyboard,
    get_feedback_direction_keyboard, get_feedback_skip_keyboard,
    get_feedback_cancel_keyboard,
)
from knowledge import BASE_EQUIPMENT_TEXT, build_links_text, MOTORCYCLE_QUOTES
from texts import (
    START_TEXT, SUBSCRIBE_TEXT, SUBSCRIBE_CONFIRMED, SUBSCRIBE_CANCELED,
    UNSUBSCRIBE_PROMPT, UNSUBSCRIBED, UNSUBSCRIBE_CANCELED, ALREADY_SUBSCRIBED,
    UPDATES_ON_TEXT, UPDATES_OFF_TEXT,
    WEEKDAYS_RU, MONTHS_RU,
    get_random_quote, get_alcohol_warning,
)
from formatters import (
    math_round, NBSP, INDENT,
    fmt_num, fmt_avg, format_visibility,
    shorten_cond, classify_clouds, build_risk_bar,
    avg_uv, uv_level, uv_advice, wind_dir_short,
    indent_multiline, fmt_spread, filter_rain_risks,
)
import feedback as fb


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
# ─── КОНЕЦ SEND_OR_EDIT ────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО HELPERS ────────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def _risk_skulls(score):
    if score <= 0:
        return ""
    return f"💀 × {score}"


def _format_vis(v):
    if v is None:
        return "—"
    if v >= 10000:
        return "10+ км"
    if v >= 1000:
        return f"{math_round(v / 1000, 0)} км"
    return f"{int(v)} м"


PERIOD_NIGHT_MAP = {
    "РАССВЕТ": 1,
    "УТРО": 0,
    "ДЕНЬ": 0,
    "ВЕЧЕР": 0,
    "НОЧЬ": 2,
}


def _period_block_h(title, emoji, p_range, verdict, score, risks_list):
    """Формат для периода: заголовок · МОЖНО · 💀 × N → список рисков."""
    skulls = _risk_skulls(score)
    header = f"{emoji} {title} ({p_range}) · {verdict}"
    if skulls:
        header += f" · {skulls}"

    if not risks_list:
        return header

    lines = [header]
    for r in risks_list[:3]:
        lines.append(f"• {r[0].lower() + r[1:]}")

    return "\n".join(lines)
# ─── КОНЕЦ HELPERS ─────────────────────────────────────────


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

    sunrise = w.get("sunrise")
    sunset = w.get("sunset")

    avg_w = a_city.get("avg_w") if isinstance(a_city, dict) else None
    if not avg_w:
        avg_w = {}

    weekday = WEEKDAYS_RU[now_dt.weekday()].lower()
    date_str = now_dt.strftime("%d.%m.%Y")
    time_str = now_dt.strftime("%H:%M")

    # ─── A: Шапка (без лого и названия) ────────────────────
    block_a = f"Минск · {weekday} · {date_str} · {time_str}"

    # ─── Цитата ────────────────────────────────────────────
    daily_quote = random.choice(MOTORCYCLE_QUOTES)

    # ─── B: Вердикт ────────────────────────────────────────
    score = a_city["score"]
    verdict = get_rider_verdict(score, now_dt.month)
    skulls = _risk_skulls(score)

    verdict_full = "ЕХАТЬ " + verdict

    b_lines = []
    if skulls:
        b_lines.append(f"<b>СЕЙЧАС {verdict_full}</b> · {skulls}")
    else:
        b_lines.append(f"<b>СЕЙЧАС {verdict_full}</b>")

    risks = a_city.get("risks", [])

    for risk in risks[:4]:
        b_lines.append(f"• {risk}")

    # Цитаты — полные, топ-2
    research_lines = []

    vis_now = avg_w.get("visibility") or 10000
    temp_now = avg_w.get("temp") or 0
    humidity_now = avg_w.get("humidity") or 0
    dew_now = avg_w.get("dew_point")
    asphalt_now = a_city.get("asphalt_temp") or 0
    is_rain_now = avg_w.get("is_rain", False)
    night_now = w.get("is_night", False)

    is_wet = is_rain_now or (dew_now is not None and temp_now - dew_now <= 1 and humidity_now >= 90)

    if is_wet:
        research_lines.append(
            "📚 JAF (Япония): на мокром асфальте тормозной путь длиннее на треть. "
            "Если на сухом ты тормозишь за 20 метров — на мокром понадобится 26. "
            "Тормози заранее, не в повороте."
        )

    if asphalt_now and asphalt_now < 15:
        research_lines.append(
            "📚 MOTOSAN: летняя моторезина теряет эластичность при +15° и ниже. "
            "Шина «дубеет», пятно контакта хуже, в повороте легче сорваться. "
            "Первые 5 км прогревай резину спокойно."
        )

    if vis_now < 2000:
        research_lines.append(
            "📚 TAAS (Корея): в туман смертность мотоциклистов в 8 раз выше, чем в дождь. "
            "Водители не видят мотоцикл до последнего момента. Туман — самое опасное явление для райдера."
        )

    if night_now:
        research_lines.append(
            "📚 IIHS: половина погибших ночью мотоциклистов — пьяные. "
            "Ночь × алкоголь × мото = смерть. Трезвым за руль, особенно ночью."
        )

    research_lines = research_lines[:2]

    block_b = "\n".join(b_lines)

    metar_warn = avg_w.get("visibility_metar_warning")
    if metar_warn:
        block_b += f"\n{metar_warn}"

    if research_lines:
        block_b += "\n\n" + "\n\n".join(research_lines)

    # ─── F: Погода ─────────────────────────────────────────
    f_lines = []

    t_avg = avg_w.get("temp")
    feels = a_city.get("feels_like")
    if t_avg is not None:
        t_str = f"Температура: {int(t_avg)}°"
        if feels is not None and feels != t_avg:
            t_str += f" (ощущается {int(feels)}°)"
        f_lines.append(t_str)

    asphalt_temp = a_city.get("asphalt_temp")
    if asphalt_temp is not None:
        f_lines.append(f"Асфальт: ≈{int(asphalt_temp)}° (расчетное)")

    wind_avg = avg_w.get("wind_speed")
    gust_avg = avg_w.get("wind_gust")
    wind_dir = m.get("wind_direction") or om.get("wind_direction")

    WIND_DIR_FULL = {
        "С": "северный", "СВ": "северо-восточный",
        "В": "восточный", "ЮВ": "юго-восточный",
        "Ю": "южный", "ЮЗ": "юго-западный",
        "З": "западный", "СЗ": "северо-западный",
        "переменный": "переменный", "штиль": "штиль",
    }
    short_dir = wind_dir_short(wind_dir) if isinstance(wind_dir, str) else None
    full_dir = WIND_DIR_FULL.get(short_dir) if short_dir else None

    if wind_avg is not None:
        w_str = f"Ветер: {int(wind_avg)} м/с"
        if gust_avg and gust_avg > wind_avg:
            w_str += f" (порывы до {int(gust_avg)} м/с)"
        if full_dir:
            w_str += f", {full_dir}"
        f_lines.append(w_str)

    vis_avg_city = avg_w.get("visibility_avg_city")
    vis_min = avg_w.get("visibility_min")
    districts_vis = w.get("precipitation_by_districts", [])

    vis_pairs = []
    for d in districts_vis:
        v = d.get("visibility")
        if v is not None and 0 < v <= 20000:
            vis_pairs.append((d.get("name", "?"), v))

    if vis_pairs:
        vis_values = [v for _, v in vis_pairs]
        avg_vis = sum(vis_values) / len(vis_values)
        min_vis = min(vis_values)

        vis_str = f"Видимость: средняя по Минску {_format_vis(avg_vis)}"

        critical = [(n, v) for n, v in vis_pairs if v < 1000]
        if critical:
            crit_str = ", ".join(f"{n} {int(v)} м" for n, v in critical)
            vis_str += f" · критическая — {crit_str}"
        elif min_vis < avg_vis * 0.6:
            worst_name, worst_v = min(vis_pairs, key=lambda x: x[1])
            vis_str += f" · худший — {worst_name} {_format_vis(worst_v)}"

        f_lines.append(vis_str)
    else:
        fb_vis = avg_w.get("visibility")
        if fb_vis is not None and fb_vis > 0:
            f_lines.append(f"Видимость: {_format_vis(fb_vis)}")
        else:
            f_lines.append("Видимость: 10+ км")

    # Осадки в 【F】
    rain_prob_now = w.get("rain_prob_now")
    is_rain_anywhere = w.get("is_rain_anywhere", False)

    if is_rain_anywhere:
        precip_pairs = []
        for d in districts_vis:
            p = d.get("precip_mm", 0) or 0
            precip_pairs.append((d.get("name", "?"), p))

        if precip_pairs:
            max_p = max(p for _, p in precip_pairs)
            if max_p > 0:
                rain_lbl = rain_label(max_p)
                non_zero = [(n, p) for n, p in precip_pairs if p > 0]
                if len(non_zero) == len(precip_pairs):
                    min_p = min(p for _, p in precip_pairs)
                    if abs(max_p - min_p) < 1.0:
                        f_lines.append(f"Осадки: {rain_lbl} везде ({min_p:.1f}–{max_p:.1f} мм)")
                    else:
                        worst_n, _ = max(non_zero, key=lambda x: x[1])
                        f_lines.append(f"Осадки: {rain_lbl} везде, сильнее {worst_n} {max_p:.1f} мм")
                elif len(non_zero) == 1:
                    n, p = non_zero[0]
                    f_lines.append(f"Осадки: {rain_label(p)} только {n} {p:.1f} мм")
                else:
                    worst_n, worst_p = max(non_zero, key=lambda x: x[1])
                    f_lines.append(f"Осадки: {rain_lbl} ({len(non_zero)} районов), сильнее {worst_n} {worst_p:.1f} мм")
    elif rain_prob_now and rain_prob_now >= 40:
        f_lines.append(f"Осадки: вероятность {rain_prob_now}%")

    if is_rain_anywhere or (rain_prob_now and rain_prob_now >= 40):
        f_lines.append("📡 Точный прогноз — кнопка «Радар осадков» внизу")

    # Сейчас — только если НЕ светло
    twilight = get_twilight_state(sunrise, sunset)
    if twilight == "темно":
        f_lines.append("Сейчас: темно")
    elif twilight in ("смеркается", "темнеет"):
        f_lines.append("Сейчас: смеркается")
    elif twilight in ("светает", "рассветает"):
        f_lines.append("Сейчас: рассветает")

    block_f = "ПОГОДА НА ДАННЫЙ МОМЕНТ\n" + "\n".join(f_lines)

    # ─── D/E: Перед выездом ────────────────────────────────
    gear_items = get_gear_dynamic(
        a_city.get("feels_like", temp_now),
        is_rain_now,
        night_now,
        temp_now,
        rain_prob=rain_prob_now or 0,
    )

    tech_items = get_tech_check_dynamic(
        vis_now,
        humidity_now,
        temp_now,
        avg_w.get("wind_gust") or 0,
        is_rain_now,
        night_now,
        avg_w.get("is_drizzle", False),
    )

    de_lines = ["ПЕРЕД ВЫЕЗДОМ", "📚 БАЗА — жми кнопку ниже!"]
    for item in gear_items:
        de_lines.append(f"+ {item}")
    for item in tech_items:
        de_lines.append(f"+ {item}")

    block_de = "\n".join(de_lines)

    # ─── G: Следующий световой период (цепочка) ────────────
    forecast_block = ""
    next_p = get_next_period(now_dt.hour, now_dt.minute, sunrise, sunset)

    if next_p and short.get("next_period") != "нет данных":
        p_title, p_emoji, p_start, p_end = next_p
        p_range = f"{min_to_time(p_start)}–{min_to_time(p_end)}"

        period_night_score = PERIOD_NIGHT_MAP.get(p_title, 0)

        period_data = {
            "temp": short.get("avg_temp") or 0,
            "feels_like": short.get("avg_temp") or 0,
            "wind_speed": short.get("avg_wind") or 0,
            "wind_gust": short.get("max_gust") or 0,
            "is_rain": (short.get("rain_total") or 0) > 0.5,
            "is_drizzle": False,
            "rain_prob_now": short.get("rain_prob"),
            "rain_prob_day": short.get("rain_prob"),
            "rain_total": short.get("rain_total") or 0,
            "precip_mm": short.get("precip_mm") or 0,
            "is_thunder": False,
            "is_hail": False,
            "visibility": vis_avg_city or 10000,
            "visibility_min": vis_min,
            "visibility_max": avg_w.get("visibility_max"),
            "visibility_big_spread": False,
            "dew_point": avg_w.get("dew_point"),
            "humidity": humidity_now,
            "clouds_pct": avg_w.get("clouds_pct"),
            "soil_temp": avg_w.get("soil_temp"),
            "night_score": period_night_score,
            "twilight": "",
            "period_title": p_title,
        }
        period_risk = analyze_risks(period_data, is_forecast=True)
        period_verdict = get_rider_verdict(period_risk["score"], now_dt.month)

        period_risks = period_risk.get("risks", [])

        period_block = f"{p_emoji} {p_title} ({p_range}) · {period_verdict} · {_risk_skulls(period_risk['score'])}"
        if period_risks:
            for r in period_risks[:2]:
                period_block += f"\n• {r[0].lower() + r[1:]}"

        forecast_block = "СЛЕДУЮЩИЙ СВЕТОВОЙ ПЕРИОД\n\n" + period_block

    # ─── H: Цепочка периодов (продолжение) ────────────────
    tomorrow_block = ""
    if f and f.get("periods"):
        tomorrow_lines = []

        if next_p and next_p[2] >= 1440:
            rp_title, rp_emoji, rp_start, rp_end = next_p
            rp_range = f"{min_to_time(rp_start)}–{min_to_time(rp_end)}"

            rp_night_score = PERIOD_NIGHT_MAP.get(rp_title, 0)
            rp_data = {
                "temp": short.get("avg_temp") or 0,
                "feels_like": short.get("avg_temp") or 0,
                "wind_speed": short.get("avg_wind") or 0,
                "wind_gust": short.get("max_gust") or 0,
                "is_rain": (short.get("rain_total") or 0) > 0.5,
                "is_drizzle": False,
                "rain_prob_now": short.get("rain_prob"),
                "rain_prob_day": short.get("rain_prob"),
                "rain_total": short.get("rain_total") or 0,
                "precip_mm": short.get("precip_mm") or 0,
                "is_thunder": False,
                "is_hail": False,
                "visibility": 10000,
                "dew_point": avg_w.get("dew_point"),
                "humidity": humidity_now,
                "clouds_pct": avg_w.get("clouds_pct"),
                "soil_temp": avg_w.get("soil_temp"),
                "night_score": rp_night_score,
                "twilight": "",
                "period_title": rp_title,
            }
            rp_risk = analyze_risks(rp_data, is_forecast=True)
            rp_verdict = get_rider_verdict(rp_risk["score"], now_dt.month)

            rp_block = _period_block_h(
                rp_title, rp_emoji, rp_range,
                rp_verdict, rp_risk["score"],
                rp_risk.get("risks", []),
            )
            tomorrow_lines.append(rp_block)
            tomorrow_lines.append("")

        for p in f["periods"]:
            p_night_score = PERIOD_NIGHT_MAP.get(p["title"], 0)

            p_data = {
                "temp": p["temp"],
                "feels_like": p["temp"],
                "wind_speed": p["wind_speed"],
                "wind_gust": p.get("wind_gust") or 0,
                "is_rain": (p.get("rain_total") or 0) > 0.5,
                "is_drizzle": False,
                "rain_prob_now": p.get("rain_prob"),
                "rain_prob_day": p.get("rain_prob"),
                "rain_total": p.get("rain_total") or 0,
                "precip_mm": p.get("rain_total") or 0,
                "is_thunder": False,
                "is_hail": False,
                "visibility": 10000,
                "dew_point": None,
                "humidity": 70,
                "clouds_pct": 50,
                "soil_temp": None,
                "night_score": p_night_score,
                "twilight": "",
                "weather_code": p.get("weather_code"),
                "period_title": p["title"],
            }
            p_risk = analyze_risks(p_data, is_forecast=True)
            p_verdict = get_rider_verdict(p_risk["score"], now_dt.month)

            p_block = _period_block_h(
                p["title"], p["emoji"], p["range"],
                p_verdict, p_risk["score"],
                p_risk.get("risks", []),
            )
            tomorrow_lines.append(p_block)
            tomorrow_lines.append("")

        tomorrow_block = "\n".join(tomorrow_lines).rstrip()

    # ─── J: Подпись ────────────────────────────────────────
    block_j = f"v{BOT_VERSION}\n«Газ до отсечки — только если мозг в черепе», @Aleksandr_K8V"

    # ─── Сборка ────────────────────────────────────────────
    parts = [block_a, "", daily_quote, "", block_b, "", block_f, "", block_de]

    if forecast_block:
        parts.extend(["", forecast_block])

    if tomorrow_block:
        parts.extend(["", tomorrow_block])

    parts.extend(["", block_j])

    return "\n".join(parts)
# ─── КОНЕЦ BUILD_WEATHER_MESSAGE ───────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО MORNING_BROADCAST ──────────────────────────────
# ═══════════════════════════════════════════════════════════
def _prepare_avg_w(w):
    avg_w = merge_weather_data(w)
    if not avg_w:
        return None

    avg_w["twilight"] = get_twilight_state(w.get("sunrise"), w.get("sunset"))

    districts_vis = w.get("precipitation_by_districts", [])
    vis_pairs = []
    for d in districts_vis:
        v = d.get("visibility")
        if v is not None and 0 < v <= 20000:
            vis_pairs.append((d.get("name", "?"), v))

    if vis_pairs:
        vis_values = [v for _, v in vis_pairs]
        min_v = min(vis_values)
        max_v = max(vis_values)
        avg_v = sum(vis_values) / len(vis_values)

        avg_w["visibility"] = min_v
        avg_w["visibility_min"] = min_v
        avg_w["visibility_max"] = max_v
        avg_w["visibility_avg_city"] = avg_v
        avg_w["visibility_big_spread"] = (max_v / min_v >= 3.0) if min_v > 0 else False

        metar_vis = None
        if w.get("m"):
            mv = w["m"].get("visibility")
            if mv is not None and 0 < mv <= 20000:
                metar_vis = mv

        if metar_vis is not None and metar_vis < min_v:
            ratio = min_v / metar_vis if metar_vis > 0 else 999
            if ratio > 3.0 and metar_vis < 1000:
                mt_str = f"{int(metar_vis)} м" if metar_vis < 1000 else f"{int(metar_vis / 1000)} км"
                avg_w["visibility_metar_warning"] = (
                    f"⚠️ Аэропорт: туман {mt_str} — для тех, кто едет на восток"
                )

        ow = w.get("ow") or {}
        ow_vis = ow.get("visibility")
        if ow_vis is not None and 0 < ow_vis <= 20000:
            if ow_vis < 1000 and min_v > 5000:
                ow_str = f"{int(ow_vis)} м"
                if "visibility_metar_warning" not in avg_w:
                    avg_w["visibility_metar_warning"] = (
                        f"⚠️ OWM: туман {ow_str}, в городе до {math_round(min_v / 1000, 0)} км"
                    )

    om_src = w.get("om") or {}
    owm_src = w.get("ow") or {}
    wttr_src = w.get("w") or {}

    temp_vals = []
    for s in [om_src, owm_src, wttr_src]:
        if s.get("temp") is not None:
            temp_vals.append(s["temp"])

    if temp_vals:
        avg_w["temp"] = math_round(sum(temp_vals) / len(temp_vals), 0)

    feels_vals = []
    for s in [om_src, owm_src, wttr_src]:
        if s.get("feels_like") is not None:
            feels_vals.append(s["feels_like"])

    if feels_vals:
        avg_w["feels_like"] = math_round(sum(feels_vals) / len(feels_vals), 0)

    return avg_w


def _calc_asphalt_temp(avg_w, w):
    temp = avg_w.get("temp")
    if temp is None:
        return None

    m = w.get("m") or {}
    om = w.get("om") or {}
    ww = w.get("w") or {}
    ow = w.get("ow") or {}

    uv_vals = [s.get("uv_index") for s in [m, om, ww, ow] if s.get("uv_index") is not None]
    uv = math_round(sum(uv_vals) / len(uv_vals), 0) if uv_vals else None

    is_night = w.get("is_night", False)
    is_rain = avg_w.get("is_rain", False)

    if is_night:
        return temp
    if is_rain:
        return temp + 2
    if uv is not None and uv >= 3:
        return temp + 12
    return temp + 5


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

        avg_w = _prepare_avg_w(w)
        if not avg_w:
            return {"error": "merge_failed", "date": today_str}

        a_city = analyze_risks(avg_w)
        a_city["agreement"] = avg_w.get("agreement")
        a_city["agree_values"] = avg_w.get("agree_values")
        a_city["avg_w"] = avg_w
        a_city["asphalt_temp"] = _calc_asphalt_temp(avg_w, w)

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

        avg_w = _prepare_avg_w(w)
        if not avg_w:
            send_or_edit(chat_id, "❌ Небо молчит.", None)
            return "error"

        a_city = analyze_risks(avg_w)
        print(f"🔍 send_weather: score={a_city['score']}, risks={a_city['risks']}", flush=True)

        a_city["agreement"] = avg_w.get("agreement")
        a_city["agree_values"] = avg_w.get("agree_values")
        a_city["avg_w"] = avg_w
        a_city["asphalt_temp"] = _calc_asphalt_temp(avg_w, w)

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
        desc_safe = desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        changelog_lines.append(f"{marker} <b>v{ver}</b> ({date}) — {desc_safe}")
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

        elif call.data == "base_equip":
            bot.answer_callback_query(call.id, "📚 База", cache_time=3)
            send_or_edit(
                chat_id,
                BASE_EQUIPMENT_TEXT,
                get_base_back_keyboard()
            )

        elif call.data == "links":
            bot.answer_callback_query(call.id, "🔗 Ссылки", cache_time=3)
            send_or_edit(
                chat_id,
                build_links_text(LINKS_DATA),
                get_links_keyboard(LINKS_DATA)
            )

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
