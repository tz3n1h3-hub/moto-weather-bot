import telebot
import requests
import json
import os
import time
import threading
from datetime import datetime, timedelta, timezone
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, jsonify

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
app = Flask(__name__)

# ============ ЧАСОВОЙ ПОЯС МИНСКА ============
MINSK_TZ = timezone(timedelta(hours=3))

def get_minsk_time():
    return datetime.now(MINSK_TZ).strftime("%H:%M")

def get_minsk_hour():
    return datetime.now(MINSK_TZ).hour

def get_minsk_month():
    return datetime.now(MINSK_TZ).month

# ============ ОПРЕДЕЛЕНИЕ ОСВЕЩЁННОСТИ ============
def get_light_level():
    current_hour = get_minsk_hour()
    month = get_minsk_month()
    
    if 5 <= month <= 8:
        if 5 <= current_hour < 22:
            return "☀️ Светло"
        else:
            return "🌙 Темно"
    elif 11 <= month <= 2:
        if 8 <= current_hour < 17:
            return "☀️ Светло"
        else:
            return "🌙 Темно"
    else:
        if 6 <= current_hour < 20:
            return "☀️ Светло"
        else:
            return "🌙 Темно"

def is_night_time():
    return get_light_level() == "🌙 Темно"

# ============ РАСШИФРОВКА ============
def get_wind_description(speed):
    if speed <= 1:
        return "штиль"
    elif speed <= 6:
        return "лёгкий ветер"
    elif speed <= 10:
        return "умеренный ветер"
    elif speed <= 14:
        return "сильный ветер"
    elif speed <= 19:
        return "очень сильный ветер"
    else:
        return "штормовой ветер! ⚠️"

def get_wind_feeling(speed):
    if speed <= 1:
        return "🌿 Безветренно"
    elif speed <= 6:
        return "🍃 Комфортно, ветер почти не ощущается"
    elif speed <= 10:
        return "🌬️ Ощущается, но не мешает"
    elif speed <= 14:
        return "💨 Требует внимания на дороге"
    elif speed <= 19:
        return "⚠️ Сильно влияет на управление"
    else:
        return "🚫 Опасно для езды!"

def get_temp_description(temp):
    if temp >= 25:
        return "жарко"
    elif temp >= 18:
        return "тепло"
    elif temp >= 10:
        return "прохладно"
    elif temp >= 5:
        return "холодно"
    elif temp >= 0:
        return "очень холодно"
    else:
        return "морозно! ⚠️"

def get_gear_recommendation(temp):
    if temp >= 25:
        return "🟢 Лёгкая экипировка, сетка, пейте больше воды"
    elif temp >= 18:
        return "🟢 Стандартная экипировка"
    elif temp >= 10:
        return "🟡 Ветрозащита, тёплая подкладка"
    elif temp >= 5:
        return "🟠 Тёплая экипировка, подогрев ручек"
    elif temp >= 0:
        return "🔴 Очень тёплая экипировка, полный подогрев"
    else:
        return "🔴 Мороз! Только с полным подогревом!"

def get_best_time():
    hour = get_minsk_hour()
    if 10 <= hour <= 16:
        return "🕐 Сейчас лучшее время для поездки (самая тёплая часть дня)"
    elif 7 <= hour <= 9:
        return "🕐 Утро — будьте осторожны, дорога может быть скользкой"
    elif 17 <= hour <= 20:
        return "🕐 Вечер — видимость ухудшается, включите свет"
    else:
        return "🕐 Ночное время — только с хорошим светом и сниженной скоростью"

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
        
        is_night = is_night_time()
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
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat=53.9045&lon=27.5615&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&cnt=8"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("cod") != "200":
            print(f"Ошибка прогноза: {data.get('message')}")
            return None
        
        tomorrow = datetime.now(MINSK_TZ) + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")
        
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
        
        avg_temp = int(sum(temps) / len(temps))
        max_temp = int(max(temps))
        min_temp = int(min(temps))
        avg_wind = int(sum(wind_speeds) / len(wind_speeds))
        max_wind = int(max(wind_speeds))
        wind_gust = int(max_wind * 1.3)
        
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

