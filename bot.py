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
    get_trend, get_minsk_time, get_light_level, get_minsk_hour
)
from analyzer import analyze_risks, get_detailed_gear, get_best_time
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
TIPS_TEXT = """🏍️ <b>СОВЕТЫ ДЛЯ РАЙДЕРОВ:</b>

🟢 <b>Светло:</b> проверьте шины и свет
🟡 <b>Ветер:</b> держите руль крепче
🔴 <b>Дождь:</b> увеличьте дистанцию
⚡ <b>Гроза:</b> остановитесь, найдите укрытие
🌫️ <b>Туман:</b> противотуманки, снизьте скорость
🌙 <b>Темно:</b> включите свет

💬 <b>ЦИТАТЫ:</b>
"Опытный райдер никогда не выезжает без защиты и перчаток."
"Для настоящего райдера важен не мотоцикл, а ощущение свободы."

🏍️ Берегите себя на дорогах!"""

ABOUT_TEXT = """ℹ️ <b>О ПРОЕКТЕ</b>

🏍️ <b>MotoWeather Минск</b>

📊 <b>ВОЗМОЖНОСТИ:</b>
• Текущая погода (METAR аэропорта)
• Прогноз на завтра и неделю
• Порывы ветра, видимость, точка росы
• Рассвет/закат, тренд за 3 часа
• Анализ рисков и экипировка

📡 <b>ИСТОЧНИКИ:</b>
✈️ METAR (UMMS) — основной
🌐 OpenWeatherMap — дополнительный

👨‍💻 <b>РАЗРАБОТЧИК:</b> Alexander_K8V

🏍️ Берегите себя!"""


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
        "✅ <b>Это НАСТОЯЩИЙ бот!</b>\n"
        f"🔑 Username: @{info.username}\n"
        "👨‍💻 Разработчик: Alexander_K8V\n\n"
        "Я анализирую погоду для райдеров!",
        parse_mode="HTML", reply_markup=get_main_keyboard())


@bot.message_handler(commands=['weather'])
def weather_cmd(m):
    save_user(m.chat.id)
    bot.send_message(m.chat.id, "⏳ Загружаю данные...")
    send_weather(m.chat.id)


@bot.message_handler(commands=['forecast'])
def forecast_cmd(m):
    save_user(m.chat.id)
    bot.send_message(m.chat.id, "⏳ Загружаю прогноз...")
    send_forecast(m.chat.id)


