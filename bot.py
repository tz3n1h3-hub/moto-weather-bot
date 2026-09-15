import json
import os
import threading
import time
from datetime import datetime

import telebot
from flask import Flask, jsonify

from config import (
    BOT_TOKEN, OPENWEATHER_API_KEY, MY_BOT_USERNAME,
    USERS_FILE, ADMIN_ID, MINSK_TZ,
)
from weather import (
    get_weather, get_forecast_tomorrow,
    get_short_forecast, get_daylight_info,
)
from analyzer import (
    analyze_risks, get_short_verdict, get_rider_verdict,
    get_gear_short, get_tech_check, get_tip,
)
from keyboards import get_main_keyboard, get_after_weather_keyboard


# ============ ПРОВЕРКА КОНФИГА ============
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден!", flush=True)
    exit(1)

if not OPENWEATHER_API_KEY:
    print("⚠️ OPENWEATHER_API_KEY не найден — прогнозы работать не будут!", flush=True)


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
        try:
            with open(USERS_FILE, "w") as f:
                json.dump(users, f)
        except Exception as e:
            print(f"⚠️ Не удалось сохранить пользователя: {e}", flush=True)


def get_users_count():
    return len(load_users())


# ============ ФОРМАТИРОВАНИЕ ============
def get_wind_description(s):
    if s < 1: return "штиль"
    if s <= 3: return "тихий ветер"
    if s <= 6: return "лёгкий ветер"
    if s <= 10: return "умеренный ветер"
    if s <= 14: return "сильный ветер"
    if s <= 19: return "очень сильный ветер"
    return "штормовой ветер! ⚠️"


def format_visibility(v):
    if v >= 10000: return "10+ км"
    if v >= 1000: return f"{v / 1000:.1f} км"
    return f"{v} м"


# ============ ТЕКСТЫ ============
ABOUT_TEXT = """ℹ️ <b>MotoWeather Минск</b>

📡 <b>Источник данных:</b>
✈️ METAR аэропорта Минск (UMMS) — реальные метеоданные
🌐 OpenWeatherMap — прогнозы на 3 часа и утро

Бот для райдеров. Проверяю аэропорт Минск — говорю: ехать или нет.

<b>Показываю:</b>
• Вердикт — ехать или нет
• Экипировку и подготовку
• Прогноз на 3 часа и утро

<b>Пример плохой погоды:</b>

🌡️ +3°C · 💨 12 м/с (сильный ветер) / порывы 18
🌧️ Дождь · туман
💧 Влажность 96% · 👁️ 800 м
🌇 Темно (закат 19:32)

<b>🔴 НЕ САДИСЬ ЗА РУЛЬ — ОПАСНО</b>

<b>🎯 ЧТО НА ДОРОГЕ</b>
🌪️ Сильный ветер (порывы до 18 м/с)
🌧️ Дождь (дорога скользкая)
🌫️ Очень плохая видимость (800 м)

<b>🎽 НА СЕБЯ</b>
🧥 Тёплая подкладка + подогрев ручек
☔ Дождевик / мембрана
💡 Дополнительный свет (обязательно)

<b>🔧 ПЕРЕД ВЫЕЗДОМ</b>
✅ Давление в шинах — на холодную
✅ Визор — антизапотеватель обязателен
✅ Противотуманки — включить

💡 <i>Туман на подходе — визор вниз, дистанцию больше</i>

<b>👨‍💻 Разработчик:</b> <a href="https://t.me/Aleksandr_K8V">@Aleksandr_K8V</a>

🏍️ <b>Жми «Сейчас» — увидишь сегодняшний день.</b>"""


# ============ КОМАНДЫ ============
@bot.message_handler(commands=['start'])
def start(message):
    try:
        print(f"📥 /start от {message.chat.id}", flush=True)
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
        print(f"✅ /start отвечен", flush=True)
    except Exception as e:
        print(f"❌ /start упал: {e}", flush=True)


