import telebot
import requests
import json
import os
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Загружаем переменные окружения (для Render)
BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")

# Если переменных нет — пробуем загрузить из config.json (для локального запуска)
if not BOT_TOKEN:
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
            BOT_TOKEN = config.get("bot_token")
            YANDEX_API_KEY = config.get("yandex_key")
    except:
        pass

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    print("Установите переменную окружения BOT_TOKEN или создайте config.json")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# ============ ПОЛУЧЕНИЕ ПОГОДЫ ОТ ЯНДЕКСА ============
def get_weather():
    """Получает данные о погоде в Минске от Яндекс.Погода (бесплатный тариф)"""
    try:
        url = "https://api.weather.yandex.ru/graphql/query"
        headers = {
            "X-Yandex-Weather-Key": YANDEX_API_KEY,
            "Content-Type": "application/json"
        }
        
        query = {
            "query": """
            {
              weatherByPoint(request: { lat: 53.9045, lon: 27.5615 }) {
                now {
                  temperature
                  condition
                  windSpeed
                  windGust
                  pressureMm
                  humidity
                  daytime
                }
                forecast {
                  days {
                    parts {
                      partName
                      temperature
                      condition
                      windSpeed
                      windGust
                    }
                  }
                }
              }
            }
            """
        }
        
        response = requests.post(url, headers=headers, json=query, timeout=10)
        data = response.json()
        
        if "errors" in data:
            print(f"Ошибка API Яндекса: {data['errors']}")
            return None
        
        now_data = data["data"]["weatherByPoint"]["now"]
        
        condition_map = {
            "clear": "☀️ Ясно",
            "partly-cloudy": "⛅ Малооблачно",
            "cloudy": "☁️ Облачно",
            "overcast": "☁️ Пасмурно",
            "light-rain": "🌦️ Небольшой дождь",
            "rain": "🌧️ Дождь",
            "heavy-rain": "🌧️ Сильный дождь",
            "showers": "🌧️ Ливень",
            "thunderstorm": "⛈️ Гроза",
            "thunderstorm-with-rain": "⛈️ Гроза с дождём",
            "snow": "❄️ Снег",
            "light-snow": "🌨️ Небольшой снег",
            "heavy-snow": "❄️ Сильный снег",
            "wet-snow": "🌨️ Мокрый снег",
        }
        
        condition_code = now_data.get("condition", "")
        condition_text = condition_map.get(condition_code, condition_code)
        
        rain_codes = ["light-rain", "rain", "heavy-rain", "showers", "thunderstorm", 
                      "thunderstorm-with-rain", "wet-snow"]
        is_rain = condition_code in rain_codes
        thunder_codes = ["thunderstorm", "thunderstorm-with-rain"]
        is_thunder = condition_code in thunder_codes
        is_night = now_data.get("daytime") == "n"
        
        forecast_parts = []
        forecast_data = data["data"]["weatherByPoint"]["forecast"]
        if forecast_data and forecast_data.get("days"):
            today = forecast_data["days"][0]
            for part in today.get("parts", [])[:6]:
                forecast_parts.append({
                    "part": part.get("partName", ""),
                    "temp": part.get("temperature", 0),
                    "wind": part.get("windSpeed", 0),
                    "condition": condition_map.get(part.get("condition", ""), part.get("condition", ""))
                })
        
        return {
            "temp": now_data.get("temperature", 0),
            "wind_speed": now_data.get("windSpeed", 0),
            "wind_gust": now_data.get("windGust", now_data.get("windSpeed", 0) * 1.3),
            "pressure": now_data.get("pressureMm", 0),
            "humidity": now_data.get("humidity", 0),
            "condition": condition_text,
            "is_rain": is_rain,
            "is_thunder": is_thunder,
            "is_night": is_night,
            "source": "Яндекс.Погода",
            "timestamp": datetime.now().strftime("%H:%M"),
            "forecast": forecast_parts
        }
        
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