@bot.message_handler(commands=['weekly'])
def weekly_cmd(m):
    save_user(m.chat.id)
    bot.send_message(m.chat.id, "⏳ Загружаю прогноз на неделю...")
    send_weekly(m.chat.id)


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
            bot.answer_callback_query(call.id, "⏳ Загружаю...")
            send_weather(call.message.chat.id)
        elif call.data == "forecast":
            bot.answer_callback_query(call.id, "⏳ Загружаю...")
            send_forecast(call.message.chat.id)
        elif call.data == "weekly":
            bot.answer_callback_query(call.id, "⏳ Загружаю...")
            send_weekly(call.message.chat.id)
        elif call.data == "tips":
            bot.answer_callback_query(call.id, "✅ Загружено")
            bot.send_message(call.message.chat.id, TIPS_TEXT,
                             parse_mode="HTML", reply_markup=get_main_keyboard())
        elif call.data == "about":
            bot.answer_callback_query(call.id, "✅ Загружено")
            bot.send_message(call.message.chat.id, ABOUT_TEXT,
                             parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e:
        print(f"Ошибка callback: {e}")


# ============ ОТПРАВКА ============
def send_weather(chat_id):
    w = get_weather()
    if not w:
        bot.send_message(chat_id, "❌ Ошибка получения данных")
        return

    a = analyze_risks(w)
    now = get_minsk_time()
    feels = a.get("feels_like", w.get("feels_like", 0))
    light = get_light_level()

    temp_line = (
        f"🌡️ <b>Температура:</b> {w['temp']}°C (ощущается как {feels}°C, {get_temp_description(feels)})"
        if feels != w["temp"]
        else f"🌡️ <b>Температура:</b> {w['temp']}°C ({get_temp_description(feels)})"
    )

    weather_info = f"{w.get('weather_emoji') or ''} {w.get('weather_text') or ''}".strip() or "✅ Без осадков"

    dew_info = ""
    if w.get("dew_point") is not None:
        dew_info = f"\n💧 <b>Точка росы:</b> {w['dew_point']}°C"
        if w.get("humidity"):
            dew_info += f" (влажность {w['humidity']}%)"

    vis_info = f"\n🌫️ <b>Видимость:</b> {format_visibility(w['visibility'])} ({get_visibility_rating(w['visibility'])})"

    wind_line = (
        f"💨 <b>Ветер:</b> {w['wind_speed']} м/с ({get_wind_description(w['wind_speed'])}) — {get_wind_feeling(w['wind_speed'])}."
    )

    if w.get("wind_gust") and w["wind_gust"] > w["wind_speed"]:
        wind_line += (f"\n⚠️ <b>ОПАСНЫЕ ПОРЫВЫ:</b> до {w['wind_gust']} м/с!"
                      if w["wind_gust"] > 10
                      else f"\n✈️ <b>Порывы (METAR):</b> до {w['wind_gust']} м/с.")

    sun_line = ""
    if w.get("sunrise") and w.get("sunset"):
        sun_line = f"\n🌅 Рассвет: {w['sunrise']} | 🌇 Закат: {w['sunset']}"

    best_time = get_best_time(w.get("sunrise"), w.get("sunset"))

    trend = get_trend()
    trend_line = ("\n\n📈 <b>Что будет через 3 часа:</b>\n" +
                  "\n".join(f"• {t}" for t in trend)) if trend else ""

    gear = get_detailed_gear(feels, w["wind_speed"], w.get("is_night", False),
                              w.get("is_rain", False), w.get("dew_point"))
    gear_text = "\n".join(f"• {g}" for g in gear)

    msg = f"""{a['color']} <b>MotoWeather Минск</b> — <b>сейчас {now}</b>

{light}
{temp_line}
{wind_line}
{w.get('cloud_emoji', '')} <b>Облачность:</b> {w.get('cloud_text', '—')}
🌧️ <b>Осадки:</b> {weather_info}{dew_info}{vis_info}{sun_line}

📡 <b>Источник:</b> {w['source']}
ℹ️ <i>Данные с метеостанции аэропорта Минск. В городе может отличаться.</i>

<b>ВЕРДИКТ:</b> {a['verdict']}
📊 <b>Уровень риска:</b> {a['score']}/10
"""

    if a["risks"]:
        msg += "\n<b>⚠️ Факторы риска:</b>\n" + "\n".join(f"• {r}" for r in a["risks"])
    else:
        msg += "\n✅ <b>Нет факторов риска</b>"

    if a["recommendations"]:
        msg += "\n\n<b>💡 Рекомендации:</b>\n" + "\n".join(f"• {r}" for r in a["recommendations"])

    msg += f"\n\n<b>🛡️ Экипировка:</b>\n{gear_text}{trend_line}\n\n<b>{best_time}</b>"

    bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=get_after_weather_keyboard())


