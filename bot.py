import json
import os
import random
import threading
import time
from datetime import datetime

import telebot
from flask import Flask, jsonify

from config import (
    BOT_TOKEN, MY_BOT_USERNAME,
    USERS_FILE, SUBSCRIBERS_FILE, ADMIN_ID, MINSK_TZ,
)
from weather import (
    get_weather, get_forecast_tomorrow,
    get_short_forecast, get_daylight_info,
)
from analyzer import (
    analyze_risks, get_short_verdict, get_rider_verdict,
    get_gear_short, get_tech_check, get_tip,
)
from keyboards import (
    get_main_keyboard, get_after_weather_keyboard,
    get_about_keyboard, get_subscribe_keyboard
)


# ============ ПРОВЕРКА КОНФИГА ============
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден!", flush=True)
    exit(1)

print("✅ METAR + прогнозы (Open-Meteo → wttr.in fallback)", flush=True)


# ============ ИНИЦИАЛИЗАЦИЯ ============
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)


# ============ НЕВИДИМЫЕ ПРОБЕЛЫ ============
Z = "\u200b"
DEV_USERNAME = f"@{Z}Aleksandr_K8V"
WTTR_NAME = f"wttr{Z}.in"


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


# ============ ПОДПИСЧИКИ ============
def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_subscriber(user_id):
    subs = load_subscribers()
    if user_id not in subs:
        subs.append(user_id)
        try:
            with open(SUBSCRIBERS_FILE, "w") as f:
                json.dump(subs, f)
        except Exception as e:
            print(f"⚠️ Не удалось сохранить подписчика: {e}", flush=True)


def remove_subscriber(user_id):
    subs = load_subscribers()
    if user_id in subs:
        subs.remove(user_id)
        try:
            with open(SUBSCRIBERS_FILE, "w") as f:
                json.dump(subs, f)
        except Exception as e:
            print(f"⚠️ Не удалось удалить подписчика: {e}", flush=True)


def is_subscribed(user_id):
    return user_id in load_subscribers()


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
ABOUT_TEXT = f"""ℹ️ <b>MotoWeather Минск</b>

📡 <b>Источник данных:</b>
✈️ METAR аэропорта Минск — текущая погода
🌐 Open-Meteo — прогнозы (основной)
🌐 {WTTR_NAME} — прогнозы (резервный)

Бот для райдеров. Проверяю аэропорт Минск — говорю: ехать или нет.

<b>Показываю:</b>
• Вердикт — ехать или нет
• Экипировку и подготовку
• Прогноз на 3 часа и следующий период

<b>Подписка на утро:</b>
Жми «🌅 Подписка на утро» — буду присылать прогноз в 7:00.

<i>━━━ ПРИМЕР ПЛОХОЙ ПОГОДЫ ━━━

🌡️ +3°C · 💨 12 м/с (сильный ветер) / порывы 18
🌧️ Дождь · туман
💧 Влажность 96% · 👁️ 800 м
🌇 Темно (закат 19:32)

🔴 НЕ САДИСЬ ЗА РУЛЬ — ОПАСНО

🎯 ЧТО НА ДОРОГЕ
🌪️ Сильный ветер (порывы до 18 м/с)
🌧️ Дождь (дорога скользкая)
🌫️ Очень плохая видимость (800 м)

🎽 НА СЕБЯ
🧥 Тёплая подкладка + подогрев ручек
☔ Дождевик / мембрана
💡 Дополнительный свет (обязательно)

🔧 ПЕРЕД ВЫЕЗДОМ
✅ Давление в шинах — на холодную
✅ Визор — антизапотеватель обязателен
✅ Противотуманки — включить

💡 Туман на подходе — визор вниз, дистанцию больше

━━━ КОНЕЦ ПРИМЕРА ━━━</i>

<b>👨‍💻 Разработчик:</b> {DEV_USERNAME}

🏍️ <b>Жми «Сейчас» — увидишь сегодняшний день.</b>"""