# ============ АНАЛИЗ РИСКОВ ============
def analyze_risks(weather):
    risks = []
    score = 0
    
    wind_gust = weather.get("wind_gust", 0)
    wind_speed = weather.get("wind_speed", 0)
    
    if wind_gust > 20:
        risks.append(f"🌪️ КРИТИЧЕСКИЙ ВЕТЕР (порывы до {wind_gust:.0f} м/с)")
        score += 5
    elif wind_gust > 15:
        risks.append(f"💨 Сильный ветер (порывы до {wind_gust:.0f} м/с)")
        score += 3
    elif wind_speed > 10:
        risks.append(f"🌬️ Ветер {wind_speed:.0f} м/с")
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
        risks.append(f"🔥 Жарко ({temp}°C)")
        score += 2
    
    if weather.get("is_night", False):
        risks.append("🌙 Ночь - плохая видимость")
        score += 2
    
    if score >= 8:
        verdict = "⛔ ОПАСНОСТЬ! НЕ РЕКОМЕНДУЕТСЯ"
    elif score >= 5:
        verdict = "⚠️ РИСКОВАННО - с осторожностью"
    elif score >= 2:
        verdict = "🟡 УМЕРЕННЫЙ РИСК"
    else:
        verdict = "✅ БЕЗОПАСНО - отличная погода!"
    
    return {"score": min(score, 10), "verdict": verdict, "risks": risks}

# ============ КЛАВИАТУРА ============
def get_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 Обновить", callback_data="update"),
        InlineKeyboardButton("🏍️ Советы", callback_data="tips")
    )
    markup.row(
        InlineKeyboardButton("📊 Прогноз", callback_data="forecast")
    )
    return markup

# ============ КОМАНДЫ ============
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🏍️ *MotoWeather Минск*\n\n"
        "Я анализирую погоду для мотоциклистов\n"
        "Нажмите *Обновить* для прогноза",
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )

@bot.message_handler(commands=['weather'])
def weather_command(message):
    bot.send_message(message.chat.id, "⏳ Загружаю...")
    send_weather(message.chat.id)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "update":
        bot.answer_callback_query(call.id, "⏳ Обновляю...")
        send_weather(call.message.chat.id)
    elif call.data == "tips":
        tips = """
🏍️ *Советы:*

🟢 *Хорошая погода:*
• Проверьте шины и свет
• Надевайте экипировку

🟡 *Ветер:*
• Держите руль крепче
• Снизьте скорость

🔴 *Дождь:*
• Увеличьте дистанцию
• Без резких манёвров

⚡ *Гроза:*
• НЕМЕДЛЕННО остановитесь
• Найдите укрытие

*Берегите себя!* 🏍️
"""
        bot.send_message(call.message.chat.id, tips, parse_mode="Markdown")
    elif call.data == "forecast":
        bot.answer_callback_query(call.id, "⏳ Загружаю прогноз...")
        weather = get_weather()
        if weather and weather.get("forecast"):
            msg = "📊 *Прогноз на сегодня:*\n═══════════════════════\n"
            for part in weather["forecast"]:
                msg += f"{part.get('part', '')}: {part.get('temp', 0)}°C, 💨{part.get('wind', 0)} м/с\n"
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
        else:
            bot.send_message(call.message.chat.id, "❌ Прогноз недоступен")

def send_weather(chat_id):
    weather = get_weather()
    if not weather:
        bot.send_message(chat_id, "❌ Ошибка получения данных")
        return
    
    analysis = analyze_risks(weather)
    
    now = datetime.now().strftime("%H:%M")
    emoji = "⛈️" if weather.get("is_thunder") else "🌧️" if weather.get("is_rain") else "☀️"
    
    msg = f"""
🏍️ *MotoWeather Минск*
🕐 {now} | {emoji} {weather.get('condition', '')}

═══════════════════════
🌡️ *Температура:* {weather.get('temp', 0)}°C
💨 *Ветер:* {weather.get('wind_speed', 0):.0f} м/с (порывы до {weather.get('wind_gust', 0):.0f})
💧 *Влажность:* {weather.get('humidity', 0)}%
📊 *Давление:* {weather.get('pressure', 0)} мм рт.ст.

═══════════════════════
*ВЕРДИКТ:* {analysis['verdict']}
"""
    if analysis["risks"]:
        msg += "\n⚠️ *Риски:*\n"
        for risk in analysis["risks"]:
            msg += f"• {risk}\n"
    
    msg += f"\n📊 *Уровень риска:* {analysis['score']}/10"
    msg += f"\n📡 *Источник:* {weather.get('source', '')}"
    
    bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=get_keyboard())

# ============ ЗАПУСК ============
if __name__ == "__main__":
    print("🏍️ MotoWeather Бот запущен!")
    print(f"✅ Источник: Яндекс.Погода")
    print("📡 Бот готов к работе")
    bot.infinity_polling()