# ============ ПОЛУЧЕНИЕ ПРОГНОЗА НА НЕДЕЛЮ ============
def get_weekly_forecast():
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat=53.9045&lon=27.5615&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&cnt=40"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("cod") != "200":
            print(f"Ошибка прогноза: {data.get('message')}")
            return None
        
        days = {}
        today = datetime.now(MINSK_TZ).date()
        
        for item in data["list"]:
            dt = datetime.fromtimestamp(item["dt"], tz=MINSK_TZ)
            date_key = dt.strftime("%Y-%m-%d")
            day_date = dt.date()
            
            if day_date == today:
                continue
            
            if date_key not in days:
                days[date_key] = {
                    "temps": [],
                    "winds": [],
                    "rain": 0,
                    "conditions": [],
                    "date": dt
                }
            
            days[date_key]["temps"].append(item["main"]["temp"])
            days[date_key]["winds"].append(item["wind"]["speed"])
            if "rain" in item:
                days[date_key]["rain"] += item["rain"].get("3h", 0)
            days[date_key]["conditions"].append(item["weather"][0]["id"])
        
        result = []
        for date_key, data_day in sorted(days.items())[:7]:
            temps = data_day["temps"]
            winds = data_day["winds"]
            conditions = data_day["conditions"]
            
            if not temps:
                continue
            
            avg_temp = int(sum(temps) / len(temps))
            max_temp = int(max(temps))
            min_temp = int(min(temps))
            avg_wind = int(sum(winds) / len(winds))
            max_wind = int(max(winds))
            wind_gust = int(max_wind * 1.3)
            rain_total = round(data_day["rain"], 1)
            
            most_common = max(set(conditions), key=conditions.count) if conditions else 800
            
            if most_common >= 200 and most_common < 300:
                condition = "⛈️"
                is_rain = True
                is_thunder = True
            elif most_common >= 500 and most_common < 600:
                condition = "🌧️"
                is_rain = True
                is_thunder = False
            elif most_common >= 600 and most_common < 700:
                condition = "❄️"
                is_rain = False
                is_thunder = False
            elif most_common == 800:
                condition = "☀️"
                is_rain = False
                is_thunder = False
            elif most_common > 800:
                condition = "☁️"
                is_rain = False
                is_thunder = False
            else:
                condition = "🌤️"
                is_rain = False
                is_thunder = False
            
            weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            weekday = weekday_names[data_day["date"].weekday()]
            
            result.append({
                "weekday": weekday,
                "date": data_day["date"].strftime("%d.%m"),
                "condition": condition,
                "temp_max": max_temp,
                "temp_min": min_temp,
                "temp_avg": avg_temp,
                "wind_speed": avg_wind,
                "wind_gust": wind_gust,
                "rain_total": rain_total,
                "is_rain": is_rain,
                "is_thunder": is_thunder
            })
        
        return result
        
    except Exception as e:
        print(f"Ошибка получения недельного прогноза: {e}")
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
    
    # ОЩУЩАЕМАЯ ТЕМПЕРАТУРА (ИСПРАВЛЕНО)
    if is_forecast:
        feels_like = temp  # Для прогноза используем среднюю температуру
    else:
        feels_like = weather.get("feels_like", temp)
    
    if feels_like < 5:
        risks.append(f"🥶 Очень холодно ({feels_like}°C)")
        score += 3
        recommendations.append("🧥 Тёплая экипировка, подогрев ручек")
    elif feels_like < 10:
        risks.append(f"❄️ Холодно ({feels_like}°C)")
        score += 1
        recommendations.append("🧥 Ветрозащита обязательна")
    elif feels_like > 35:
        risks.append(f"🔥 Очень жарко ({feels_like}°C)")
        score += 2
        recommendations.append("💧 Пейте воду, делайте частые остановки")
    
    if not is_forecast and weather.get("is_night", False):
        risks.append("🌙 Темно - плохая видимость")
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
        "recommendations": recommendations,
        "feels_like": feels_like
    }

