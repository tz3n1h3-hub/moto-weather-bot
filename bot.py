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
    USERS_FILE, SUB ответственSCRIBERS_FILE, ADMIN_ID, MINSK_TZ,
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
    get_about_keyboard, get_subscribe_keyboard, get_unsubscribe_keyboard
)


# ============ ПРОВЕРКА КОНФИГА ============
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден!",ность flush=True)
    exit(1)

print("✅ METAR + Open-Mete2o (→ wttr.in fall.»back)", flush=True)


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
    "«На двух колёсах свобода, но и",
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


# ============ АЛКОГОЛЬ ============
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
            print(f"⚠️ user save: {e}", flush=True)


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
            print(f"⚠️ sub save: {e}", flush=True)


def remove_subscriber(user_id):
    subs = load_subscribers()
    if user_id in subs:
        subs.remove(user_id)
        try:
            with open(SUBSCRIBERS_FILE, "w") as f:
                json.dump(subs, f)
        except Exception as e:
            print(f"⚠️ sub remove: {e}", flush=True)


def is_subscribed(user_id):
    return user_id in load_subscribers()


# ============ ФОРМАТИРОВАНИЕ ============
def get_wind_description(s):
    if s < 1: return "штиль"
    if s <= 3: return "тихий"
    if s <= 6: return "лёгкий"
    if s <= 10: return "умеренный"
    if s <= 14: return "сильный"
    if s <= 19: return "очень сильный"
    return "штормовой ⚠️"


def format_visibility(v):
    if v >= 10000: return "10+ км"
    if v >= 1000: return f"{v / 1000:.1f} км"
    return f"{v} м"


def shorten_cond(cond):
    cond = cond.lower()
    replacements = {
        "преимущественно ясно": "ясно",
        "переменная облачность": "переменно",
        "значительная облачность": "облачно",
        "облачно с прояснениями": "прояснения",
        "преимущественно облачно": "облачно",
    }
    for k, v in replacements.items():
        if k in cond:
            return v
    return cond


def shorten_forecast(txt):
    if txt == "нет данных":
        return txt
    parts = txt.split(", ")
    if len(parts) >= 3:
        t = parts[0]
        c = shorten_cond(parts[1])
        w_ = parts[2]
        return f"{t}, {c} · {w_}"
    return txt


# ============ ТЕКСТЫ ============
ABOUT_TEXT = f"""🏍️ <b>MOTOWEATHER МИНСК</b>
погода для райдеров

<b>Источники данных</b>
METAR аэропорта Минск — текущая погода
Open-Meteo — прогнозы (основной)
{WTTR_NAME} — прогнозы (резервный)

<b>Показываю</b>
Вердикт — ехать или нет
Экипировку и подготовку
Прогноз на 3ч, ночь, завтра

<b>Подписка на утро</b>
Прогноз в 7:00 каждый день

<b>▼▼▼ ПРИМЕР ПЛОХОЙ ПОГОДЫ ▼▼▼</b>

🌧️ <b>MotoWeather Минск</b> · 06:00

+3°C, дождь · 12 м/с, порывы 18
💧 96% · 👁️ 800 м · 🌇 темно

🔴 НЕ САДИСЬ ЗА РУЛЬ
Риск 9/10

🌧️ Дождь — скользко
🌫️ Туман — видимость 800 м
🌪️ Ветер 12 м/с

🧥 Тёплое
☔ Дождевик
💡 Доп. свет

✅ Шины + свет
✅ Визор
✅ Противотуманки

💡 Туман — противотуманки, скорость минимальная.

🏍️ Ровной дороги!

<b>▲▲▲ КОНЕЦ ПРИМЕРА ▲▲▲</b>

<b>🚫 За рулём — только трезвый</b>
Алкоголь = реакция ×3 хуже.

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

Отписаться — кнопкой ниже."""

SUBSCRIBE_CANCELED = """❌ <b>Подписка отменена</b>

Жми «🌅 Подписка» чтобы вернуться."""

UNSUBSCRIBE_PROMPT = """❌ <b>Отписаться от рассылки?</b>

Перестанешь получать утренний прогноз в 7:00."""

UNSUBSCRIBED = """❌ <b>Отписан от рассылки</b>

Жми «🌅 Подписка» чтобы вернуться."""

UNSUBSCRIBE_CANCELED = """✅ <b>Остаёмся!</b>

Прогноз в 7:00 продолжит приходить."""

