import json
import os
import threading
from datetime import datetime

import telebot
from flask import Flask, jsonify

from config import (
    BOT_TOKEN, OPENWEATHER_API_KEY, MY_BOT_USERNAME,
    USERS_FILE, ADMIN_ID, MINSK_TZ,
)
from weather import (
    get_weather, get_forecast_tomorrow, get_weekly_forecast,
    get_trend, get_minsk_time, get_light_level, get_minsk_hour,
    get_short_forecast, get_daylight_info,
)
from analyzer import (
    analyze_risks, get_detailed_gear, get_best_time,
    get_short_verdict, get_gear_short, get_tech_check, get_tip,
)
from keyboards import get_main_keyboard, get_after_weather_keyboard


# ============ ПРОВЕРКА КОНФИГА ============
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден!")
    exit(1)

if not OPENWEATHER_API_KEY:
    print("⚠️ OPENWEATHER_API_KEY не найден — прогнозы работать не будут!")


# ============ ИНИЦИАЛИЗАЦИЯ ============
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)


# ============ ПОЛЬЗОВАТЕЛИ ============
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_user(user_id):
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        with open(USERS_FILE, "w") as f:
            json.dump(users, f)


def get_users_count():
    return len(load_users())


# ============ ФОРМАТИРОВАНИЕ ============
def get_temp_description(t):
    if t >= 30: return "очень жарко"
    if t >= 25: return "жарко"
    if t >= 18: return "тепло"
    if t >= 10: return "прохладно"
    if t >= 5: return "холодно"
    if t >= 0: return "очень холодно"
    return "морозно! ⚠️"


def get_wind_description(s):
    if s < 1: return "штиль"
    if s <= 3: return "тихий ветер"
    if s <= 6: return "лёгкий ветер"
    if s <= 10: return "умеренный ветер"
    if s <= 14: return "сильный ветер"
    if s <= 19: return "очень сильный ветер"
    return "штормовой ветер! ⚠️"


def get_wind_feeling(s):
    if s < 1: return "🌿 безветренно"
    if s <= 3: return "🍃 почти незаметно"
    if s <= 6: return "🍃 комфортно"
    if s <= 10: return "🌬️ ощущается"
    if s <= 14: return "💨 требует внимания"
    if s <= 19: return "⚠️ сильно влияет"
    return "🚫 опасно для езды!"


def get_visibility_rating(v):
    if v >= 10000: return "✅ отличная"
    if v >= 5000: return "✅ хорошая"
    if v >= 2000: return "🟡 средняя"
    if v >= 1000: return "🟠 плохая"
    if v >= 500: return "🔴 очень плохая"
    return "🔴🔴 критичная (туман)"


def format_visibility(v):
    if v >= 10000: return "10+ км"
    if v >= 1000: return f"{v / 1000:.1f} км"
    return f"{v} м"


# ============ ТЕКСТЫ ============
ABOUT_TEXT = """ℹ️ <b>О ПРОЕКТЕ</b>

🏍️ <b>MotoWeather Минск</b>

Погода для тех, кто на двух колёсах. Проверяю аэропорт Минск и говорю прямо: <b>ехать или нет</b>.

<b>Что показывает:</b>
• Риск 0–10 — ехать или нет
• Экипировку и подготовку
• Прогноз на 3 часа и утро

━━━━━━━━━━━━━━━━━━━━
🟢 <b>ОТЛИЧНЫЙ ДЕНЬ</b> — Риск 1/10

🌡️ +22°C | 💨 2 м/с (лёгкий ветер)
☀️ Ясно | 🌧️ без осадков
💧 Влажность 45% | 👁️ 10+ км

<b>🎯 ЧТО НА ДОРОГЕ:</b>
• ✅ Дорога чистая

<b>🎽 НА СЕБЯ:</b>
• 🧢 Вентиляция + перчатки

⏱️ <b>ЧЕРЕЗ 3 ЧАСА:</b> +24°C, Ясно
💡 <i>Погода шепчет — едь</i>

━━━━━━━━━━━━━━━━━━━━
🟠 <b>С ОСТОРОЖНОСТЬЮ</b> — Риск 6/10

🌡️ +8°C | 💨 1 м/с | 🌫️ туман
💧 Влажность 93% — воздух близок к туману

<b>🎯 ЧТО НА ДОРОГЕ:</b>
• 🌫️ Туман близко
• ❄️ Холодно
• 🌙 Темно

💡 <i>Визор вниз, дистанцию больше</i>

━━━━━━━━━━━━━━━━━━━━
🔴 <b>ОПАСНО</b> — Риск 9/10

🌡️ +2°C | 💨 18 м/с | ⛈️ гроза
💨 Порывы до 25 м/с

<b>🎯 ЧТО НА ДОРОГЕ:</b>
• ⚡ ГРОЗА!
• 💨 Критический ветер
• 🧊 Риск обледенения

💡 <i>Глуши мотор — сегодня не твой день</i>

━━━━━━━━━━━━━━━━━━━━
<b>📡 ИСТОЧНИКИ:</b>
✈️ METAR (UMMS) — основной
🌐 OpenWeatherMap — прогнозы

<b>👨‍💻 Автор:</b> Alexander_K8V

🏍️ <i>Ровной дороги!</i>

<b>Жми «Сейчас» — увидишь погоду на сегодня.</b>"""


