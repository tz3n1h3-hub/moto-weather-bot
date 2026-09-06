import telebot
import requests
import json
import os
import time
import threading
from datetime import datetime, timedelta, timezone
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============ ТОКЕНЫ ============
BOT_TOKEN = "8726317506:AAFTww4YFYu76GPuy4ZfSbz5MwoiLtAdTK8"
OPENWEATHER_API_KEY = "6454a46bd311f896c7cc92ffdf5781ad"

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

if not OPENWEATHER_API_KEY:
    print("❌ ОШИБКА: OPENWEATHER_API_KEY не найден!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# ============ ЧАСОВОЙ ПОЯС МИНСКА ============
MINSK_TZ = timezone(timedelta(hours=3))

def get_minsk_time():
    return datetime.now(MINSK_TZ).strftime("%H:%M")

def get_minsk_hour():
    return datetime.now(MINSK_TZ).hour

# ============ РАБОТА С ФАЙЛОМ ПОЛЬЗОВАТЕЛЕЙ ============
USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_user(user_id):
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        with open(USERS_FILE, "w") as f:
            json.dump(users, f)
        return True
    return False

def get_users_count():
    return len(load_users())

# ============ ПОЛУЧЕНИЕ ТЕКУЩЕЙ ПОГОДЫ ============
def get_weather():
    try:
        cache_buster = int(time.time())
        url = f"https://api.openweathermap.org/data/2.5/weather?lat=53.9045&lon=27.5615&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&_={cache_buster}"
        
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if data.get("cod") != 200:
            print(f"Ошибка OpenWeatherMap: {data.get('message')}")
            return None
        
        temp = int(data["main"]["temp"])
        wind_speed = int(data["wind"]["speed"])
        wind_gust = int(data["wind"].get("gust", wind_speed * 1.2))
        humidity = int(data["main"]["humidity"])
        pressure = int(data["main"]["pressure"] * 0.75006)
        
        rain = data.get("rain")
        rain_1h = 0
        if rain:
            rain_1h = rain.get("1h", 0)
        
        snow = data.get("snow")
        snow_1h = 0
        if snow:
            snow_1h = snow.get("1h", 0)
        
        visibility = data.get("visibility", 10000)
        
        weather_id = data["weather"][0]["id"]
        weather_desc = data["weather"][0]["description"]
        
        if weather_id >= 200 and weather_id < 300:
            condition = "⛈️ Гроза"
            is_thunder = True
            is_rain = True
        elif weather_id >= 300 and weather_id < 400:
            condition = "🌦️ Морось"
            is_thunder = False
            is_rain = True
        elif weather_id >= 500 and weather_id < 600:
            if weather_id >= 502:
                condition = "🌧️ Сильный дождь"
            else:
                condition = "🌧️ Дождь"
            is_thunder = False
            is_rain = True
        elif weather_id >= 600 and weather_id < 700:
            condition = "❄️ Снег"
            is_thunder = False
            is_rain = False
        elif weather_id >= 700 and weather_id < 800:
            if weather_id == 741:
                condition = "🌫️ Туман"
            else:
                condition = "🌫️ Дымка"
            is_thunder = False
            is_rain = False
        elif weather_id == 800:
            condition = "☀️ Ясно"
            is_thunder = False
            is_rain = False
        elif weather_id > 800:
            if weather_id >= 803:
                condition = "☁️ Пасмурно"
            else:
                condition = "⛅ Облачно"
            is_thunder = False
            is_rain = False
        else:
            condition = f"🌤️ {weather_desc}"
            is_thunder = False
            is_rain = False
        
        current_hour = get_minsk_hour()
        is_night = current_hour < 6 or current_hour > 20
        
        feels_like = int(data["main"]["feels_like"])
        
        return {
            "temp": temp,
            "feels_like": feels_like,
            "condition": condition,
            "wind_speed": wind_speed,
            "wind_gust": wind_gust,
            "humidity": humidity,
            "pressure": pressure,
            "rain_1h": rain_1h,
            "snow_1h": snow_1h,
            "visibility": visibility,
            "is_rain": is_rain,
            "is_thunder": is_thunder,
            "is_night": is_night,
            "source": "OpenWeatherMap",
            "timestamp": get_minsk_time(),
            "description": weather_desc,
            "update_time": datetime.now(MINSK_TZ).strftime("%H:%M:%S")
        }
        
    except Exception as e:
        print(f"Ошибка получения погоды: {e}")
        return None

# ============ ПОЛУЧЕНИЕ ПРОГНОЗА НА ЗАВТРА ============
def get_forecast_tomorrow():
    """Получает прогноз на завтра (средние значения за день)"""
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat=53.9045&lon=27.5615&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&cnt=8"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("cod") != "200":
            print(f"Ошибка прогноза: {data.get('message')}")
            return None
        
        # Завтрашний день
        tomorrow = datetime.now(MINSK_TZ) + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")
        
        # Собираем данные по завтрашним прогнозам (каждые 3 часа)
        temps = []
        wind_speeds = []
        rain_total = 0
        conditions = []
        
        for item in data["list"]:
            dt = datetime.fromtimestamp(item["dt"], tz=MINSK_TZ)
            if dt.strftime("%Y-%m-%d") == tomorrow_str:
                temps.append(item["main"]["temp"])
                wind_speeds.append(item["wind"]["speed"])
                if "rain" in item:
                    rain_total += item["rain"].get("3h", 0)
                conditions.append(item["weather"][0]["id"])
        
        if not temps:
            return None
        
        # Средние значения
        avg_temp = int(sum(temps) / len(temps))
        max_temp = int(max(temps))
        min_temp = int(min(temps))
        avg_wind = int(sum(wind_speeds) / len(wind_speeds))
        max_wind = int(max(wind_speeds))
        wind_gust = int(max_wind * 1.3)
        
        # Определяем погоду
        most_common = max(set(conditions), key=conditions.count) if conditions else 800
        
        if most_common >= 200 and most_common < 300:
            condition = "⛈️ Гроза"
            is_rain = True
            is_thunder = True
        elif most_common >= 500 and most_common < 600:
            if most_common >= 502:
                condition = "🌧️ Сильный дождь"
            else:
                condition = "🌧️ Дождь"
            is_rain = True
            is_thunder = False
        elif most_common >= 600 and most_common < 700:
            condition = "❄️ Снег"
            is_rain = False
            is_thunder = False
        elif most_common == 800:
            condition = "☀️ Ясно"
            is_rain = False
            is_thunder = False
        elif most_common > 800:
            condition = "☁️ Облачно"
            is_rain = False
            is_thunder = False
        else:
            condition = "🌤️ Переменная облачность"
            is_rain = False
            is_thunder = False
        
        return {
            "date": tomorrow.strftime("%d.%m.%Y"),
            "temp_avg": avg_temp,
            "temp_max": max_temp,
            "temp_min": min_temp,
            "wind_speed": avg_wind,
            "wind_gust": wind_gust,
            "rain_total": round(rain_total, 1),
            "condition": condition,
            "is_rain": is_rain,
            "is_thunder": is_thunder,
            "source": "OpenWeatherMap (прогноз)",
            "update_time": datetime.now(MINSK_TZ).strftime("%H:%M:%S")
        }
        
    except Exception as e:
        print(f"Ошибка получения прогноза: {e}")
        return None

# ============ АНАЛИЗ РИСКОВ ============
def analyze_risks(weather, is_forecast=False):
    risks = []
    score = 0
    recommendations = []
    
    wind_gust = weather.get("wind_gust", 0)
    wind_speed = weather.get("wind_speed", 0)
    temp = weather.get("temp", 0)
    rain_total = weather.get("rain_total", 0)
    is_rain = weather.get("is_rain", False)
    is_thunder = weather.get("is_thunder", False)
    
    if wind_gust > 20:
        risks.append(f"🌪️ КРИТИЧЕСКИЙ ВЕТЕР (порывы до {wind_gust:.0f} м/с)!")
        score += 5
        recommendations.append("🚫 Откажитесь от поездки")
    elif wind_gust > 15:
        risks.append(f"💨 Сильный ветер (порывы до {wind_gust:.0f} м/с)")
        score += 3
        recommendations.append("🛑 Держите руль крепче, снизьте скорость")
    elif wind_speed > 10:
        risks.append(f"🌬️ Умеренный ветер {wind_speed:.0f} м/с")
        score += 1
    
    if is_thunder:
        risks.append("⚡ ГРОЗА! Категорически запрещено")
        score += 5
        recommendations.append("🚫 НЕМЕДЛЕННО остановитесь, найдите укрытие")
    elif rain_total > 5:
        risks.append(f"🌧️ СИЛЬНЫЙ ДОЖДЬ ({rain_total:.1f} мм) - плохая видимость!")
        score += 4
        recommendations.append("🐢 Увеличьте дистанцию, снизьте скорость")
    elif rain_total > 1:
        risks.append(f"🌧️ Дождь ({rain_total:.1f} мм) - дорога мокрая")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию, избегайте резких манёвров")
    elif is_rain:
        risks.append("🌧️ Дождь (дорога скользкая)")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию, избегайте резких манёвров")
    
    if isinstance(weather.get("temp"), (int, float)):
        feels_like = weather.get("feels_like", temp)
    else:
        feels_like = temp
    
    if feels_like < 5:
        risks.append(f"🥶 Очень холодно (ощущается как {feels_like}°C)")
        score += 3
        recommendations.append("🧥 Тёплая экипировка, подогрев ручек")
    elif feels_like < 10:
        risks.append(f"❄️ Холодно (ощущается как {feels_like}°C)")
        score += 1
        recommendations.append("🧥 Ветрозащита обязательна")
    elif feels_like > 35:
        risks.append(f"🔥 Очень жарко (ощущается как {feels_like}°C)")
        score += 2
        recommendations.append("💧 Пейте воду, делайте частые остановки")
    
    if not is_forecast and weather.get("is_night", False):
        risks.append("🌙 Ночное время - плохая видимость")
        score += 2
        recommendations.append("💡 Включите свет, снизьте скорость")
    
    if score >= 8:
        verdict = "⛔️ ОПАСНОСТЬ! НЕ РЕКОМЕНДУЕТСЯ!"
        color = "🔴"
    elif score >= 5:
        verdict = "⚠️ РИСКОВАННО - с осторожностью"
        color = "🟡"
    elif score >= 2:
        verdict = "🟡 УМЕРЕННЫЙ РИСК - будьте внимательны"
        color = "🟠"
    else:
        verdict = "✅ БЕЗОПАСНО - отличная погода!"
        color = "🟢"
    
    return {
        "score": min(score, 10),
        "verdict": verdict,
        "color": color,
        "risks": risks,
        "recommendations": recommendations
    }

# ============ КЛАВИАТУРА ============
def get_main_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📊 Прогноз", callback_data="weather"),
        InlineKeyboardButton("📅 Завтра", callback_data="forecast")
    )
    markup.row(
        InlineKeyboardButton("🏍️ Советы", callback_data="tips"),
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup

def get_after_weather_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 Обновить", callback_data="update"),
        InlineKeyboardButton("📅 Завтра", callback_data="forecast")
    )
    markup.row(
        InlineKeyboardButton("🏍️ Советы", callback_data="tips"),
        InlineKeyboardButton("ℹ️ О проекте", callback_data="about")
    )
    return markup