ALREADY_SUBSCRIBED = """ℹ️ <b>Ты уже подписан</b>

Отписаться — кнопкой ниже."""


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
            print(f"⚠️ edit_or_send: {e2}", flush=True)
        return False


# ============ СБОРКА СООБЩЕНИЯ ============
def build_weather_message(w, a, short, f, is_morning=False):
    now_dt = datetime.now(MINSK_TZ)
    now = now_dt.strftime("%H:%M")

    feels = a.get("feels_like", w.get("feels_like", 0))

    cloud = shorten_cond(w.get('cloud_text', '—'))
    weather_info = f"{w.get('weather_emoji') or ''} {w.get('weather_text') or ''}".strip()
    if not weather_info:
        weather_info = "без осадков"
    else:
        weather_info = shorten_cond(weather_info)

    weather_line = f"{w['temp']}°C, {cloud}"
    if weather_info and weather_info != "без осадков":
        weather_line += f", {weather_info}"
    weather_line += f" · {w['wind_speed']} м/с"

    wind_extra = ""
    if w.get("wind_gust") and w["wind_gust"] > w["wind_speed"] + 3:
        wind_extra = f", порывы {w['wind_gust']}"

    humidity_str = f"{w['humidity']}%" if w.get("humidity") else "—"
    vis_str = format_visibility(w["visibility"])

    light_short = ""
    if w.get("sunrise") and w.get("sunset"):
        light_full = get_daylight_info(w.get("sunrise"), w.get("sunset"))
        if "Темно" in light_full:
            light_short = "темно"
        elif "Светло" in light_full:
            light_short = "светло"

    info_line = f"💧 {humidity_str} · 👁️ {vis_str}"
    if light_short:
        info_line += f" · 🌇 {light_short}"

    rider_verdict = get_rider_verdict(a["score"])

    risk_factors = a["risks"][:3]
    risk_block = "\n".join(risk_factors) if risk_factors else "✅ Дорога чистая"

    gear = get_gear_short(feels, w.get("is_rain", False), w.get("is_night", False), w["wind_speed"])
    gear_block = "\n".join(gear)

    tech = get_tech_check(feels, w.get("is_night", False), w.get("is_rain", False),
                          w.get("humidity"), w.get("dew_point"))
    tech_block = "\n".join(f"✅ {t}" for t in tech)

    next_hour = short.get("next_hour", "нет данных")
    next_period = short.get("next_period", "нет данных")
    next_period_label = short.get("next_period_label", "—")
    next_period_title = short.get("next_period_title", "—")
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

    next_hour_short = shorten_forecast(next_hour)
    next_period_short = shorten_forecast(next_period)

    tomorrow_line = "нет данных"
    if f:
        fa = analyze_risks(f, is_forecast=True)
        fa_short = get_short_verdict(fa["score"])
        cond_low = shorten_cond(f["condition"].split(" ", 1)[-1].lower())
        emoji_short = f["condition"].split(" ", 1)[0]
        tomorrow_line = (
            f"{f['temp_min']}–{f['temp_max']}°C, {cond_low} · "
            f"{f['wind_speed']} м/с {emoji_short} {fa['color']}"
        )

    tip = get_tip(
        feels, w.get("humidity"), w.get("is_rain", False), w.get("is_night", False),
        w["wind_speed"], w.get("is_thunder", False), w.get("visibility")
    )

    header_icon = w.get('weather_emoji') or "🌤"
    if is_morning:
        header_text = "🌅 <b>MotoWeather Минск</b> · утро"
    else:
        header_text = f"{header_icon} <b>MotoWeather Минск</b> · {now}"

    next_hour_block = ""
    if show_next_hour and next_hour != "нет данных":
        next_hour_block = f"⏱️ +3ч: {next_hour_short}\n"

    msg = f"""{header_text}

{weather_line}{wind_extra}
{info_line}

<b>{rider_verdict}</b>
Риск {a['score']}/10

<b>ЧТО НА ДОРОГЕ</b>
{risk_block}

<b>НА СЕБЯ</b>
{gear_block}

<b>ПЕРЕД ВЫЕЗДОМ</b>
{tech_block}

{next_hour_block}{next_period_title}: {next_period_short}
📅 Завтра: {tomorrow_line}

💡 <i>{tip}</i>"""

    if is_morning:
        alcohol = get_alcohol_warning()
        quote = get_random_quote()
        msg += f"\n\n{alcohol}\n\n💬 <i>{quote}</i>"

    msg += "\n\n🏍️ <b>Ровной дороги!</b>"

    return msg


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
                print(f"🌅 Утренняя рассылка ({today_str})", flush=True)

                subs = load_subscribers()
                if not subs:
                    _last_morning_sent["date"] = today_str
                    continue

                w = get_weather()
                if not w:
                    _last_morning_sent["date"] = today_str
                    continue

                a = analyze_risks(w)
                short = get_short_forecast()
                f = get_forecast_tomorrow()

                msg = build_weather_message(w, a, short, f, is_morning=True)

                sent = 0
                failed = []
                for uid in subs:
                    try:
                        bot.send_message(uid, msg, parse_mode="HTML",
                                         reply_markup=get_after_weather_keyboard(is_subscribed=True))
                        sent += 1
                        time.sleep(0.05)
                    except Exception as e:
                        print(f"⚠️ Не отправил {uid}: {e}", flush=True)
                        failed.append(uid)

                print(f"✅ Рассылка: {sent} ок, {len(failed)} ошибок", flush=True)
                for uid in failed:
                    remove_subscriber(uid)

                _last_morning_sent["date"] = today_str

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
            "🏍️ <b>MOTOWEATHER МИНСК</b>\n"
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
        # 🔴 ФИКС: "⏳ Смотрю на небо..." теперь превращается в погоду
        # через edit, а не висит вечно отдельным сообщением.
        loading = bot.send_message(m.chat.id, "⏳ Смотрю на небо...")
        send_weather(m.chat.id, edit_message=loading)
    except Exception as e:
        print(f"❌ /weather: {e}", flush=True)