# ============ КЛАВИАТУРА ============
def get_main_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📊 Сейчас", callback_data="weather"),
        InlineKeyboardButton("📅 Завтра", callback_data="forecast")
    )
    markup.row(
        InlineKeyboardButton("📆 Неделя", callback_data="weekly"),
        InlineKeyboardButton("🏍️ Советы", callback_data="tips")
    )
    markup.row(
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
        InlineKeyboardButton("📆 Неделя", callback_data="weekly"),
        InlineKeyboardButton("🏍️ Советы", callback_data="tips")
    )
    markup.row(
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

@bot.message_handler(commands=['weekly'])
def weekly_command(message):
    save_user(message.chat.id)
    bot.send_message(message.chat.id, "⏳ Загружаю прогноз на неделю...")
    send_weekly(message.chat.id)

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

# ============ ОБРАБОТКА КНОПОК ============
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
        elif call.data == "weekly":
            bot.answer_callback_query(call.id, "⏳ Загружаю прогноз на неделю...")
            send_weekly(call.message.chat.id)
        elif call.data == "update":
            bot.answer_callback_query(call.id, "⏳ Обновляю...")
            send_weather(call.message.chat.id)
        elif call.data == "tips":
            tips = """
🏍️ *Советы для мотоциклистов:*

🟢 *Светло:*
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

🌙 *Темно:*
• Включите дальний свет
• Снизьте скорость
• Будьте особенно внимательны

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
ℹ️ *О ПРОЕКТЕ*

🏍️ *MotoWeather Минск*

Бот создан для мотоциклистов, чтобы анализировать погоду и оценивать риски для безопасных поездок.

═══════════════════════
*📊 ВОЗМОЖНОСТИ БОТА:*

🌡️ *Текущая погода* — температура, ветер, влажность, давление
📅 *Прогноз на завтра* — средняя, мин и макс температура
📆 *Прогноз на неделю* — погода на 7 дней вперёд
💨 *Реальные порывы ветра* — точные данные с учётом усилений
🌧️ *Учёт осадков* — количество мм в час/день
📊 *Анализ рисков* — оценка опасности для мотоциклиста (0-10)
💡 *Персональные рекомендации* — конкретные советы по поведению
🛡️ *Рекомендации по экипировке* — что надеть в зависимости от погоды
🕐 *Лучшее время для поездки* — когда безопаснее всего выезжать
🌙 *Определение освещённости* — Светло / Темно (с учётом сезона)

═══════════════════════
*📡 ИСТОЧНИКИ ДАННЫХ:*
• OpenWeatherMap — текущая погода

*🖥️ ПЛАТФОРМА:*
• Render.com — работает 24/7

*👨‍💻 РАЗРАБОТЧИК:*
• Alexander_K8V

═══════════════════════
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

# ============ ОТПРАВКА ПОГОДЫ ============
def send_weather(chat_id):
    weather = get_weather()
    if not weather:
        bot.send_message(chat_id, "❌ Не удалось получить данные о погоде.")
        return
    
    analysis = analyze_risks(weather)
    
    now = get_minsk_time()
    feels_like = analysis.get('feels_like', weather.get('feels_like', weather.get('temp', 0)))
    light_level = get_light_level()
    
    weather_desc = weather.get('condition', '').replace('🌦️', '').replace('🌧️', '').replace('☀️', '').replace('⛅', '').replace('☁️', '').replace('🌫️', '').replace('❄️', '').replace('⛈️', '').replace('🌤️', '').strip()
    
    risk_emoji = analysis['color']
    
    rain_info = ""
    if weather.get('rain_1h', 0) > 0:
        rain_info = f" 🌧️{weather.get('rain_1h', 0):.1f} мм/ч"
    elif weather.get('snow_1h', 0) > 0:
        rain_info = f" ❄️{weather.get('snow_1h', 0):.1f} мм/ч"
    
    visibility_info = ""
    visibility = weather.get('visibility', 10000)
    if visibility < 2000:
        visibility_info = f" 🌫️{visibility} м"
    
    wind_speed = weather.get('wind_speed', 0)
    wind_desc = get_wind_description(wind_speed)
    wind_feeling = get_wind_feeling(wind_speed)
    temp_desc = get_temp_description(feels_like)
    gear_rec = get_gear_recommendation(feels_like)
    best_time = get_best_time()
    
    if weather.get('wind_gust', 0) > wind_speed:
        wind_line = f"💨 *Ветер:* {wind_speed} м/с (порывы до {weather.get('wind_gust', 0)} м/с, {wind_desc}) — {wind_feeling}"
    else:
        wind_line = f"💨 *Ветер:* {wind_speed} м/с ({wind_desc}) — {wind_feeling}"
    
    msg = f"""
{risk_emoji} *MotoWeather Минск* — *сейчас {now}*

{light_level}
🌡️ *Температура:* {weather.get('temp', 0)}°C (ощущается как {feels_like}°C, {temp_desc})
{wind_line}
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
    
    msg += f"\n*🛡️ Экипировка:* {gear_rec}"
    msg += f"\n*{best_time}*"
    
    bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=get_after_weather_keyboard())

