import telebot
import requests
import json
import os
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============ ТОКЕН БОТА ============
BOT_TOKEN = "8726317506:AAFTww4YFYu76GPuy4ZfSbz5MwoiLtAdTK8"
if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# ============ ПОЛУЧЕНИЕ ПОГОДЫ (wttr.in) ============
def get_weather():
    """Получает погоду для Минска из wttr.in (без API-ключа)"""
    try:
        url = "https://wttr.in/Minsk?format=j1&lang=ru"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        current = data["current_condition"][0]
        
        temp = int(current["temp_C"])
        wind_speed = int(current["windspeedKmph"])
        humidity = int(current["humidity"])
        pressure = int(current["pressure"]) // 1.333
        weather_desc = current["weatherDesc"][0]["value"]
        
        condition = weather_desc
        is_rain = "дождь" in condition.lower() or "ливень" in condition.lower()
        is_thunder = "гроза" in condition.lower()
        wind_gust = int(wind_speed * 1.4)
        
        current_hour = datetime.now().hour
        is_night = current_hour < 6 or current_hour > 20
        
        return {
            "temp": temp,
            "condition": condition,
            "wind_speed": wind_speed,
            "wind_gust": wind_gust,
            "humidity": humidity,
            "pressure": pressure,
            "is_rain": is_rain,
            "is_thunder": is_thunder,
            "is_night": is_night,
            "source": "wttr.in",
            "timestamp": datetime.now().strftime("%H:%M"),
            "description": weather_desc
        }
    except Exception as e:
        print(f"Ошибка получения погоды: {e}")
        return None

# ============ АНАЛИЗ РИСКОВ ============
def analyze_risks(weather):
    risks = []
    score = 0
    
    wind_gust = weather.get("wind_gust", 0)
    wind_speed = weather.get("wind_speed", 0)
    
    if wind_gust > 20:
        risks.append(f"🌪️ КРИТИЧЕСКИЙ ВЕТЕР (порывы до {wind_gust:.0f} м/с)!")
        score += 5
    elif wind_gust > 15:
        risks.append(f"💨 Сильный ветер (порывы до {wind_gust:.0f} м/с)")
        score += 3
    elif wind_speed > 10:
        risks.append(f"🌬️ Умеренный ветер {wind_speed:.0f} м/с")
        score += 1
    
    if weather.get("is_thunder", False):
        risks.append("⚡ ГРОЗА! Категорически запрещено")
        score += 5
    elif weather.get("is_rain", False):
        risks.append("🌧️ Дождь (дорога скользкая)")
        score += 2
    
    temp = weather.get("temp", 0)
    if temp < 5:
        risks.append(f"🥶 Очень холодно ({temp}°C)")
        score += 3
    elif temp < 10:
        risks.append(f"❄️ Холодно ({temp}°C)")
        score += 1
    elif temp > 35:
        risks.append(f"🔥 Очень жарко ({temp}°C)")
        score += 2
    
    if weather.get("is_night", False):
        risks.append("🌙 Ночное время - плохая видимость")
        score += 2
    
    if score >= 8:
        verdict = "⛔ ОПАСНОСТЬ! Категорически НЕ РЕКОМЕНДУЕТСЯ"
    elif score >= 5:
        verdict = "⚠️ РИСКОВАННО - только с большой осторожностью"
    elif score >= 2:
        verdict = "🟡 УМЕРЕННЫЙ РИСК - можно, но будьте внимательны"
    else:
        verdict = "✅ БЕЗОПАСНО - отличная погода для поездки!"
    
    return {"score": min(score, 10), "verdict": verdict, "risks": risks}

# ============ КЛАВИАТУРА ============
def get_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 Обновить", callback_data="update"),
        InlineKeyboardButton("🏍️ Советы", callback_data="tips")
    )
    markup.row(
        InlineKeyboardButton("👨‍💻 О разработчике", callback_data="about")
    )
    return markup

# ============ КОМАНДЫ БОТА ============
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🏍️ *MotoWeather Минск*\n\n"
        "Я анализирую погоду для мотоциклистов!\n"
        "Отправьте /weather чтобы узнать прогноз.\n\n"
        "👨‍💻 *Разработчик:* K8V",
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )

@bot.message_handler(commands=['weather'])
def weather_command(message):
    bot.send_message(message.chat.id, "⏳ Загружаю данные...")
    send_weather(message.chat.id)

@bot.message_handler(commands=['about'])
def about_command(message):
    about_text = """
👨‍💻 *О разработчике*

*Имя:* K8V
*Проект:* MotoWeather Минск

Бот создан для мотоциклистов, чтобы анализировать погоду и оценивать риски для безопасных поездок.

*Источник данных:* wttr.in (бесплатный API)
*Платформа:* Render.com (24/7)

🏍️ *Берегите себя на дороге!*
"""
    bot.send_message(message.chat.id, about_text, parse_mode="Markdown")

# ============ ОБРАБОТКА КНОПОК (БЕЗ ОШИБОК) ============
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        if call.data == "update":
            # Убираем bot.answer_callback_query() — это вызывает ошибку
            send_weather(call.message.chat.id)
        elif call.data == "tips":
            tips = """
🏍️ *Советы для мотоциклистов:*

🟢 *Хорошая погода:*
• Проверьте шины и свет
• Надевайте защитную экипировку

🟡 *Ветер:*
• Держите руль крепче
• Снизьте скорость

🔴 *Дождь:*
• Увеличьте дистанцию
• Избегайте резких манёвров

⚡ *Гроза:*
• НЕМЕДЛЕННО остановитесь
• Найдите укрытие

*Берегите себя!* 🏍️
"""
            bot.send_message(call.message.chat.id, tips, parse_mode="Markdown")
        elif call.data == "about":
            about_text = """
👨‍💻 *О разработчике*

*Имя:* K8V
*Проект:* MotoWeather Минск

Бот создан для мотоциклистов, чтобы анализировать погоду и оценивать риски для безопасных поездок.

*Источник данных:* wttr.in (бесплатный API)
*Платформа:* Render.com (24/7)

🏍️ *Берегите себя на дороге!*
"""
            bot.send_message(call.message.chat.id, about_text, parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка в callback: {e}")

def send_weather(chat_id):
    weather = get_weather()
    if not weather:
        bot.send_message(chat_id, "❌ Не удалось получить данные о погоде. Попробуйте позже.")
        return
    
    analysis = analyze_risks(weather)
    
    now = datetime.now().strftime("%H:%M")
    
    msg = f"""
🏍️ *MotoWeather Минск*
🕐 {now} | {weather.get('condition', '')}

═══════════════════════
🌡️ *Температура:* {weather.get('temp', 0)}°C
💨 *Ветер:* {weather.get('wind_speed', 0):.0f} м/с (порывы до {weather.get('wind_gust', 0):.0f})
💧 *Влажность:* {weather.get('humidity', 0)}%
📊 *Давление:* {weather.get('pressure', 0)} мм рт.ст.
🌙 *Время суток:* {'🌙 Ночь' if weather.get('is_night', False) else '☀️ День'}

═══════════════════════
*ВЕРДИКТ:* {analysis['verdict']}
"""
    if analysis["risks"]:
        msg += "\n*⚠️ Факторы риска:*\n"
        for risk in analysis["risks"]:
            msg += f"• {risk}\n"
    else:
        msg += "\n✅ *Нет факторов риска*\n"
    
    msg += f"\n📊 *Уровень риска:* {analysis['score']}/10"
    msg += f"\n📡 *Источник:* {weather.get('source', 'Неизвестно')}"
    if weather.get("description"):
        msg += f"\n📝 *Описание:* {weather.get('description')}"
    
    msg += f"\n\n👨‍💻 *Разработчик:* K8V"
    
    bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=get_keyboard())

# ============ ЗАПУСК ============
if __name__ == "__main__":
    print("🏍️ MotoWeather Бот запущен!")
    print("✅ Используется wttr.in (без API-ключа)")
    print("👨‍💻 Разработчик: K8V")
    print("📡 Бот готов к работе")
    bot.infinity_polling()
EOF