@bot.message_handler(commands=['about'])
def about_cmd(m):
    try:
        save_user(m.chat.id)
        sub_status = is_subscribed(m.chat.id)
        bot.send_message(m.chat.id, ABOUT_TEXT, parse_mode="HTML",
                         reply_markup=get_about_keyboard(is_subscribed=sub_status))
    except Exception as e:
        print(f"❌ /about: {e}", flush=True)


@bot.message_handler(commands=['subscribe'])
def subscribe_cmd(m):
    try:
        save_user(m.chat.id)
        if is_subscribed(m.chat.id):
            bot.send_message(m.chat.id, ALREADY_SUBSCRIBED,
                             parse_mode="HTML",
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
            bot.send_message(m.chat.id, "ℹ️ Ты не подписан.",
                             parse_mode="HTML",
                             reply_markup=get_main_keyboard(is_subscribed=False))
            return
        bot.send_message(m.chat.id, UNSUBSCRIBE_PROMPT, parse_mode="HTML",
                         reply_markup=get_unsubscribe_keyboard())
    except Exception as e:
        print(f"❌ /unsubscribe: {e}", flush=True)


@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    # 🔴 ФИКС: если ADMIN_ID не задан (0) — админки нет ни у кого.
    if not ADMIN_ID or m.chat.id != ADMIN_ID:
        bot.reply_to(m, "❌ Нет прав.")
        return
    bot.reply_to(
        m,
        f"📊 <b>Статистика</b>\n"
        f"👥 Юзеров: {get_users_count()}\n"
        f"🌅 Подписчиков: {len(load_subscribers())}\n"
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
            msg_text = "⏳ Смотрю..." if call.data == "weather" else "⏳ Обновляю..."
            bot.answer_callback_query(call.id, msg_text, cache_time=3)
            send_weather(chat_id, edit_message=call.message)

        elif call.data == "about":
            bot.answer_callback_query(call.id, "✅", cache_time=3)
            sub_status = is_subscribed(chat_id)
            edit_or_send(chat_id, msg_id, ABOUT_TEXT,
                         get_about_keyboard(is_subscribed=sub_status))

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

        elif call.data == "unsubscribe_prompt":
            bot.answer_callback_query(call.id, "❌ Отписка", cache_time=3)
            edit_or_send(chat_id, msg_id, UNSUBSCRIBE_PROMPT,
                         get_unsubscribe_keyboard())

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
def send_weather(chat_id, edit_message=None):
    try:
        w = get_weather()
        if not w:
            bot.send_message(chat_id, "❌ Небо молчит.")
            return

        a = analyze_risks(w)
        short = get_short_forecast()
        f = get_forecast_tomorrow()

        msg = build_weather_message(w, a, short, f, is_morning=False)
        sub_status = is_subscribed(chat_id)

        if edit_message:
            edit_or_send(chat_id, edit_message.message_id, msg,
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