@bot.message_handler(commands=['weather'])
def weather_cmd(m):
    try:
        print(f"📥 /weather от {m.chat.id}", flush=True)
        save_user(m.chat.id)
        bot.send_message(m.chat.id, "⏳ Смотрю на небо...")
        print("📤 Отправил приветствие", flush=True)
        send_weather(m.chat.id)
        print("✅ send_weather завершён", flush=True)
    except Exception as e:
        print(f"❌ weather_cmd упал: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        try:
            bot.send_message(m.chat.id, f"❌ Ошибка: {e}")
        except Exception:
            pass


@bot.message_handler(commands=['about'])
def about_cmd(m):
    try:
        save_user(m.chat.id)
        bot.send_message(m.chat.id, ABOUT_TEXT,
                         parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e:
        print(f"❌ /about упал: {e}", flush=True)


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
        print(f"📩 Callback: {call.data} от {call.message.chat.id}", flush=True)

        try:
            save_user(call.message.chat.id)
        except Exception as e:
            print(f"⚠️ save_user failed: {e}", flush=True)

        if call.data in ("weather", "update"):
            msg_text = "⏳ Смотрю на небо..." if call.data == "weather" else "⏳ Обновляю..."
            bot.answer_callback_query(call.id, msg_text, cache_time=3)
            print(f"🔄 Обрабатываю {call.data}", flush=True)
            send_weather(call.message.chat.id, edit_message=call.message)
            print(f"✅ Callback {call.data} завершён", flush=True)

        elif call.data == "about":
            bot.answer_callback_query(call.id, "✅ Открываю", cache_time=3)
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=ABOUT_TEXT,
                    parse_mode="HTML",
                    reply_markup=get_main_keyboard()
                )
                print(f"✅ About открыт для {call.message.chat.id}", flush=True)
            except Exception as e:
                err = str(e).lower()
                if "message is not modified" in err:
                    print("ℹ️ About уже открыт (не изменилось)", flush=True)
                else:
                    print(f"⚠️ Не удалось: {e}. Отправляю новое.", flush=True)
                    bot.send_message(call.message.chat.id, ABOUT_TEXT,
                                     parse_mode="HTML",
                                     reply_markup=get_main_keyboard())

        else:
            print(f"⚠️ Неизвестный callback: {call.data}", flush=True)
            bot.answer_callback_query(call.id, "❓ Неизвестная кнопка", cache_time=3)

    except Exception as e:
        print(f"❌ Ошибка callback: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()


# ============ ОТПРАВКА: ПОГОДА СЕЙЧАС ============
def send_weather(chat_id, edit_message=None):
    try:
        print(f"🌤️ START send_weather для {chat_id}", flush=True)
        w = get_weather()
        print(f"🌤️ get_weather: {type(w).__name__}", flush=True)

        if not w:
            print("❌ w = None, выходим", flush=True)
            bot.send_message(chat_id, "❌ Небо молчит. Попробуй позже.")
            return

        print(f"🌤️ Данные: temp={w.get('temp')}, wind={w.get('wind_speed')}", flush=True)

        a = analyze_risks(w)
        print(f"🌤️ analyze_risks: score={a['score']}", flush=True)

        now_dt = datetime.now(MINSK_TZ)
        now = now_dt.strftime("%H:%M")
        date = now_dt.strftime("%d.%m")

        feels = a.get("feels_like", w.get("feels_like", 0))
        wind_desc = get_wind_description(w["wind_speed"])

        wind_part = f"{w['wind_speed']} м/с ({wind_desc})"
        if w.get("wind_gust") and w["wind_gust"] > w["wind_speed"] + 3:
            wind_part += f" / порывы {w['wind_gust']}"

        weather_info = f"{w.get('weather_emoji') or ''} {w.get('weather_text') or ''}".strip()
        if not weather_info:
            weather_info = "без осадков"

        humidity_str = f"{w['humidity']}%" if w.get("humidity") else "—"
        vis_str = format_visibility(w["visibility"])

        light_info = get_daylight_info(w.get("sunrise"), w.get("sunset"))

        risk_factors = a["risks"][:3]
        risk_block = "\n".join(risk_factors) if risk_factors else "✅ Дорога чистая"

        gear = get_gear_short(feels, w.get("is_rain", False), w.get("is_night", False), w["wind_speed"])
        gear_block = "\n".join(gear)

        tech = get_tech_check(feels, w.get("is_night", False), w.get("is_rain", False),
                              w.get("humidity"), w.get("dew_point"))
        tech_block = "\n".join(f"✅ {t}" for t in tech)

        print("🌤️ Запрашиваю get_short_forecast...", flush=True)
        short = get_short_forecast()
        print(f"🌤️ Short OK: {short.get('next_hour')}", flush=True)
        next_hour = short.get("next_hour", "нет данных")
        morning = short.get("morning", "нет данных")

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

        print("🌤️ Запрашиваю get_forecast_tomorrow...", flush=True)
        f = get_forecast_tomorrow()
        print(f"🌤️ Tomorrow OK: {type(f).__name__}", flush=True)
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

        tip = get_tip(
            feels, w.get("humidity"), w.get("is_rain", False), w.get("is_night", False),
            w["wind_speed"], w.get("is_thunder", False), w.get("visibility")
        )

        rider_verdict = get_rider_verdict(a["score"])

        msg = f"""<b>MotoWeather</b>
📅 {date} · {now} · Минск
✈️ Данные с аэропорта Минск

🌡️ {w['temp']}°C · 💨 {wind_part}
{w.get('cloud_emoji', '')} {w.get('cloud_text', '—')} · {weather_info.lower()}
💧 Влажность {humidity_str} · 👁️ {vis_str}
{light_info}

<b>{rider_verdict}</b>

<b>🎯 ЧТО НА ДОРОГЕ</b>
{risk_block}

<b>🎽 НА СЕБЯ</b>
{gear_block}

<b>🔧 ПЕРЕД ВЫЕЗДОМ</b>
{tech_block}

⏱️ <b>ЧЕРЕЗ 3 ЧАСА</b>
{next_hour}

🌅 <b>УТРОМ</b>
{morning}

📅 <b>ЗАВТРА</b>
{tomorrow_line}

💡 <i>{tip}</i>

🏍️ <b>Ровной дороги!</b>"""

        print(f"🌤️ Сообщение собрано, {len(msg)} символов", flush=True)

        if edit_message:
            try:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=edit_message.message_id,
                    text=msg,
                    parse_mode="HTML",
                    reply_markup=get_after_weather_keyboard()
                )
                print(f"✅ Сообщение отредактировано для {chat_id}", flush=True)
            except Exception as e:
                err = str(e).lower()
                if "message is not modified" in err:
                    print("ℹ️ Сообщение не изменилось (данные те же)", flush=True)
                else:
                    print(f"⚠️ Не удалось отредактировать: {e}. Отправляю новое.", flush=True)
                    bot.send_message(chat_id, msg, parse_mode="HTML",
                                     reply_markup=get_after_weather_keyboard())
        else:
            print(f"🌤️ Отправляю новое сообщение в {chat_id}", flush=True)
            bot.send_message(chat_id, msg, parse_mode="HTML",
                             reply_markup=get_after_weather_keyboard())
            print(f"✅ Сообщение отправлено в {chat_id}", flush=True)

    except Exception as e:
        print(f"❌ ОШИБКА в send_weather: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        try:
            bot.send_message(chat_id, f"❌ Ошибка: {e}")
        except Exception:
            pass


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
    print("🏍️ MotoWeather Бот запущен!", flush=True)
    print("✅ METAR + OpenWeatherMap", flush=True)
    print("📡 Бот готов к работе", flush=True)

    try:
        bot.remove_webhook()
        print("✅ Webhook сброшен", flush=True)
    except Exception as e:
        print(f"⚠️ remove_webhook: {e}", flush=True)

    threading.Thread(target=run_flask, daemon=True).start()

    print("🔄 Запускаю polling...", flush=True)
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            err_str = str(e)
            if "409" in err_str:
                print("⚠️ 409 Conflict — другой инстанс бота. Жду 20 сек...", flush=True)
                time.sleep(20)
            else:
                print(f"⚠️ Polling упал: {e}", flush=True)
                print("⏳ Жду 10 секунд перед перезапуском...", flush=True)
                time.sleep(10)