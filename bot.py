import telebot
import requests
import json
import os
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

# ============ РАБОТА С ФАЙЛОМ ПОЛЬЗОВАТЕЛЕЙ ============
USERS_FILE = "users.json"

def load_users():
    """Загружает список пользователей из файла"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_user(user_id):
    """Сохраняет пользователя в файл, если его там нет"""
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        with open(USERS_FILE, "w") as f:
            json.dump(users, f)
        return True
    return False

def get_users_count():
    """Возвращает количество пользователей"""
    return len(load_users())

# ============ ЧАСОВОЙ ПОЯС МИНСКА ============
MINSK_TZ = timezone(timedelta(hours=3))

def get_minsk_time():
    return datetime.now(MINSK_TZ).strftime("%H:%M")

def get_minsk_hour():
    return datetime.now(MINSK_TZ).hour

# ============ ПОЛУЧЕНИЕ ПОГОДЫ ИЗ OPENWEATHERMAP ============
def get_weather():
    """Получает погоду для Минска из OpenWeatherMap"""
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat=53.9045&lon=27.5615&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("cod") != 200:
            print(f"Ошибка OpenWeatherMap: {data.get('message', 'Неизвестная ошибка')}")
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
            "description": weather_desc
        }
        
    except requests.exceptions.Timeout:
        print("Ошибка: Таймаут при запросе к OpenWeatherMap")
        return None
    except requests.exceptions.ConnectionError:
        print("Ошибка: Нет соединения с OpenWeatherMap")
        return None
    except Exception as e:
        print(f"Ошибка получения погоды: {e}")
        return None

# ============ АНАЛИЗ РИСКОВ ============
def analyze_risks(weather):
    risks = []
    score = 0
    recommendations = []
    
    wind_gust = weather.get("wind_gust", 0)
    wind_speed = weather.get("wind_speed", 0)
    temp = weather.get("temp", 0)
    feels_like = weather.get("feels_like", temp)
    rain_1h = weather.get("rain_1h", 0)
    snow_1h = weather.get("snow_1h", 0)
    visibility = weather.get("visibility", 10000)
    is_rain = weather.get("is_rain", False)
    is_thunder = weather.get("is_thunder", False)
    is_night = weather.get("is_night", False)
    
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
    elif snow_1h > 0:
        risks.append(f"❄️ Снег ({snow_1h:.1f} мм/ч) - очень скользко!")
        score += 4
        recommendations.append("🐢 Снизьте скорость до минимума, избегайте резких манёвров")
    elif rain_1h > 2.5:
        risks.append(f"🌧️ СИЛЬНЫЙ ДОЖДЬ ({rain_1h:.1f} мм/ч) - плохая видимость!")
        score += 4
        recommendations.append("🐢 Увеличьте дистанцию, снизьте скорость")
    elif rain_1h > 0.5:
        risks.append(f"🌧️ Дождь ({rain_1h:.1f} мм/ч) - дорога мокрая")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию, избегайте резких манёвров")
    elif is_rain:
        risks.append("🌧️ Дождь (дорога скользкая)")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию, избегайте резких манёвров")
    
    if visibility < 200:
        risks.append(f"🌫️ КРИТИЧЕСКИЙ ТУМАН (видимость {visibility} м)!")
        score += 5
        recommendations.append("🚫 НЕ ВЫЕЗЖАЙТЕ! Остановитесь в безопасном месте")
    elif visibility < 500:
        risks.append(f"🌫️ Сильный туман (видимость {visibility} м)")
        score += 3
        recommendations.append("🌫️ Включите противотуманки, снизьте скорость до минимума")
    elif visibility < 1000:
        risks.append(f"🌫️ Туман (видимость {visibility} м)")
        score += 2
        recommendations.append("🌫️ Включите противотуманки, держите дистанцию")
    elif visibility < 2000:
        risks.append(f"🌫️ Лёгкий туман (видимость {visibility} м)")
        score += 1
        recommendations.append("💡 Включите ближний свет, будьте внимательны")
    
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
    
    if is_night:
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
    # Сохраняем пользователя
    user_id = message.chat.id
    save_user(user_id)
    
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
    # Тоже сохраняем пользователя (на всякий случай)
    save_user(message.chat.id)
    bot.send_message(message.chat.id, "⏳ Загружаю данные из OpenWeatherMap...")
    send_weather(message.chat.id)

@bot.message_handler(commands=['stats'])
def stats_command(message):
    """Показывает количество пользователей (только для админа)"""
    # Замените на ваш Telegram ID
    ADMIN_ID = 8930836312  # ВСТАВЬТЕ ВАШ ID
    
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
        # Сохраняем пользователя при нажатии кнопки
        save_user(call.message.chat.id)
        
        if call.data == "weather":
            bot.answer_callback_query(call.id, "⏳ Загружаю прогноз...")
            send_weather(call.message.chat.id)
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
• 🌡️ Реальная погода (температура, ветер, влажность)
• 💨 Реальные порывы ветра
• 🌧️ Учёт осадков в мм (сила дождя)
• 🌫️ Учёт видимости (туман)
• 📊 Анализ рисков для мотоциклиста
• 💡 Персональные рекомендации
• 🌙 Учёт времени суток

*Источник данных:* OpenWeatherMap (реальный API)
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
        bot.send_message(
            chat_id, 
            "❌ Не удалось получить данные о погоде.\n"
            "Проверьте API-ключ или попробуйте позже."
        )
        return
    
    analysis = analyze_risks(weather)
    
    now = get_minsk_time()
    feels_like = weather.get('feels_like', weather.get('temp', 0))
    
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
{risk_emoji} *MotoWeather Минск*

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
    
    bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=get_after_weather_keyboard())

# ============ ЗАПУСК ============
if __name__ == "__main__":
    print("🏍️ MotoWeather Бот запущен!")
    print("✅ Источник: OpenWeatherMap")
    print("✅ Учтены: осадки в мм, видимость")
    print("✅ Добавлен подсчёт пользователей")
    print("✅ Файл users.json будет создан автоматически")
    print("📡 Бот готов к работе")
    bot.infinity_polling()
EOF