# ============ КОМАНДЫ ============
@bot.message_handler(commands=['start'])
def start(message):
    save_user(message.chat.id)
    info = bot.get_me()

    if info.username != MY_BOT_USERNAME:
        bot.send_message(message.chat.id,
            f"⚠️ <b>Это поддельный бот!</b>\nНастоящий: @{MY_BOT_USERNAME}",
            parse_mode="HTML")
        return

    bot.send_message(message.chat.id,
        "🏍️ <b>MotoWeather Минск</b>\n\n"
        "Погода для тех, кто на двух колёсах.\n"
        "Проверяю аэропорт Минск и говорю прямо: ехать или нет.\n\n"
        "<b>Жми «Сейчас» — и вперёд.</b>",
        parse_mode="HTML", reply_markup=get_main_keyboard())


@bot.message_handler(commands=['weather'])
def weather_cmd(m):
    save_user(m.chat.id)
    bot.send_message(m.chat.id, "⏳ Смотрю на небо...")
    send_weather(m.chat.id)


@bot.message_handler(commands=['about'])
def about_cmd(m):
    save_user(m.chat.id)
    bot.send_message(m.chat.id, ABOUT_TEXT,
                     parse_mode="HTML", reply_markup=get_main_keyboard())


@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    if m.chat.id != ADMIN_ID:
        bot.reply_to(m, "❌ Нет прав.")
        return
    bot.reply_to(m,
        f"📊 <b>Статистика</b>\n👥 {get_users_count()} пользователей\n"
        f"📅 {datetime.now(MINSK_TZ).strftime('%d.%m.%Y %H:%M')}",
        parse_mode="HTML")