def get_back_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔙 Назад", callback_data="back")
    )
    return markup

# ============ КОМАНДЫ ============
@bot.message_handler(commands=['start'])
def start(message):
    save_user(message.chat.id)
    bot.send_message(
        message.chat.id,
        "🏍️ *MotoWeather Минск*\n\n"
        "Я анализирую погоду для мотоциклистов!\n"
        "Нажмите кнопку ниже, чтобы узнать прогноз.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(commands=['weather'])
def weather_command(message):
    save_user(message.chat.id)
    bot.send_message(message.chat.id, "⏳ Загружаю данные...")
    send_weather(message.chat.id)

@bot.message_handler(commands=['forecast'])
def forecast_command(message):
    save_user(message.chat.id)
    bot.send_message(message.chat.id, "⏳ Загружаю прогноз на завтра...")
    send_forecast(message.chat.id)

@bot.message_handler(commands=['stats'])
def stats_command(message):
    ADMIN_ID = 8930836312
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет прав на эту команду.")
        return
    
    count = get_users_count()
    bot.reply_to(
        message, 
        f"📊 *Статистика бота*\n\n"
        f"👥 Всего пользователей: *{count}*\n"
        f"📅 Последнее обновление: {datetime.now(MINSK_TZ).strftime('%d.%m.%Y %H:%M')}",
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        save_user(call.message.chat.id)
        
        if call.data == "weather":
            bot.answer_callback_query(call.id, "⏳ Загружаю прогноз...")
            send_weather(call.message.chat.id)
        elif call.data == "forecast":
            bot.answer_callback_query(call.id, "⏳ Загружаю прогноз на завтра...")
            send_forecast(call.message.chat.id)
        elif call.data == "update":
            bot.answer_callback_query(call.id, "⏳ Обновляю...")
            send_weather(call.message.chat.id)
        elif call.data == "tips":
            tips = """
🏍️ *Советы для мотоциклистов:*

🟢 *Хорошая погода:*
• Проверьте шины и свет
• Надевайте защитную экипировку

🟡 *Ветер:*
• Держите руль крепче
• Снизьте скорость на открытых участках

🔴 *Дождь:*
• Увеличьте дистанцию
• Избегайте резких манёвров
• Будьте осторожны на разметке

⚡ *Гроза:*
• НЕМЕДЛЕННО остановитесь
• Найдите укрытие
• Не стойте под деревьями

🌫️ *Туман:*
• Включите противотуманки
• Снизьте скорость до минимума

*Берегите себя!* 🏍️
"""
            bot.send_message(
                call.message.chat.id, 
                tips, 
                parse_mode="Markdown",
                reply_markup=get_back_keyboard()
            )
        elif call.data == "about":
            about_text = """
ℹ️ *О проекте*

🏍️ *MotoWeather Минск*

Бот создан для мотоциклистов, чтобы анализировать погоду и оценивать риски для безопасных поездок.

*Возможности:*
• 🌡️ Текущая погода
• 📅 Прогноз на завтра
• 💨 Реальные порывы ветра
• 🌧️ Учёт осадков
• 📊 Анализ рисков
• 💡 Персональные рекомендации
• 🌙 Учёт времени суток

*Источник данных:* OpenWeatherMap
*Платформа:* Render.com (24/7)
*Часовой пояс:* Минск (UTC+3)

👨‍💻 *Разработчик:* K8V

🏍️ *Берегите себя на дороге!*
"""
            bot.send_message(
                call.message.chat.id, 
                about_text, 
                parse_mode="Markdown",
                reply_markup=get_back_keyboard()
            )
        elif call.data == "back":
            bot.answer_callback_query(call.id, "🔙 Возвращаюсь...")
            bot.send_message(
                call.message.chat.id,
                "🏍️ *MotoWeather Минск*\n\n"
                "Выберите действие:",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        print(f"Ошибка: {e}")

def send_weather(chat_id):
    weather = get_weather()
    if not weather:
        bot.send_message(chat_id, "❌ Не удалось получить данные о погоде.")
        return
    
    analysis = analyze_risks(weather)
    
    now = get_minsk_time()
    feels_like = weather.get('feels_like', weather.get('temp', 0))
    update_time = weather.get('update_time', 'Неизвестно')
    
    weather_desc = weather.get('condition', '').replace('🌦️', '').replace('🌧️', '').replace('☀️', '').replace('⛅', '').replace('☁️', '').replace('🌫️', '').replace('❄️', '').replace('⛈️', '').replace('🌤️', '').strip()
    
    risk_emoji = analysis['color']
    
    day_emoji = '🌙' if weather.get('is_night', False) else '☀️'
    day_text = 'Ночь' if weather.get('is_night', False) else 'День'
    
    rain_info = ""
    if weather.get('rain_1h', 0) > 0:
        rain_info = f" 🌧️{weather.get('rain_1h', 0):.1f} мм/ч"
    elif weather.get('snow_1h', 0) > 0:
        rain_info = f" ❄️{weather.get('snow_1h', 0):.1f} мм/ч"
    
    visibility_info = ""
    visibility = weather.get('visibility', 10000)
    if visibility < 2000:
        visibility_info = f" 🌫️{visibility} м"
    
    msg = f"""
{risk_emoji} *MotoWeather Минск* — *Сейчас*

{day_emoji} *Время суток:* {day_text} ({now})
🌡️ *Температура:* {weather.get('temp', 0)}°C (ощущается как {feels_like}°C)
💨 *Ветер:* {weather.get('wind_speed', 0):.0f} м/с (порывы до {weather.get('wind_gust', 0):.0f})
💧 *Влажность:* {weather.get('humidity', 0)}% {f'({weather_desc})' if weather_desc else ''}{rain_info}{visibility_info}
📊 *Давление:* {weather.get('pressure', 0):.1f} мм рт.ст.

*ВЕРДИКТ:* {analysis['verdict']}
📊 *Уровень риска:* {analysis['score']}/10
"""
    
    if analysis["risks"]:
        msg += "\n*⚠️ Факторы риска:*\n"
        for risk in analysis["risks"]:
            msg += f"• {risk}\n"
    else:
        msg += "\n✅ *Нет факторов риска*\n"
    
    if analysis["recommendations"]:
        msg += "\n*💡 Рекомендации:*\n"
        for rec in analysis["recommendations"]:
            msg += f"• {rec}\n"
    
    msg += f"\n🔄 *Обновлено:* {update_time}"
    
    bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=get_after_weather_keyboard())

def send_forecast(chat_id):
    forecast = get_forecast_tomorrow()
    if not forecast:
        bot.send_message(chat_id, "❌ Не удалось получить прогноз на завтра.")
        return
    
    analysis = analyze_risks(forecast, is_forecast=True)
    
    risk_emoji = analysis['color']
    update_time = forecast.get('update_time', 'Неизвестно')
    
    rain_info = ""
    if forecast.get('rain_total', 0) > 0:
        rain_info = f" 🌧️{forecast.get('rain_total', 0):.1f} мм (за день)"
    
    msg = f"""
{risk_emoji} *MotoWeather Минск* — *Прогноз на {forecast.get('date', 'завтра')}*

🌡️ *Температура:* {forecast.get('temp_avg', 0)}°C (мин {forecast.get('temp_min', 0)}°C / макс {forecast.get('temp_max', 0)}°C)
💨 *Ветер:* {forecast.get('wind_speed', 0):.0f} м/с (порывы до {forecast.get('wind_gust', 0):.0f})
☁️ *Погода:* {forecast.get('condition', '')}{rain_info}

*ВЕРДИКТ:* {analysis['verdict']}
📊 *Уровень риска:* {analysis['score']}/10
"""
    
    if analysis["risks"]:
        msg += "\n*⚠️ Факторы риска:*\n"
        for risk in analysis["risks"]:
            msg += f"• {risk}\n"
    else:
        msg += "\n✅ *Нет факторов риска*\n"
    
    if analysis["recommendations"]:
        msg += "\n*💡 Рекомендации:*\n"
        for rec in analysis["recommendations"]:
            msg += f"• {rec}\n"
    
    msg += f"\n🔄 *Обновлено:* {update_time}"
    msg += f"\n📡 *Источник:* {forecast.get('source', 'Неизвестно')}"
    
    bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=get_after_weather_keyboard())

# ============ ВЕБ-СЕРВЕР ДЛЯ ПИНГА ============
from flask import Flask, jsonify
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "🏍️ MotoWeather Bot is running! Use /weather in Telegram.", 200

@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "bot": "MotoWeather Minsk",
        "users": get_users_count(),
        "time": datetime.now(MINSK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    }), 200

def run_flask():
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ============ ЗАПУСК ============
if __name__ == "__main__":
    print("🏍️ MotoWeather Бот запущен!")
    print("✅ Источник: OpenWeatherMap")
    print("✅ Добавлен прогноз на завтра")
    print("✅ Веб-сервер для пинга: https://moto-weather-bot.onrender.com/health")
    print("✅ Часовой пояс: Минск (UTC+3)")
    print("📡 Бот готов к работе")
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    bot.infinity_polling()
EOF