SUBSCRIBE_TEXT = """🌅 <b>Подписка на утренний прогноз</b>

Каждый день в <b>7:00</b> буду присылать:
• Погоду в Минске
• Вердикт — ехать или нет
• Экипировку и подготовку
• Прогноз на день и завтра
• Цитату для настроения

<b>Подписаться?</b>"""

SUBSCRIBE_CONFIRMED = """✅ <b>Подписка активирована!</b>

Каждый день в <b>7:00</b> буду присылать утренний прогноз.

Отписаться — /unsubscribe"""

SUBSCRIBE_CANCELED = """❌ <b>Подписка отменена</b>

Если передумаешь — жми «🌅 Подписка на утро»."""

UNSUBSCRIBED = """❌ <b>Ты отписан от утренней рассылки</b>

Если снова захочешь — жми «🌅 Подписка на утро»."""

ALREADY_SUBSCRIBED = """ℹ️ <b>Ты уже подписан</b> на утренний прогноз.

Отписаться — /unsubscribe"""


# ============ ХЕЛПЕР ============
def edit_or_send(chat_id, message_id, text, reply_markup):
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
            print(f"⚠️ edit_or_send fallback failed: {e2}", flush=True)
        return False


# ============ УТРЕННЯЯ РАССЫЛКА ============
_last_morning_sent = {"date": None}


def morning_broadcast_loop():
    global _last_morning_sent
    print("⏰ Поток утренней рассылки запущен", flush=True)

    while True:
        try:
            now = datetime.now(MINSK_TZ)
            today_str = now.strftime("%Y-%m-%d")

            if now.hour == 7 and now.minute < 5 and _last_morning_sent["date"] != today_str:
                print(f"🌅 Начинаю утреннюю рассылку ({today_str})", flush=True)

                subs = load_subscribers()
                if not subs:
                    print("⚠️ Нет подписчиков", flush=True)
                    _last_morning_sent["date"] = today_str
                    continue

                w = get_weather()
                if not w:
                    print("❌ Не удалось получить погоду", flush=True)
                    _last_morning_sent["date"] = today_str
                    continue

                a = analyze_risks(w)
                f = get_forecast_tomorrow()
                short = get_short_forecast()

                next_period = short.get("next_period", "нет данных")
                next_period_label = short.get("next_period_label", "ДЕНЬ")
                forecast_src = short.get("source", "none")

                verdict = get_rider_verdict(a["score"])
                tip = get_tip(
                    a.get("feels_like", w.get("temp", 0)),
                    w.get("humidity"), w.get("is_rain", False),
                    False,
                    w.get("wind_speed"), w.get("is_thunder", False),
                    w.get("visibility")
                )

                wind_desc = get_wind_description(w["wind_speed"])
                weather_info = f"{w.get('weather_emoji') or ''} {w.get('weather_text') or ''}".strip() or "без осадков"
                humidity_str = f"{w['humidity']}%" if w.get("humidity") else "—"
                vis_str = format_visibility(w["visibility"])

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

                source_line = "✈️ METAR + Open-Meteo"
                if forecast_src == "wttr.in":
                    source_line = f"✈️ METAR + {WTTR_NAME}"

                quote = get_random_quote()

                risk_text = "\n".join(a['risks'][:3]) if a['risks'] else "✅ Дорога чистая"
                gear_text = "\n".join(get_gear_short(
                    a.get('feels_like', w['temp']), w.get('is_rain', False),
                    False, w['wind_speed']
                ))
                tech_text = "\n".join(
                    "✅ " + t for t in get_tech_check(
                        a.get('feels_like', w['temp']), False,
                        w.get('is_rain', False), w.get('humidity'), w.get('dew_point')
                    )
                )

                msg = f"""🌅 <b>Доброе утро, райдер!</b>
📅 {now.strftime('%d.%m')} · {now.strftime('%H:%M')} · Минск
{source_line}

🌡️ {w['temp']}°C · 💨 {w['wind_speed']} м/с ({wind_desc})
{w.get('cloud_emoji', '')} {w.get('cloud_text', '—')} · {weather_info.lower()}
💧 Влажность {humidity_str} · 👁️ {vis_str}

<b>{verdict}</b>

<b>🎯 ЧТО НА ДОРОГЕ</b>
{risk_text}

<b>🎽 НА СЕБЯ</b>
{gear_text}

<b>🔧 ПЕРЕД ВЫЕЗДОМ</b>
{tech_text}

🌤 <b>{next_period_label} (средняя)</b>
{next_period}

📅 <b>ЗАВТРА</b>
{tomorrow_line}

💡 <i>{tip}</i>

💬 <i>{quote}</i>

🏍️ <b>Ровной дороги!</b>"""

                sent = 0
                failed = []
                for uid in subs:
                    try:
                        bot.send_message(uid, msg, parse_mode="HTML",
                                         reply_markup=get_after_weather_keyboard())
                        sent += 1
                        time.sleep(0.05)
                    except Exception as e:
                        print(f"⚠️ Не отправил {uid}: {e}", flush=True)
                        failed.append(uid)

                print(f"✅ Утренняя рассылка: {sent} отправлено, {len(failed)} ошибок", flush=True)

                for uid in failed:
                    remove_subscriber(uid)

                _last_morning_sent["date"] = today_str

        except Exception as e:
            print(f"❌ Ошибка в рассылке: {e}", flush=True)

        time.sleep(60)