# ============ CALLBACK ============
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    try:
        save_user(call.message.chat.id)

        if call.data in ("weather", "update"):
            bot.answer_callback_query(call.id, "⏳ Смотрю на небо...")
            send_weather(call.message.chat.id)
        elif call.data == "about":
            bot.answer_callback_query(call.id, "✅ Открываю")
            bot.send_message(call.message.chat.id, ABOUT_TEXT,
                             parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e:
        print(f"Ошибка callback: {e}")


# ============ ОТПРАВКА: ПОГОДА СЕЙЧАС ============
def send_weather(chat_id):
    w = get_weather()
    if not w:
        bot.send_message(chat_id, "❌ Небо молчит. Попробуй позже.")
        return

    a = analyze_risks(w)
    now_dt = datetime.now(MINSK_TZ)
    now = now_dt.strftime("%H:%M")
    date = now_dt.strftime("%d.%m")

    feels = a.get("feels_like", w.get("feels_like", 0))
    wind_desc = get_wind_description(w["wind_speed"])

    # Ветро-строка: скорость + описание + порывы (если значимы)
    wind_part = f"{w['wind_speed']} м/с ({wind_desc})"
    if w.get("wind_gust") and w["wind_gust"] > w["wind_speed"] + 3:
        wind_part += f" / порывы {w['wind_gust']}"

    # Осадки
    weather_info = f"{w.get('weather_emoji') or ''} {w.get('weather_text') or ''}".strip()
    if not weather_info:
        weather_info = "без осадков"

    # Влажность + видимость
    humidity_str = f"{w['humidity']}%" if w.get("humidity") else "—"
    vis_str = format_visibility(w["visibility"])

    # Светлое время
    light_info = get_daylight_info(w.get("sunrise"), w.get("sunset"))

    # Факторы риска (максимум 3)
    risk_factors = a["risks"][:3]
    risk_block = "\n".join(f"• {r}" for r in risk_factors) if risk_factors else "• ✅ Дорога чистая"

    # Экипировка
    gear = get_gear_short(feels, w.get("is_rain", False), w.get("is_night", False), w["wind_speed"])
    gear_block = "\n".join(f"• {g}" for g in gear)

    # Подготовка
    tech = get_tech_check(feels, w.get("is_night", False), w.get("is_rain", False),
                          w.get("humidity"), w.get("dew_point"))
    tech_block = "\n".join(f"• {t}" for t in tech)

    # Короткий прогноз
    short = get_short_forecast()
    next_hour = short.get("next_hour", "нет данных")
    morning = short.get("morning", "нет данных")

    # Дельта температуры
    if next_hour != "нет данных":
        try:
            fc_temp = int(next_hour.split("°C")[0])
            delta = fc_temp - w["temp"]
            if delta >= 2:
                next_hour = next_hour.replace(f"{fc_temp}°C", f"{fc_temp}°C (+{delta}°C)", 1)
            elif delta <= -2:
                next_hour = next_hour.replace(f"{fc_temp}°C", f"{fc_temp}°C ({delta}°C)", 1)
        except (ValueError, IndexError):
            pass

    # Прогноз на завтра одной строкой
    f = get_forecast_tomorrow()
    tomorrow_line = "нет данных"
    if f:
        fa = analyze_risks(f, is_forecast=True)
        fa_short = get_short_verdict(fa["score"])
        cond_low = f["condition"].split(" ", 1)[-1].lower()
        tomorrow_line = (
            f"{f['temp_min']}–{f['temp_max']}°C, "
            f"{cond_low}, "
            f"{f['wind_speed']} м/с — {fa['color']} {fa_short}"
        )

    # Совет
    tip = get_tip(
        feels, w.get("humidity"), w.get("is_rain", False), w.get("is_night", False),
        w["wind_speed"], w.get("is_thunder", False), w.get("visibility")
    )

    verdict_short = get_short_verdict(a["score"])

    # Сборка — дерзкий стиль
    msg = f"""{a['color']} <b>MotoWeather Минск</b> — {date}, {now}

━━━━━━━━━━━━━━━━━━━━
🌡️ {w['temp']}°C | 💨 {wind_part}
{w.get('cloud_emoji', '')} {w.get('cloud_text', '—')} | 🌧️ {weather_info.lower()}
💧 Влажность {humidity_str} | 👁️ {vis_str}
{light_info}
━━━━━━━━━━━━━━━━━━━━

⚠️ <b>РИСК {a['score']}/10 — {verdict_short}</b>

<b>🎯 ЧТО НА ДОРОГЕ:</b>
{risk_block}

━━━━━━━━━━━━━━━━━━━━
<b>🎽 НА СЕБЯ:</b>
{gear_block}

<b>🔧 ПРОВЕРЬ ЖЕЛЕЗО:</b>
{tech_block}
━━━━━━━━━━━━━━━━━━━━

⏱️ <b>ЧЕРЕЗ 3 ЧАСА:</b> {next_hour}

🌅 <b>УТРОМ:</b> {morning}

📅 <b>ЗАВТРА:</b> {tomorrow_line}
━━━━━━━━━━━━━━━━━━━━
💡 <i>{tip}</i>

🏍️ <b>Ровной дороги!</b>"""

    bot.send_message(chat_id, msg, parse_mode="HTML",
                     reply_markup=get_after_weather_keyboard())


# ============ FLASK ДЛЯ ПИНГА ============
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
        "users": get_users_count(),
        "time": datetime.now(MINSK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    }), 200


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# ============ ЗАПУСК ============
if __name__ == "__main__":
    print("🏍️ MotoWeather Бот запущен!")
    print("✅ METAR + OpenWeatherMap")
    print("📡 Бот готов к работе")

    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"⚠️ remove_webhook: {e}")

    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling()