def send_forecast(chat_id):
    f = get_forecast_tomorrow()
    if not f:
        bot.send_message(chat_id, "❌ Ошибка прогноза")
        return

    a = analyze_risks(f, is_forecast=True)
    rain_info = f" 🌧️{f['rain_total']:.1f} мм" if f.get("rain_total", 0) > 0 else ""
    feels = f["temp_avg"]

    msg = f"""{a['color']} <b>MotoWeather Минск</b> — <b>завтра {f['date']}</b>

🌡️ <b>Средняя температура:</b> {feels}°C (мин {f['temp_min']}°C / макс {f['temp_max']}°C)
💨 <b>Ветер:</b> {f['wind_speed']} м/с (порывы до {f['wind_gust']} м/с)
{f['condition']}{rain_info}

<b>ВЕРДИКТ:</b> {a['verdict']}
📊 <b>Уровень риска:</b> {a['score']}/10
"""

    if a["risks"]:
        msg += "\n<b>⚠️ Факторы риска:</b>\n" + "\n".join(f"• {r}" for r in a["risks"])

    if a["recommendations"]:
        msg += "\n\n<b>💡 Рекомендации:</b>\n" + "\n".join(f"• {r}" for r in a["recommendations"])

    gear = get_detailed_gear(feels, f["wind_speed"], False, f.get("is_rain", False), None)
    msg += "\n\n<b>🛡️ Экипировка:</b>\n" + "\n".join(f"• {g}" for g in gear)
    msg += "\n\n📡 <b>Источник:</b> OpenWeatherMap"

    bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=get_after_weather_keyboard())


def send_weekly(chat_id):
    w = get_weekly_forecast()
    if not w:
        bot.send_message(chat_id, "❌ Ошибка прогноза")
        return

    msg = "📆 <b>ПРОГНОЗ НА НЕДЕЛЮ (Минск)</b>\n\n"

    for d in w:
        emoji = "🔴" if d["wind_speed"] > 14 or d["is_thunder"] else \
                "🟡" if d["wind_speed"] > 10 or d["rain_total"] > 5 else "🟢"
        rain = f" 🌧️{d['rain_total']:.1f}мм" if d["rain_total"] > 0 else ""
        msg += f"{emoji} <b>{d['weekday']}</b> {d['date']}: {d['condition']} {d['temp_min']}°...{d['temp_max']}° | 💨 {d['wind_speed']} м/с{rain}\n"

    msg += "\n<b>📊 АНАЛИЗ НЕДЕЛИ:</b>\n\n"

    rainy, windy = [], []
    best, worst = None, None
    best_s, worst_s = float("inf"), -float("inf")

    for d in w:
        issues = []
        if d["rain_total"] > 0:
            issues.append(f"дождь {d['rain_total']:.1f}мм")
            rainy.append(d["weekday"])
        if d["wind_speed"] > 10:
            issues.append(f"ветер {d['wind_speed']} м/с")
            windy.append(d["weekday"])
        if d["temp_max"] > 30:
            issues.append("жарко")
        if d["temp_min"] < 0:
            issues.append("мороз")

        score = d["wind_speed"] + d["rain_total"] * 3
        if score < best_s:
            best_s, best = score, d
        if score > worst_s:
            worst_s, worst = score, d

        if not issues:
            msg += f"☀️ <b>{d['weekday']}</b>: отличный день\n"
        elif len(issues) == 1:
            msg += f"☀️ <b>{d['weekday']}</b>: {issues[0]}\n"
        else:
            msg += f"⚠️ <b>{d['weekday']}</b>: {', '.join(issues)}\n"

    if best and worst:
        msg += f"\n<b>🏍️ РЕКОМЕНДАЦИИ:</b>\n\n"
        msg += f"✅ <b>Лучший день:</b> {best['weekday']} ({best['temp_min']}°...{best['temp_max']}°)\n"
        msg += f"⚠️ <b>Худший день:</b> {worst['weekday']}\n"

        msg += "\n💡 <b>Общие советы:</b>\n"
        if rainy:
            msg += f"• ☔ Дождевик: {', '.join(rainy)}\n"
        if windy:
            msg += f"• 💨 Держите руль: {', '.join(windy)}\n"
        if best:
            msg += f"• ⭐ Планируйте: {best['weekday']}\n"

    msg += "\n📡 <b>Источник:</b> OpenWeatherMap\n🏍️ <b>Берегите себя!</b>"

    bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=get_after_weather_keyboard())


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

    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling()
