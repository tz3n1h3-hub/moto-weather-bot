import telebot
import requests
import json
import os
import time
import threading
import re
import math
from datetime import datetime, timedelta, timezone
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, jsonify

# ============ ТОКЕНЫ ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

if not OPENWEATHER_API_KEY:
    print("❌ ОШИБКА: OPENWEATHER_API_KEY не найден!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ============ ЗАЩИТА ОТ ПОДДЕЛКИ ============
MY_BOT_USERNAME = "MotoWeatherMinskBot"

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
        return "🌿 безветренно"
    elif speed <= 6:
        return "🍃 комфортно, ветер почти не ощущается"
    elif speed <= 10:
        return "🌬️ ощущается, но не мешает"
    elif speed <= 14:
        return "💨 требует внимания на дороге"
    elif speed <= 19:
        return "⚠️ сильно влияет на управление"
    else:
        return "🚫 опасно для езды!"

def get_temp_description(temp):
    if temp >= 30:
        return "очень жарко"
    elif temp >= 25:
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

def get_visibility_rating(vis_m):
    if vis_m >= 10000:
        return "✅ отличная"
    elif vis_m >= 5000:
        return "✅ хорошая"
    elif vis_m >= 2000:
        return "🟡 средняя"
    elif vis_m >= 1000:
        return "🟠 плохая"
    elif vis_m >= 500:
        return "🔴 очень плохая"
    else:
        return "🔴🔴 критичная (туман)"

def format_visibility(vis_m):
    if vis_m >= 10000:
        return "10+ км"
    elif vis_m >= 1000:
        return f"{vis_m / 1000:.1f} км"
    else:
        return f"{vis_m} м"

# ============ ДЕТАЛЬНАЯ ЭКИПИРОВКА ============
def get_detailed_gear(temp, wind_speed, is_night, is_rain, dew_point):
    gear = []
    
    if temp >= 25:
        gear.append("🟢 Лёгкая экипировка с сеткой")
    elif temp >= 18:
        gear.append("🟢 Стандартная экипировка")
    elif temp >= 10:
        gear.append("🟡 Ветрозащита + тёплая подкладка")
    elif temp >= 5:
        gear.append("🟠 Тёплая экипировка")
        gear.append("🔥 Подогрев ручек")
    elif temp >= 0:
        gear.append("🔴 Термобельё + полный подогрев")
    else:
        gear.append("❄️ Зимняя экипировка + подогрев всего")
    
    if wind_speed > 10:
        gear.append("💨 Плотная ветрозащита (сильный ветер)")
    
    if is_night:
        gear.append("💡 Дополнительный свет / светоотражатели")
        gear.append("🪞 Чистый визор (ночная видимость)")
    
    if is_rain:
        gear.append("🌧️ Дождевик / мембрана")
        gear.append("🧤 Водонепроницаемые перчатки")
    elif dew_point is not None and temp - dew_point <= 2:
        gear.append("💧 Антизапотеватель для визора (роса)")
    
    return gear

# ============ РАССВЕТ И ЗАКАТ ============
def get_sun_times(data):
    try:
        sunrise_ts = data.get("sys", {}).get("sunrise")
        sunset_ts = data.get("sys", {}).get("sunset")
        
        if sunrise_ts and sunset_ts:
            sunrise = datetime.fromtimestamp(sunrise_ts, tz=MINSK_TZ).strftime("%H:%M")
            sunset = datetime.fromtimestamp(sunset_ts, tz=MINSK_TZ).strftime("%H:%M")
            return sunrise, sunset
        return None, None
    except:
        return None, None

# ============ ЛУЧШЕЕ ВРЕМЯ ============
def get_best_time(sunrise=None, sunset=None):
    hour = get_minsk_hour()
    now = datetime.now(MINSK_TZ)
    
    if 9 <= hour <= 18:
        return "🕐 Лучшее время для поездки: с 9:00 до 18:00 ☀️"
    elif 7 <= hour <= 9:
        return "🕐 Утро (с 7:00 до 9:00) — будьте осторожны 🌅"
    elif 18 <= hour <= 22:
        if sunset:
            return f"🕐 Вечер — закат был в {sunset}, включите свет 🌆"
        return "🕐 Вечер (с 18:00 до 22:00) — включите свет 🌆"
    elif 22 <= hour or hour <= 5:
        if sunrise:
            sunrise_dt = datetime.strptime(sunrise, "%H:%M").replace(
                year=now.year, month=now.month, day=now.day, tzinfo=MINSK_TZ
            )
            if now.hour >= 22:
                sunrise_dt += timedelta(days=1)
            elif now.hour < 6 and sunrise_dt < now:
                sunrise_dt += timedelta(days=1)
            
            delta = sunrise_dt - now
            hours = int(delta.total_seconds() // 3600)
            minutes = int((delta.total_seconds() % 3600) // 60)
            return f"🕐 Ночь — до рассвета (~{sunrise}) ещё {hours} ч {minutes} мин 🌙"
        return "🕐 Ночь (с 22:00 до 6:00) — только с хорошим светом 🌙"
    else:
        return "🕐 Раннее утро (с 5:00 до 7:00) — будьте внимательны 🌄"

# ============ ТРЕНД ЗА 3 ЧАСА ============
def get_trend(chat_id):
    try:
        cache_buster = int(time.time())
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat=53.9045&lon=27.5615&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&cnt=2&_={cache_buster}"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("cod") != "200":
            return None
        
        if not data.get("list"):
            return None
        
        current = data["list"][0]
        
        owm_url = f"https://api.openweathermap.org/data/2.5/weather?lat=53.9045&lon=27.5615&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru"
        owm_response = requests.get(owm_url, timeout=10)
        owm_data = owm_response.json()
        
        if owm_data.get("cod") != 200:
            return None
        
        current_temp = int(owm_data["main"]["temp"])
        current_wind = int(owm_data["wind"]["speed"])
        forecast_temp = int(current["main"]["temp"])
        forecast_wind = int(current["wind"]["speed"])
        
        temp_diff = forecast_temp - current_temp
        wind_diff = forecast_wind - current_wind
        
        trend = []
        
        if abs(temp_diff) >= 2:
            if temp_diff > 0:
                trend.append(f"🌡️ Потеплеет на +{temp_diff}°C")
            else:
                trend.append(f"🌡️ Похолодает на {temp_diff}°C")
        else:
            trend.append("🌡️ Температура стабильна")
        
        if abs(wind_diff) >= 3:
            if wind_diff > 0:
                trend.append(f"💨 Ветер усилится на +{wind_diff} м/с")
            else:
                trend.append(f"💨 Ветер ослабнет на {wind_diff} м/с")
        else:
            trend.append("💨 Ветер без изменений")
        
        if "rain" in current:
            trend.append("🌧️ Ожидается дождь")
        elif any("rain" in item for item in data["list"][:2]):
            trend.append("🌧️ Возможен дождь в ближайшие часы")
        else:
            trend.append("☀️ Осадков не ожидается")
        
        return trend
    except Exception as e:
        print(f"Ошибка получения тренда: {e}")
        return None

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

# ============ РАСЧЁТ ВЛАЖНОСТИ ============
def calculate_humidity(temp, dew_point):
    try:
        a, b = 17.27, 237.7
        alpha = ((a * dew_point) / (b + dew_point)) - ((a * temp) / (b + temp))
        humidity = 100 * math.exp(alpha)
        return round(humidity)
    except:
        return None

# ============ ПАРСЕР METAR ============
def parse_clouds(metar_text):
    if "OVC" in metar_text:
        return "☁️", "Пасмурно"
    elif "BKN" in metar_text:
        return "☁️", "Значительная облачность"
    elif "SCT" in metar_text:
        return "⛅", "Облачно с прояснениями"
    elif "FEW" in metar_text:
        return "🌤️", "Малооблачно"
    elif "CAVOK" in metar_text:
        return "🌤️", "Преимущественно ясно"
    elif "NSC" in metar_text or "SKC" in metar_text or "CLR" in metar_text:
        return "🌤️", "Преимущественно ясно"
    else:
        return "⛅", "Облачно"

def parse_visibility(metar_text):
    if "CAVOK" in metar_text:
        return 10000
    if "9999" in metar_text:
        return 10000
    vis_match = re.search(r'\s(\d{4})\s', metar_text)
    if vis_match:
        return int(vis_match.group(1))
    return 10000

def parse_weather_phenomena(metar_text):
    if "TS" in metar_text:
        if "TSRA" in metar_text:
            return "⛈️", "Гроза с дождём", True, True
        elif "TSSN" in metar_text:
            return "⛈️", "Гроза со снегом", False, True
        else:
            return "⛈️", "Гроза", False, True
    
    if "SHRA" in metar_text:
        return "🌧️", "Ливневый дождь", True, False
    if "SHSN" in metar_text:
        return "🌨️", "Ливневый снег", False, False
    
    if "+RA" in metar_text:
        return "🌧️", "Сильный дождь", True, False
    if "RA" in metar_text:
        return "🌧️", "Дождь", True, False
    if "-RA" in metar_text:
        return "🌦️", "Слабый дождь", True, False
    
    if "DZ" in metar_text:
        return "🌦️", "Морось", True, False
    
    if "+SN" in metar_text:
        return "❄️", "Сильный снег", False, False
    if "SN" in metar_text:
        return "❄️", "Снег", False, False
    if "-SN" in metar_text:
        return "🌨️", "Слабый снег", False, False
    
    if "FG" in metar_text:
        return "🌫️", "Туман", False, False
    if "BR" in metar_text:
        return "🌫️", "Дымка", False, False
    if "HZ" in metar_text:
        return "🌫️", "Мгла", False, False
    
    if "GR" in metar_text:
        return "🧊", "Град", False, False
    
    return None, None, False, False

def get_metar_data():
    try:
        url = "https://metar.vatsim.net/UMMS"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            return None
        
        metar_text = response.text.strip()
        print(f"METAR: {metar_text}")
        
        result = {}
        
        wind_match = re.search(r'\b(\d{3})(\d{2,3})(G(\d{2,3}))?(KT|MPS)\b', metar_text)
        if wind_match:
            wind_value = int(wind_match.group(2))
            unit = wind_match.group(5)
            wind_ms = round(wind_value * 0.514444) if unit == "KT" else wind_value
            result["wind_speed"] = wind_ms
            
            if wind_match.group(4):
                gust_value = int(wind_match.group(4))
                gust_ms = round(gust_value * 0.514444) if unit == "KT" else gust_value
                result["wind_gust"] = gust_ms
            else:
                result["wind_gust"] = None
        
        emoji, cloud_text = parse_clouds(metar_text)
        result["cloud_emoji"] = emoji
        result["cloud_text"] = cloud_text
        
        result["visibility"] = parse_visibility(metar_text)
        
        w_emoji, w_text, is_rain, is_thunder = parse_weather_phenomena(metar_text)
        result["weather_emoji"] = w_emoji
        result["weather_text"] = w_text
        result["is_rain"] = is_rain
        result["is_thunder"] = is_thunder
        
        temp_match = re.search(r'\s(M?\d{2})/(M?\d{2})\s', metar_text)
        if temp_match:
            temp_str = temp_match.group(1).replace("M", "-")
            result["temp"] = int(temp_str)
            dew_str = temp_match.group(2).replace("M", "-")
            result["dew_point"] = int(dew_str)
        
        return result
    except Exception as e:
        print(f"Ошибка получения METAR: {e}")
        return None

# ============ РАСЧЁТ ОЩУЩАЕМОЙ ТЕМПЕРАТУРЫ ============
def calculate_feels_like(temp, wind_speed):
    if temp <= 10 and wind_speed > 1.3:
        wind_kmh = wind_speed * 3.6
        feels = 13.12 + 0.6215 * temp - 11.37 * (wind_kmh ** 0.16) + 0.3965 * temp * (wind_kmh ** 0.16)
        return round(feels)
    elif temp >= 27:
        return round(temp + 1)
    return round(temp)

# ============ ПОЛУЧЕНИЕ ТЕКУЩЕЙ ПОГОДЫ ============
def get_weather():
    try:
        cache_buster = int(time.time())
        url = f"https://api.openweathermap.org/data/2.5/weather?lat=53.9045&lon=27.5615&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&_={cache_buster}"
        
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("cod") != 200:
            return None
        
        owm_temp = int(data["main"]["temp"])
        owm_wind = int(data["wind"]["speed"])
        
        sunrise, sunset = get_sun_times(data)
        
        metar = get_metar_data()
        
        if metar:
            temp = metar.get("temp", owm_temp)
            wind_speed = metar.get("wind_speed", owm_wind)
            cloud_emoji = metar.get('cloud_emoji', '⛅')
            cloud_text = metar.get('cloud_text', 'Облачно')
            visibility = metar.get("visibility", 10000)
            weather_text = metar.get("weather_text")
            weather_emoji = metar.get("weather_emoji")
            dew_point = metar.get("dew_point")
            is_rain = metar.get("is_rain", False)
            is_thunder = metar.get("is_thunder", False)
            wind_gust = metar.get("wind_gust")
            gust_source = "METAR" if wind_gust else None
            source_text = "METAR (аэропорт Минск)"
        else:
            temp = owm_temp
            wind_speed = owm_wind
            cloud_emoji = "⛅"
            cloud_text = "—"
            visibility = 10000
            weather_text = None
            weather_emoji = None
            dew_point = None
            is_rain = False
            is_thunder = False
            wind_gust = None
            gust_source = None
            source_text = "OpenWeatherMap"
        
        feels_like = calculate_feels_like(temp, wind_speed)
        is_night = is_night_time()
        
        humidity = None
        if dew_point is not None:
            humidity = calculate_humidity(temp, dew_point)
        
        return {
            "temp": temp,
            "feels_like": feels_like,
            "cloud_emoji": cloud_emoji,
            "cloud_text": cloud_text,
            "weather_text": weather_text,
            "weather_emoji": weather_emoji,
            "dew_point": dew_point,
            "humidity": humidity,
            "wind_speed": wind_speed,
            "wind_gust": wind_gust,
            "gust_source": gust_source,
            "visibility": visibility,
            "is_rain": is_rain,
            "is_thunder": is_thunder,
            "is_night": is_night,
            "sunrise": sunrise,
            "sunset": sunset,
            "source": source_text
        }
    except Exception as e:
        print(f"Ошибка получения погоды: {e}")
        return None

# ============ ПРОГНОЗ НА ЗАВТРА ============
def get_forecast_tomorrow():
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat=53.9045&lon=27.5615&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&cnt=8"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("cod") != "200":
            return None
        
        tomorrow = datetime.now(MINSK_TZ) + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")
        
        temps, wind_speeds, conditions = [], [], []
        rain_total = 0
        
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
            condition, is_rain, is_thunder = "⛈️ Гроза", True, True
        elif most_common >= 500 and most_common < 600:
            condition = "🌧️ Сильный дождь" if most_common >= 502 else "🌧️ Дождь"
            is_rain, is_thunder = True, False
        elif most_common >= 600 and most_common < 700:
            condition, is_rain, is_thunder = "❄️ Снег", False, False
        elif most_common == 800:
            condition, is_rain, is_thunder = "☀️ Ясно", False, False
        elif most_common > 800:
            condition, is_rain, is_thunder = "☁️ Облачно", False, False
        else:
            condition, is_rain, is_thunder = "🌤️ Переменная облачность", False, False
        
        return {
            "date": tomorrow.strftime("%d.%m.%Y"),
            "temp_avg": avg_temp, "temp_max": max_temp, "temp_min": min_temp,
            "wind_speed": avg_wind, "wind_gust": wind_gust,
            "rain_total": round(rain_total, 1),
            "condition": condition, "is_rain": is_rain, "is_thunder": is_thunder
        }
    except Exception as e:
        print(f"Ошибка прогноза: {e}")
        return None

# ============ ПРОГНОЗ НА НЕДЕЛЮ ============
def get_weekly_forecast():
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat=53.9045&lon=27.5615&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&cnt=40"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("cod") != "200":
            return None
        
        days = {}
        today = datetime.now(MINSK_TZ).date()
        
        for item in data["list"]:
            dt = datetime.fromtimestamp(item["dt"], tz=MINSK_TZ)
            date_key = dt.strftime("%Y-%m-%d")
            
            if dt.date() == today:
                continue
            
            if date_key not in days:
                days[date_key] = {"temps": [], "winds": [], "rain": 0, "conditions": [], "date": dt}
            
            days[date_key]["temps"].append(item["main"]["temp"])
            days[date_key]["winds"].append(item["wind"]["speed"])
            if "rain" in item:
                days[date_key]["rain"] += item["rain"].get("3h", 0)
            days[date_key]["conditions"].append(item["weather"][0]["id"])
        
        result = []
        for date_key, data_day in sorted(days.items())[:7]:
            temps, winds, conditions = data_day["temps"], data_day["winds"], data_day["conditions"]
            if not temps:
                continue
            
            avg_temp = int(sum(temps) / len(temps))
            max_temp, min_temp = int(max(temps)), int(min(temps))
            avg_wind = int(sum(winds) / len(winds))
            wind_gust = int(max(winds) * 1.3)
            rain_total = round(data_day["rain"], 1)
            
            most_common = max(set(conditions), key=conditions.count) if conditions else 800
            
            if most_common >= 200 and most_common < 300:
                condition, is_rain, is_thunder = "⛈️", True, True
            elif most_common >= 500 and most_common < 600:
                condition, is_rain, is_thunder = "🌧️", True, False
            elif most_common >= 600 and most_common < 700:
                condition, is_rain, is_thunder = "❄️", False, False
            elif most_common == 800:
                condition, is_rain, is_thunder = "☀️", False, False
            elif most_common > 800:
                condition, is_rain, is_thunder = "☁️", False, False
            else:
                condition, is_rain, is_thunder = "🌤️", False, False
            
            weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            weekday = weekday_names[data_day["date"].weekday()]
            
            result.append({
                "weekday": weekday, "date": data_day["date"].strftime("%d.%m"),
                "condition": condition, "temp_max": max_temp, "temp_min": min_temp,
                "temp_avg": avg_temp, "wind_speed": avg_wind, "wind_gust": wind_gust,
                "rain_total": rain_total, "is_rain": is_rain, "is_thunder": is_thunder
            })
        return result
    except Exception as e:
        print(f"Ошибка недельного прогноза: {e}")
        return None

# ============ АНАЛИЗ РИСКОВ ============
def analyze_risks(weather, is_forecast=False):
    risks = []
    score = 0
    recommendations = []
    
    wind_gust = weather.get("wind_gust") or 0
    wind_speed = weather.get("wind_speed", 0)
    temp = weather.get("temp", 0)
    rain_total = weather.get("rain_total", 0)
    is_rain = weather.get("is_rain", False)
    is_thunder = weather.get("is_thunder", False)
    visibility = weather.get("visibility", 10000)
    dew_point = weather.get("dew_point")
    
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
        risks.append(f"🌧️ СИЛЬНЫЙ ДОЖДЬ ({rain_total:.1f} мм)")
        score += 4
        recommendations.append("🐢 Увеличьте дистанцию, снизьте скорость")
    elif rain_total > 1:
        risks.append(f"🌧️ Дождь ({rain_total:.1f} мм)")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию, избегайте резких манёвров")
    elif is_rain:
        risks.append("🌧️ Дождь (дорога скользкая)")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию, избегайте резких манёвров")
    
    if not is_forecast:
        if visibility < 500:
            risks.append(f"🌫️ КРИТИЧЕСКАЯ ВИДИМОСТЬ ({visibility} м)!")
            score += 5
            recommendations.append("🚫 Остановитесь в безопасном месте")
        elif visibility < 1000:
            risks.append(f"🌫️ Очень плохая видимость ({visibility} м)")
            score += 3
            recommendations.append("🌫️ Включите противотуманки, снизьте скорость")
        elif visibility < 2000:
            risks.append(f"🌫️ Плохая видимость ({visibility} м)")
            score += 2
            recommendations.append("💡 Включите ближний свет")
    
    if not is_forecast and dew_point is not None:
        diff = temp - dew_point
        if diff <= 0:
            risks.append(f"🌫️ Точка росы = температуре! Туман, роса на дороге")
            score += 3
            recommendations.append("🐢 Снизьте скорость, дорога мокрая")
        elif diff <= 2:
            risks.append(f"💧 Высокая влажность (разница {diff}°C) — роса на дороге")
            score += 2
            recommendations.append("🐢 Осторожно на разметке и в поворотах")
        elif diff <= 4:
            risks.append(f"💧 Повышенная влажность (разница {diff}°C)")
            score += 1
    
    feels_like = weather.get("temp_avg", temp) if is_forecast else weather.get("feels_like", temp)
    
    if feels_like < 0:
        risks.append(f"❄️ Мороз (ощущается как {feels_like}°C)")
        score += 4
        recommendations.append("🧊 Риск обледенения! Только с полным подогревом")
    elif feels_like < 5:
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
        recommendations.append("💧 Пейте воду, делайте остановки")
    
    if not is_forecast and weather.get("is_night", False):
        risks.append("🌙 Темно - плохая видимость")
        score += 2
        recommendations.append("💡 Включите свет, снизьте скорость")
    
    if score >= 8:
        verdict, color = "⛔️ ОПАСНОСТЬ! НЕ РЕКОМЕНДУЕТСЯ!", "🔴"
    elif score >= 5:
        verdict, color = "⚠️ РИСКОВАННО - с осторожностью", "🟡"
    elif score >= 2:
        verdict, color = "🟡 УМЕРЕННЫЙ РИСК - будьте внимательны", "🟠"
    else:
        verdict, color = "✅ БЕЗОПАСНО - отличная погода!", "🟢"
    
    return {
        "score": min(score, 10), "verdict": verdict, "color": color,
        "risks": risks, "recommendations": recommendations, "feels_like": feels_like
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
    markup.row(InlineKeyboardButton("ℹ️ О проекте", callback_data="about"))
    return markup
    def get_after_weather_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 Сейчас", callback_data="update"),
        InlineKeyboardButton("📅 Завтра", callback_data="forecast")
    )
    markup.row(
        InlineKeyboardButton("📆 Неделя", callback_data="weekly"),
        InlineKeyboardButton("🏍️ Советы", callback_data="tips")
    )
    markup.row(InlineKeyboardButton("ℹ️ О проекте", callback_data="about"))
    return markup

# ============ КОМАНДЫ ============
@bot.message_handler(commands=['start'])
def start(message):
    save_user(message.chat.id)
    bot_info = bot.get_me()
    
    if bot_info.username != MY_BOT_USERNAME:
        bot.send_message(message.chat.id,
            f"⚠️ <b>Это поддельный бот!</b>\n\nНастоящий: @{MY_BOT_USERNAME}",
            parse_mode="HTML")
        return
    
    bot.send_message(message.chat.id,
        "🏍️ <b>MotoWeather Минск</b>\n\n"
        "✅ <b>Это НАСТОЯЩИЙ бот!</b>\n"
        f"🔑 Username: @{bot_info.username}\n"
        "👨‍💻 Разработчик: Alexander_K8V\n\n"
        "Я анализирую погоду для райдеров!\n"
        "Нажмите кнопку ниже, чтобы узнать прогноз.",
        parse_mode="HTML", reply_markup=get_main_keyboard())

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
        bot.reply_to(message, "❌ У вас нет прав.")
        return
    
    count = get_users_count()
    bot.reply_to(message,
        f"📊 <b>Статистика</b>\n\n👥 Пользователей: <b>{count}</b>\n"
        f"📅 {datetime.now(MINSK_TZ).strftime('%d.%m.%Y %H:%M')}",
        parse_mode="HTML")

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
🏍️ <b>СОВЕТЫ ДЛЯ РАЙДЕРОВ:</b>

🟢 <b>Светло:</b>
• Проверьте шины и свет
• Надевайте защитную экипировку

🟡 <b>Ветер:</b>
• Держите руль крепче
• Снизьте скорость на открытых участках

🔴 <b>Дождь:</b>
• Увеличьте дистанцию
• Избегайте резких манёвров
• Будьте осторожны на разметке

⚡ <b>Гроза:</b>
• НЕМЕДЛЕННО остановитесь
• Найдите укрытие
• Не стойте под деревьями

🌫️ <b>Туман:</b>
• Включите противотуманки
• Снизьте скорость до минимума

🌙 <b>Темно:</b>
• Включите дальний свет
• Снизьте скорость

💬 <b>ЦИТАТЫ:</b>

"Опытный райдер никогда не выезжает без защиты и нормальных перчаток."

"Для настоящего райдера важен не мотоцикл, а ощущение свободы."

"Среди райдеров есть поговорка: 'Четыре колеса возят тело, два — душу'."

🏍️ Берегите себя на дорогах!
"""
            bot.answer_callback_query(call.id, "✅ Советы загружены")
            bot.send_message(call.message.chat.id, tips, parse_mode="HTML",
                reply_markup=get_main_keyboard())
        elif call.data == "about":
            about_text = """
ℹ️ <b>О ПРОЕКТЕ</b>

🏍️ <b>MotoWeather Минск</b>

Бот создан для райдеров, чтобы анализировать погоду и оценивать риски.

📊 <b>ВОЗМОЖНОСТИ:</b>

🌡️ Текущая погода — METAR аэропорта Минск
📅 Прогноз на завтра — OpenWeatherMap
📆 Прогноз на неделю — OpenWeatherMap
💨 Порывы ветра — METAR
☁️ Облачность — METAR
🌫️ Видимость — METAR
🌧️ Осадки — METAR
💧 Точка росы + влажность — METAR
🌅 Рассвет/закат — OpenWeatherMap
📈 Что будет через 3 часа — OpenWeatherMap
🚨 Предупреждение о росе/тумане
🛡️ Детальная экипировка
📊 Анализ рисков (0-10)
🕐 Лучшее время для поездки
🌙 Определение освещённости

📡 <b>ИСТОЧНИКИ:</b>
✈️ METAR (UMMS) — основной
🌐 OpenWeatherMap — дополнительный

👨‍💻 <b>РАЗРАБОТЧИК:</b> Alexander_K8V

🏍️ Берегите себя на дорогах!
"""
            bot.answer_callback_query(call.id, "✅ Информация загружена")
            bot.send_message(call.message.chat.id, about_text, parse_mode="HTML",
                reply_markup=get_main_keyboard())
    except Exception as e:
        print(f"Ошибка: {e}")

# ============ ОТПРАВКА ПОГОДЫ ============
def send_weather(chat_id):
    weather = get_weather()
    if not weather:
        bot.send_message(chat_id, "❌ Не удалось получить данные.")
        return
    
    analysis = analyze_risks(weather)
    now = get_minsk_time()
    feels_like = analysis.get('feels_like', weather.get('feels_like', weather.get('temp', 0)))
    light_level = get_light_level()
    risk_emoji = analysis['color']
    
    temp_value = weather.get('temp', 0)
    temp_desc = get_temp_description(feels_like)
    
    if feels_like != temp_value:
        temp_line = f"🌡️ <b>Температура:</b> {temp_value}°C (ощущается как {feels_like}°C, {temp_desc})"
    else:
        temp_line = f"🌡️ <b>Температура:</b> {temp_value}°C ({temp_desc})"
    
    weather_info = weather.get('weather_text')
    if weather_info:
        weather_info = f"{weather.get('weather_emoji', '')} {weather_info}"
    else:
        weather_info = "✅ Без осадков"
    
    dew_info = ""
    if weather.get('dew_point') is not None:
        dew_info = f"\n💧 <b>Точка росы:</b> {weather.get('dew_point')}°C"
        if weather.get('humidity') is not None:
            dew_info += f" (влажность {weather.get('humidity')}%)"
    
    visibility = weather.get('visibility', 10000)
    vis_info = f"\n🌫️ <b>Видимость:</b> {format_visibility(visibility)} ({get_visibility_rating(visibility)})"
    
    wind_speed = weather.get('wind_speed', 0)
    wind_desc = get_wind_description(wind_speed)
    wind_feeling = get_wind_feeling(wind_speed)
    wind_line = f"💨 <b>Ветер:</b> {wind_speed} м/с ({wind_desc}) — {wind_feeling}."
    
    wind_gust = weather.get('wind_gust')
    if wind_gust and wind_gust > wind_speed:
        if wind_gust > 10:
            wind_line += f"\n⚠️ <b>ОПАСНЫЕ ПОРЫВЫ:</b> до {wind_gust} м/с! Держите руль крепче."
        else:
            wind_line += f"\n✈️ <b>Порывы (METAR):</b> до {wind_gust} м/с."
    
    sun_line = ""
    if weather.get('sunrise') and weather.get('sunset'):
        sun_line = f"\n🌅 Рассвет: {weather['sunrise']} | 🌇 Закат: {weather['sunset']}"
    
    best_time = get_best_time(weather.get('sunrise'), weather.get('sunset'))
    
    trend_line = ""
    trend = get_trend(chat_id)
    if trend:
        trend_line = "\n\n📈 <b>Что будет через 3 часа:</b>\n" + "\n".join(f"• {t}" for t in trend)
    
    gear_list = get_detailed_gear(
        feels_like, wind_speed, weather.get('is_night', False),
        weather.get('is_rain', False), weather.get('dew_point')
    )
    gear_text = "\n".join(f"• {g}" for g in gear_list)
    
    msg = f"""
{risk_emoji} <b>MotoWeather Минск</b> — <b>сейчас {now}</b>

{light_level}
{temp_line}
{wind_line}
{weather.get('cloud_emoji', '')} <b>Облачность:</b> {weather.get('cloud_text', '—')}
🌧️ <b>Осадки:</b> {weather_info}{dew_info}{vis_info}{sun_line}

📡 <b>Источник:</b> {weather.get('source', 'Неизвестно')}
ℹ️ <i>Данные с метеостанции аэропорта Минск-2. В городе условия могут немного отличаться.</i>

<b>ВЕРДИКТ:</b> {analysis['verdict']}
📊 <b>Уровень риска:</b> {analysis['score']}/10
"""
    
    if analysis["risks"]:
        msg += "\n<b>⚠️ Факторы риска:</b>\n"
        for risk in analysis["risks"]:
            msg += f"• {risk}\n"
    else:
        msg += "\n✅ <b>Нет факторов риска</b>\n"
    
    if analysis["recommendations"]:
        msg += "\n<b>💡 Рекомендации:</b>\n"
        for rec in analysis["recommendations"]:
            msg += f"• {rec}\n"
    
    msg += f"\n<b>🛡️ Экипировка:</b>\n{gear_text}"
    msg += f"{trend_line}"
    msg += f"\n\n<b>{best_time}</b>"
    
    bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=get_after_weather_keyboard())

def send_forecast(chat_id):
    forecast = get_forecast_tomorrow()
    if not forecast:
        bot.send_message(chat_id, "❌ Не удалось получить прогноз.")
        return
    
    analysis = analyze_risks(forecast, is_forecast=True)
    risk_emoji = analysis['color']
    
    rain_info = f" 🌧️{forecast.get('rain_total', 0):.1f} мм (за день)" if forecast.get('rain_total', 0) > 0 else ""
    
    wind_speed = forecast.get('wind_speed', 0)
    wind_desc = get_wind_description(wind_speed)
    wind_feeling = get_wind_feeling(wind_speed)
    avg_temp = forecast.get('temp_avg', 0)
    
    if forecast.get('wind_gust', 0) > wind_speed:
        wind_line = f"💨 <b>Ветер:</b> {wind_speed} м/с (порывы до {forecast.get('wind_gust', 0)} м/с, {wind_desc}) — {wind_feeling}"
    else:
        wind_line = f"💨 <b>Ветер:</b> {wind_speed} м/с ({wind_desc}) — {wind_feeling}"
    
    msg = f"""
{risk_emoji} <b>MotoWeather Минск</b> — <b>завтра {forecast.get('date', 'завтра')}</b>

🌡️ <b>Средняя температура:</b> {avg_temp}°C (мин {forecast.get('temp_min', 0)}°C / макс {forecast.get('temp_max', 0)}°C)
{wind_line}
{forecast.get('condition', '')}{rain_info}

<b>ВЕРДИКТ:</b> {analysis['verdict']}
📊 <b>Уровень риска:</b> {analysis['score']}/10
"""
    
    if analysis["risks"]:
        msg += "\n<b>⚠️ Факторы риска:</b>\n"
        for risk in analysis["risks"]:
            msg += f"• {risk}\n"
    else:
        msg += "\n✅ <b>Нет факторов риска</b>\n"
    
    if analysis["recommendations"]:
        msg += "\n<b>💡 Рекомендации:</b>\n"
        for rec in analysis["recommendations"]:
            msg += f"• {rec}\n"
    
    gear_list = get_detailed_gear(avg_temp, wind_speed, False, forecast.get('is_rain', False), None)
    gear_text = "\n".join(f"• {g}" for g in gear_list)
    msg += f"\n<b>🛡️ Экипировка:</b>\n{gear_text}"
    
    msg += f"\n\n📡 <b>Источник:</b> OpenWeatherMap (прогноз)"
    
    bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=get_after_weather_keyboard())

def send_weekly(chat_id):
    weekly = get_weekly_forecast()
    if not weekly:
        bot.send_message(chat_id, "❌ Не удалось получить прогноз.")
        return
    
    msg = "📆 <b>ПРОГНОЗ НА НЕДЕЛЮ (Минск)</b>\n\n"
    
    for day in weekly:
        temp_str = f"{day['temp_min']}°...{day['temp_max']}°"
        wind_str = f"{day['wind_speed']} м/с"
        rain_str = f" 🌧️{day['rain_total']:.1f}мм" if day['rain_total'] > 0 else ""
        
        if day['wind_speed'] > 14 or day['is_thunder']:
            emoji = "🔴"
        elif day['wind_speed'] > 10 or day['rain_total'] > 5:
            emoji = "🟡"
        else:
            emoji = "🟢"
        
        msg += f"{emoji} <b>{day['weekday']}</b> {day['date']}: {day['condition']} {temp_str} | 💨 {wind_str}{rain_str}\n"
    
    msg += "\n<b>📊 АНАЛИЗ НЕДЕЛИ:</b>\n\n"
    
    rainy_days_list = []
    windy_days_list = []
    best_day, worst_day = None, None
    best_day_score, worst_day_score = float('inf'), -float('inf')
    
    for day in weekly:
        day_name = day['weekday']
        wind, rain = day['wind_speed'], day['rain_total']
        temp_max, temp_min = day['temp_max'], day['temp_min']
        
        issues = []
        if rain > 0:
            issues.append(f"дождь {rain:.1f}мм")
            rainy_days_list.append(day_name)
        if wind > 10:
            issues.append(f"ветер {wind} м/с")
            windy_days_list.append(day_name)
        if temp_max > 30:
            issues.append("жарко")
        if temp_min < 0:
            issues.append("мороз")
        
        score = wind + rain * 3
        if score < best_day_score:
            best_day_score, best_day = score, day
        if score > worst_day_score:
            worst_day_score, worst_day = score, day
        
        if not issues:
            msg += f"☀️ <b>{day_name}</b>: отличный день для поездки\n"
        elif len(issues) == 1:
            msg += f"☀️ <b>{day_name}</b>: {issues[0]} — будьте внимательны\n"
        else:
            msg += f"⚠️ <b>{day_name}</b>: {', '.join(issues)} — осторожно!\n"
    
    if best_day and worst_day:
        best_reason = []
        if best_day['rain_total'] == 0:
            best_reason.append("без дождя")
        elif best_day['rain_total'] < 1:
            best_reason.append(f"небольшой дождь ({best_day['rain_total']:.1f}мм)")
        if best_day['wind_speed'] <= 5:
            best_reason.append("слабый ветер")
        if best_day['temp_max'] >= 18:
            best_reason.append("тепло")
        
        worst_reason = []
        if worst_day['rain_total'] > 0:
            worst_reason.append(f"дождь ({worst_day['rain_total']:.1f}мм)")
        if worst_day['wind_speed'] > 10:
            worst_reason.append(f"сильный ветер ({worst_day['wind_speed']} м/с)")
        if worst_day['temp_max'] < 15:
            worst_reason.append("прохладно")
        if worst_day['temp_max'] > 30:
            worst_reason.append("жарко")
        
        msg += "\n<b>🏍️ РЕКОМЕНДАЦИИ НА НЕДЕЛЮ:</b>\n\n"
        msg += f"✅ <b>Лучший день:</b> {best_day['weekday']} ({best_day['temp_min']}°...{best_day['temp_max']}°)\n"
        if best_reason:
            msg += f"   → {', '.join(best_reason)}\n"
        
        msg += f"\n⚠️ <b>Худший день:</b> {worst_day['weekday']}\n"
        if worst_reason:
            msg += f"   → {', '.join(worst_reason)}\n"
        
        msg += "\n💡 <b>Общие советы:</b>\n"
        if rainy_days_list:
            msg += f"• ☔ Возьмите дождевик: {', '.join(rainy_days_list)}\n"
        if windy_days_list:
            msg += f"• 💨 Держите руль крепче: {', '.join(windy_days_list)}\n"
        if best_day:
            msg += f"• ⭐ Планируйте поездки: {best_day['weekday']}\n"
        if any(day['temp_min'] < 0 for day in weekly):
            msg += f"• 🧥 Тёплая экипировка обязательна\n"
        if any(day['temp_max'] > 30 for day in weekly):
            msg += f"• 💧 Пейте больше воды в жаркие дни\n"
    
    msg += "\n📡 <b>Источник:</b> OpenWeatherMap (прогноз)"
    msg += "\n🏍️ <b>Берегите себя на дорогах!</b>"
    
    bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=get_after_weather_keyboard())

# ============ ВЕБ-СЕРВЕР ДЛЯ ПИНГА ============
@app.route('/')
def home():
    return "🏍️ MotoWeather Bot is running!", 200

@app.route('/health')
def health():
    return jsonify({
        "status": "ok", "bot": "MotoWeather Minsk",
        "users": get_users_count(),
        "time": datetime.now(MINSK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    }), 200

def run_flask():
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ============ ЗАПУСК ============
if __name__ == "__main__":
    print("🏍️ MotoWeather Бот запущен!")
    print("✅ Источник (Сейчас): METAR аэропорта Минск")
    print("✅ Источник (Завтра/Неделя): OpenWeatherMap")
    print("✅ Кнопка 'Сегодня' переименована в 'Сейчас'")
    print("📡 Бот готов к работе")
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    bot.infinity_polling()