def send_forecast(chat_id):
    forecast = get_forecast_tomorrow()
    if not forecast:
        bot.send_message(chat_id, "❌ Не удалось получить прогноз на завтра.")
        return
    
    analysis = analyze_risks(forecast, is_forecast=True)
    
    risk_emoji = analysis['color']
    
    rain_info = ""
    if forecast.get('rain_total', 0) > 0:
        rain_info = f" 🌧️{forecast.get('rain_total', 0):.1f} мм (за день)"
    
    wind_speed = forecast.get('wind_speed', 0)
    wind_desc = get_wind_description(wind_speed)
    wind_feeling = get_wind_feeling(wind_speed)
    avg_temp = forecast.get('temp_avg', 0)
    gear_rec = get_gear_recommendation(avg_temp)
    
    if forecast.get('wind_gust', 0) > wind_speed:
        wind_line = f"💨 *Ветер:* {wind_speed} м/с (порывы до {forecast.get('wind_gust', 0)} м/с, {wind_desc}) — {wind_feeling}"
    else:
        wind_line = f"💨 *Ветер:* {wind_speed} м/с ({wind_desc}) — {wind_feeling}"
    
    msg = f"""
{risk_emoji} *MotoWeather Минск* — *завтра {forecast.get('date', 'завтра')}*

🌡️ *Средняя температура:* {avg_temp}°C (мин {forecast.get('temp_min', 0)}°C / макс {forecast.get('temp_max', 0)}°C)
{wind_line}
{forecast.get('condition', '')}{rain_info}

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
    
    msg += f"\n*🛡️ Экипировка:* {gear_rec}"
    
    bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=get_after_weather_keyboard())

def send_weekly(chat_id):
    weekly = get_weekly_forecast()
    if not weekly:
        bot.send_message(chat_id, "❌ Не удалось получить прогноз на неделю.")
        return
    
    msg = f"""
📆 *ПРОГНОЗ НА НЕДЕЛЮ (Минск)*

"""
    
    for day in weekly:
        temp_str = f"{day['temp_min']}°...{day['temp_max']}°"
        wind_str = f"{day['wind_speed']} м/с"
        rain_str = f" 🌧️{day['rain_total']:.1f}мм" if day['rain_total'] > 0 else ""
        msg += f"🗓️ *{day['weekday']}* {day['date']}: {day['condition']} {temp_str} | 💨 {wind_str}{rain_str}\n"
    
    windy_days = [d for d in weekly if d['wind_speed'] > 10]
    if windy_days:
        windy_names = ", ".join([d['weekday'] for d in windy_days])
        msg += f"\n💡 *Внимание:* Сильный ветер ({windy_names}) — будьте осторожны!"
    
    rainy_days = [d for d in weekly if d['is_rain']]
    if rainy_days:
        rainy_names = ", ".join([d['weekday'] for d in rainy_days])
        msg += f"\n☔ *Дождь:* {rainy_names} — возьмите дождевик!"
    
    bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=get_after_weather_keyboard())

# ============ ВЕБ-СЕРВЕР ДЛЯ ПИНГА ============
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
    print("✅ Добавлен прогноз на неделю")
    print("✅ Добавлена сезонная корректировка дня/ночи")
    print("✅ Добавлено описание ощущения ветра")
    print("✅ Веб-сервер для пинга: https://moto-weather-bot.onrender.com/health")
    print("✅ Часовой пояс: Минск (UTC+3)")
    print("📡 Бот готов к работе")
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    bot.infinity_polling()
