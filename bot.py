import telebot
import requests
import json
import os
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============ ТОКЕН БОТА ============
BOT_TOKEN = "8726317506:AAFTww4YFYu76GPuy4ZfSbz5MwoiLtAdTK8"
if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# ============ ЧАСОВОЙ ПОЯС МИНСКА ============
MINSK_TZ = timedelta(hours=3)

def get_minsk_time():
    return (datetime.utcnow() + MINSK_TZ).strftime("%H:%M")

def get_minsk_hour():
    return (datetime.utcnow() + MINSK_TZ).hour

# ============ РАСШИФРОВЩИК ПОГОДЫ ============
def parse_weather_condition(condition_text):
    condition_lower = condition_text.lower()
    
    thunder_keywords = ["гроз", "thunder", "storm", "молния", "lightning"]
    is_thunder = any(word in condition_lower for word in thunder_keywords)
    
    rain_keywords = [
        "дожд", "rain", "ливень", "shower", "морос", "drizzle",
        "patchy rain", "мокрый", "wet", "влажн", "осадк"
    ]
    is_rain = any(word in condition_lower for word in rain_keywords)
    
    if is_thunder:
        return {"condition": "⛈️ Гроза", "is_rain": True, "is_thunder": True}
    elif "снег" in condition_lower or "snow" in condition_lower:
        return {"condition": "❄️ Снег", "is_rain": False, "is_thunder": False}
    elif "туман" in condition_lower or "fog" in condition_lower or "mist" in condition_lower:
        return {"condition": "🌫️ Туман", "is_rain": False, "is_thunder": False}
    elif is_rain:
        if "сильн" in condition_lower or "heavy" in condition_lower:
            return {"condition": "🌧️ Сильный дождь", "is_rain": True, "is_thunder": False}
        elif "небольш" in condition_lower or "light" in condition_lower or "patchy" in condition_lower:
            return {"condition": "🌦️ Небольшой дождь", "is_rain": True, "is_thunder": False}
        else:
            return {"condition": "🌧️ Дождь", "is_rain": True, "is_thunder": False}
    elif "ясно" in condition_lower or "clear" in condition_lower or "солнеч" in condition_lower:
        return {"condition": "☀️ Ясно", "is_rain": False, "is_thunder": False}
    elif "облач" in condition_lower or "cloud" in condition_lower:
        if "пасмур" in condition_lower or "overcast" in condition_lower:
            return {"condition": "☁️ Пасмурно", "is_rain": False, "is_thunder": False}
        else:
            return {"condition": "⛅ Облачно", "is_rain": False, "is_thunder": False}
    else:
        return {"condition": f"🌤️ {condition_text}", "is_rain": False, "is_thunder": False}

# ============ ПОЛУЧЕНИЕ ПОГОДЫ ============
def get_weather():
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
        
        parsed = parse_weather_condition(weather_desc)
        wind_gust = int(wind_speed * 1.4)
        
        current_hour = get_minsk_hour()
        is_night = current_hour < 6 or current_hour > 20
        
        # Ощущаемая температура (упрощённая формула)
        feels_like = int(temp - (wind_speed * 0.2))
        if feels_like < -10:
            feels_like = -10
        
        return {
            "temp": temp,
            "feels_like": feels_like,
            "condition": parsed["condition"],
            "wind_speed": wind_speed,
            "wind_gust": wind_gust,
            "humidity": humidity,
            "pressure": pressure,
            "is_rain": parsed["is_rain"],
            "is_thunder": parsed["is_thunder"],
            "is_night": is_night,
            "source": "wttr.in",
            "timestamp": get_minsk_time()
        }
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

# ============ РАСШИРЕННЫЙ АНАЛИЗ РИСКОВ ============
def analyze_risks(weather):
    risks = []
    score = 0
    recommendations = []
    
    wind_gust = weather.get("wind_gust", 0)
    wind_speed = weather.get("wind_speed", 0)
    temp = weather.get("temp", 0)
    feels_like = weather.get("feels_like", temp)
    
    # ===== ВЕТЕР =====
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
    
    # ===== ОСАДКИ =====
    if weather.get("is_thunder", False):
        risks.append("⚡ ГРОЗА! Категорически запрещено")
        score += 5
        recommendations.append("🚫 НЕМЕДЛЕННО остановитесь, найдите укрытие")
    elif weather.get("is_rain", False):
        risks.append("🌧️ Дождь (дорога скользкая)")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию, избегайте резких манёвров")
    
    # ===== ТЕМПЕРАТУРА =====
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
    
    # ===== НОЧЬ =====
    if weather.get("is_night", False):
        risks.append("🌙 Ночное время - плохая видимость")
        score += 2
        recommendations.append("💡 Включите свет, снизьте скорость")
    
    # ===== ДОПОЛНИТЕЛЬНО =====
    if "туман" in weather.get("condition", "").lower():
        recommendations.append("🌫️ Включите противотуманки, держите дистанцию")
    
    # ===== ВЕРДИКТ С ЦВЕТОМ =====
    if score >= 8:
        verdict = "⛔ ОПАСНОСТЬ! НЕ РЕКОМЕНДУЕТСЯ"
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
def get_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 Обновить", callback_data="update"),
        InlineKeyboardButton("🏍️ Советы", callback_data="tips")
    )
    return markup

# ============ КОМАНДЫ ============
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🏍️ *MotoWeather Минск*\n\n"
        "Я анализирую погоду для мотоциклистов!\n"
        "Отправьте /weather для прогноза.",
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )

@bot.message_handler(commands=['weather'])
def weather_command(message):
    bot.send_message(message.chat.id, "⏳ Загружаю данные...")
    send_weather(message.chat.id)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        if call.data == "update":
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
            bot.send_message(call.message.chat.id, tips, parse_mode="Markdown")
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
    
    # Цветовой индикатор уровня риска
    risk_emoji = analysis['color']
    
    msg = f"""
🏍️ *MotoWeather Минск* {risk_emoji}
🕐 {now} | {weather.get('condition', '')}

═══════════════════════
🌡️ *Температура:* {weather.get('temp', 0)}°C (ощущается как {feels_like}°C)
💨 *Ветер:* {weather.get('wind_speed', 0):.0f} м/с (порывы до {weather.get('wind_gust', 0):.0f})
💧 *Влажность:* {weather.get('humidity', 0)}%
📊 *Давление:* {weather.get('pressure', 0)} мм рт.ст.
🌙 *Время:* {'🌙 Ночь' if weather.get('is_night', False) else '☀️ День'}

═══════════════════════
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
    
    msg += f"\n📡 *Источник:* {weather.get('source', 'Неизвестно')}"
    
    bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=get_keyboard())

# ============ ЗАПУСК ============
if __name__ == "__main__":
    print("🏍️ MotoWeather Бот запущен!")
    print("✅ Источник: wttr.in")
    print("✅ Часовой пояс: Минск (UTC+3)")
    print("📡 Бот готов к работе")
    bot.infinity_polling()
EOF