# ============ КОМАНДЫ ============
@bot.message_handler(commands=['start'])
def start(message):
    try:
        print(f"📥 /start от {message.chat.id}", flush=True)
        save_user(message.chat.id)
        info = bot.get_me()

        if info.username != MY_BOT_USERNAME:
            bot.send_message(
                message.chat.id,
                f"⚠️ <b>Это поддельный бот!</b>\nНастоящий: @{MY_BOT_USERNAME}",
                parse_mode="HTML"
            )
            return

        bot.send_message(
            message.chat.id,
            "🏍️ <b>MotoWeather Минск</b>\n\n"
            "Погода для тех, кто на двух колёсах.\n"
            "Проверяю аэропорт Минск и говорю прямо: ехать или нет.\n\n"
            "<b>Жми «Сейчас» — и вперёд.</b>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        print(f"❌ /start упал: {e}", flush=True)


@bot.message_handler(commands=['weather'])
def weather_cmd(m):
    try:
        save_user(m.chat.id)
        bot.send_message(m.chat.id, "⏳ Смотрю на небо...")
        send_weather(m.chat.id)
    except Exception as e:
        print(f"❌ weather_cmd упал: {e}", flush=True)


@bot.message_handler(commands=['about'])
def about_cmd(m):
    try:
        save_user(m.chat.id)
        bot.send_message(
            m.chat.id,
            ABOUT_TEXT,
            parse_mode="HTML",
            reply_markup=get_about_keyboard()
        )
    except Exception as e:
        print(f"❌ /about упал: {e}", flush=True)


@bot.message_handler(commands=['subscribe'])
def subscribe_cmd(m):
    try:
        save_user(m.chat.id)
        if is_subscribed(m.chat.id):
            bot.send_message(m.chat.id, ALREADY_SUBSCRIBED,
                             parse_mode="HTML",
                             reply_markup=get_main_keyboard())
            return
        bot.send_message(
            m.chat.id,
            SUBSCRIBE_TEXT,
            parse_mode="HTML",
            reply_markup=get_subscribe_keyboard()
        )
    except Exception as e:
        print(f"❌ /subscribe упал: {e}", flush=True)


@bot.message_handler(commands=['unsubscribe'])
def unsubscribe_cmd(m):
    try:
        save_user(m.chat.id)
        remove_subscriber(m.chat.id)
        bot.send_message(m.chat.id, UNSUBSCRIBED, parse_mode="HTML",
                         reply_markup=get_main_keyboard())
    except Exception as e:
        print(f"❌ /unsubscribe упал: {e}", flush=True)


@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    if m.chat.id != ADMIN_ID:
        bot.reply_to(m, "❌ Нет прав.")
        return
    bot.reply_to(
        m,
        f"📊 <b>Статистика</b>\n"
        f"👥 Пользователей: {get_users_count()}\n"
        f"🌅 Подписчиков: {len(load_subscribers())}\n"
        f"📅 {datetime.now(MINSK_TZ).strftime('%d.%m.%Y %H:%M')}",
        parse_mode="HTML"
    )


# ============ CALLBACK ============
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    try:
        print(f"📩 Callback: {call.data} от {call.message.chat.id}", flush=True)
        try:
            save_user(call.message.chat.id)
        except Exception as e:
            print(f"⚠️ save_user failed: {e}", flush=True)

        chat_id = call.message.chat.id
        msg_id = call.message.message_id

        if call.data in ("weather", "update"):
            msg_text = "⏳ Смотрю на небо..." if call.data == "weather" else "⏳ Обновляю..."
            bot.answer_callback_query(call.id, msg_text, cache_time=3)
            send_weather(chat_id, edit_message=call.message)

        elif call.data == "about":
            bot.answer_callback_query(call.id, "✅ Открываю", cache_time=3)
            edit_or_send(chat_id, msg_id, ABOUT_TEXT, get_about_keyboard())

        elif call.data == "subscribe":
            if is_subscribed(chat_id):
                bot.answer_callback_query(call.id, "ℹ️ Уже подписан", cache_time=3)
                edit_or_send(chat_id, msg_id, ALREADY_SUBSCRIBED, get_main_keyboard())
            else:
                bot.answer_callback_query(call.id, "🌅 Подписка", cache_time=3)
                edit_or_send(chat_id, msg_id, SUBSCRIBE_TEXT, get_subscribe_keyboard())

        elif call.data == "subscribe_confirm":
            save_subscriber(chat_id)
            bot.answer_callback_query(call.id, "✅ Подписка активирована", cache_time=3)
            edit_or_send(chat_id, msg_id, SUBSCRIBE_CONFIRMED, get_main_keyboard())

        elif call.data == "subscribe_cancel":
            bot.answer_callback_query(call.id, "❌ Отменено", cache_time=3)
            edit_or_send(chat_id, msg_id, SUBSCRIBE_CANCELED, get_main_keyboard())

        else:
            print(f"⚠️ Неизвестный callback: {call.data}", flush=True)
            bot.answer_callback_query(call.id, "❓ Неизвестная кнопка", cache_time=3)

    except Exception as e:
        print(f"❌ Ошибка callback: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()


# ============ ОТПРАВКА: ПОГОДА ============
def send_weather(chat_id, edit_message=None):
    try:
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

        wind_part = f"{w['wind_speed']} м/с ({wind_desc})"
        if w.get("wind_gust") and w["wind_gust"] > w["wind_speed"] + 3:
            wind_part += f" / порывы {w['wind_gust']}"

        weather_info = f"{w.get('weather_emoji') or ''} {w.get('weather_text') or ''}".strip()
        if not weather_info:
            weather_info = "без осадков"

        humidity_str = f"{w['humidity']}%" if w.get("humidity") else "—"
        vis_str = format_visibility(w["visibility"])

        if w.get("sunrise") and w.get("sunset"):
            light_info = get_daylight_info(w.get("sunrise"), w.get("sunset"))
        else:
            light_info = ""

        risk_factors = a["risks"][:3]
        risk_block = "\n".join(risk_factors) if risk_factors else "✅ Дорога чистая"

        gear = get_gear_short(feels, w.get("is_rain", False), w.get("is_night", False), w["wind_speed"])
        gear_block = "\n".join(gear)

        tech = get_tech_check(feels, w.get("is_night", False), w.get("is_rain", False),
                              w.get("humidity"), w.get("dew_point"))
        tech_block = "\n".join(f"✅ {t}" for t in tech)

        short = get_short_forecast()
        next_hour = short.get("next_hour", "нет данных")
        next_period = short.get("next_period", "нет данных")
        next_period_label = short.get("next_period_label", "—")
        forecast_src = short.get("source", "none")
        forecast_now_temp = short.get("current_temp")
        show_next_hour = short.get("show_next_hour", True)

        if next_hour != "нет данных":
            try:
                fc_temp = int(next_hour.split("°C")[0])
                base_temp = forecast_now_temp if forecast_now_temp is not None else w["temp"]
                delta = fc_temp - base_temp
                if delta >= 2:
                    next_hour = next_hour.replace(f"{fc_temp}°C", f"{fc_temp}°C (+{delta}°C)", 1)
                elif delta <= -2:
                    next_hour = next_hour.replace(f"{fc_temp}°C", f"{fc_temp}°C ({delta}°C)", 1)
            except (ValueError, IndexError):
                pass

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

        tip = get_tip(
            feels, w.get("humidity"), w.get("is_rain", False), w.get("is_night", False),
            w["wind_speed"], w.get("is_thunder", False), w.get("visibility")
        )

        rider_verdict = get_rider_verdict(a["score"])

        weather_block = f"""🌡️ {w['temp']}°C · 💨 {wind_part}
{w.get('cloud_emoji', '')} {w.get('cloud_text', '—')} · {weather_info.lower()}
💧 Влажность {humidity_str} · 👁️ {vis_str}"""
        if light_info:
            weather_block += f"\n{light_info}"

        if forecast_src == "Open-Meteo":
            source_line = "✈️ METAR + Open-Meteo"
        elif forecast_src == "wttr.in":
            source_line = f"✈️ METAR + {WTTR_NAME}"
        else:
            source_line = "✈️ METAR (аэропорт Минск)"

        next_hour_block = ""
        if show_next_hour and next_hour != "нет данных":
            next_hour_block = f"""
⏱️ <b>ЧЕРЕЗ 3 ЧАСА</b>
{next_hour}
"""

        msg = f"""<b>MotoWeather</b>
📅 {date} · {now} · Минск
{source_line}

{weather_block}

<b>{rider_verdict}</b>

<b>🎯 ЧТО НА ДОРОГЕ</b>
{risk_block}

<b>🎽 НА СЕБЯ</b>
{gear_block}

<b>🔧 ПЕРЕД ВЫЕЗДОМ</b>
{tech_block}
{next_hour_block}
🌤 <b>{next_period_label} (средняя)</b>
{next_period}

📅 <b>ЗАВТРА</b>
{tomorrow_line}

💡 <i>{tip}</i>

🏍️ <b>Ровной дороги!</b>"""

        if edit_message:
            edit_or_send(chat_id, edit_message.message_id, msg, get_after_weather_keyboard())
        else:
            bot.send_message(chat_id, msg, parse_mode="HTML",
                             reply_markup=get_after_weather_keyboard())

    except Exception as e:
        print(f"❌ ОШИБКА в send_weather: {type(e).__name__}: {e}", flush=True)
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
        "users": get_users_count(),
        "subscribers": len(load_subscribers()),
        "time": datetime.now(MINSK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    }), 200


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# ============ ЗАПУСК ============
if __name__ == "__main__":
    print("🏍️ MotoWeather Бот запущен!", flush=True)
    print("✅ METAR + прогнозы (Open-Meteo → wttr.in fallback)", flush=True)
    print("📡 Бот готов к работе", flush=True)

    try:
        bot.remove_webhook()
        print("✅ Webhook сброшен", flush=True)
    except Exception as e:
        print(f"⚠️ remove_webhook: {e}", flush=True)

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=morning_broadcast_loop, daemon=True).start()

    print("🔄 Запускаю polling...", flush=True)
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            err_str = str(e)
            if "409" in err_str:
                print("⚠️ 409 Conflict. Жду 20 сек...", flush=True)
                time.sleep(20)
            else:
                print(f"⚠️ Polling упал: {e}", flush=True)
                time.sleep(10)
