import re
import math
import time
import requests
from datetime import datetime, timedelta

from config import (
    OPENWEATHER_API_KEY, MINSK_TZ,
    METAR_URL, OWM_WEATHER_URL, OWM_FORECAST_URL,
    MINSK_LAT, MINSK_LON
)


# ============ ВСПОМОГАТЕЛЬНЫЕ ============
def get_minsk_time():
    return datetime.now(MINSK_TZ).strftime("%H:%M")


def get_minsk_hour():
    return datetime.now(MINSK_TZ).hour


def get_minsk_month():
    return datetime.now(MINSK_TZ).month


# ============ ОСВЕЩЁННОСТЬ ============
def get_light_level():
    h = get_minsk_hour()
    m = get_minsk_month()

    if 5 <= m <= 8:
        return "☀️ Светло" if 5 <= h < 22 else "🌙 Темно"
    elif 11 <= m <= 2:
        return "☀️ Светло" if 8 <= h < 17 else "🌙 Темно"
    else:
        return "☀️ Светло" if 6 <= h < 20 else "🌙 Темно"


def is_night_time():
    return get_light_level() == "🌙 Темно"


# ============ РАСЧЁТ ВЛАЖНОСТИ ============
def calculate_humidity(temp, dew_point):
    try:
        a, b = 17.27, 237.7
        alpha = ((a * dew_point) / (b + dew_point)) - ((a * temp) / (b + temp))
        return round(100 * math.exp(alpha))
    except Exception:
        return None


def calculate_feels_like(temp, wind_speed):
    if temp <= 10 and wind_speed > 1.3:
        w = wind_speed * 3.6
        feels = 13.12 + 0.6215 * temp - 11.37 * (w ** 0.16) + 0.3965 * temp * (w ** 0.16)
        return round(feels)
    elif temp >= 27:
        return round(temp + 1)
    return round(temp)


# ============ ПАРСЕР METAR ============
def parse_clouds(metar_text):
    if "OVC" in metar_text:
        return "☁️", "Пасмурно"
    if "BKN" in metar_text:
        return "☁️", "Значительная облачность"
    if "SCT" in metar_text:
        return "⛅", "Облачно с прояснениями"
    if "FEW" in metar_text:
        return "🌤️", "Малооблачно"
    if any(x in metar_text for x in ["CAVOK", "NSC", "SKC", "CLR"]):
        return "🌤️", "Преимущественно ясно"
    return "⛅", "Облачно"


def parse_visibility(metar_text):
    if "CAVOK" in metar_text or "9999" in metar_text:
        return 10000
    match = re.search(r"\s(\d{4})\s", metar_text)
    return int(match.group(1)) if match else 10000


def parse_weather_phenomena(metar_text):
    if "TS" in metar_text:
        if "TSRA" in metar_text:
            return "⛈️", "Гроза с дождём", True, True
        if "TSSN" in metar_text:
            return "⛈️", "Гроза со снегом", False, True
        return "⛈️", "Гроза", False, True

    if "SHRA" in metar_text:
        return "🌧️", "Ливневый дождь", True, False
    if "SHSN" in metar_text:
        return "🌨️", "Ливневый снег", False, False

    if "+RA" in metar_text:
        return "🌧️", "Сильный дождь", True, False
    if "-RA" in metar_text:
        return "🌦️", "Слабый дождь", True, False
    if "RA" in metar_text:
        return "🌧️", "Дождь", True, False

    if "DZ" in metar_text:
        return "🌦️", "Морось", True, False

    if "+SN" in metar_text:
        return "❄️", "Сильный снег", False, False
    if "-SN" in metar_text:
        return "🌨️", "Слабый снег", False, False
    if "SN" in metar_text:
        return "❄️", "Снег", False, False

    if "FG" in metar_text:
        return "🌫️", "Туман", False, False
    if "BR" in metar_text:
        return "🌫️", "Дымка", False, False
    if "HZ" in metar_text:
        return "🌫️", "Мгла", False, False

    if "GR" in metar_text:
        return "🧊", "Град", False, False

    return "", "", False, False


def get_metar_data():
    try:
        response = requests.get(METAR_URL, timeout=10)
        if response.status_code != 200:
            return None

        metar_text = response.text.strip()
        print(f"METAR: {metar_text}")

        result = {}

        # Ветер
        wind_match = re.search(r"\b(\d{3})(\d{2,3})(G(\d{2,3}))?(KT|MPS)\b", metar_text)
        if wind_match:
            unit = wind_match.group(5)
            value = int(wind_match.group(2))
            result["wind_speed"] = round(value * 0.514444) if unit == "KT" else value

            if wind_match.group(4):
                gust = int(wind_match.group(4))
                result["wind_gust"] = round(gust * 0.514444) if unit == "KT" else gust
            else:
                result["wind_gust"] = None

        # Облачность
        emoji, text = parse_clouds(metar_text)
        result["cloud_emoji"] = emoji
        result["cloud_text"] = text

        # Видимость
        result["visibility"] = parse_visibility(metar_text)

        # Осадки
        w_emoji, w_text, is_rain, is_thunder = parse_weather_phenomena(metar_text)
        result["weather_emoji"] = w_emoji
        result["weather_text"] = w_text
        result["is_rain"] = is_rain
        result["is_thunder"] = is_thunder

        # Температура и точка росы
        temp_match = re.search(r"\s(M?\d{2})/(M?\d{2})\s", metar_text)
        if temp_match:
            result["temp"] = int(temp_match.group(1).replace("M", "-"))
            result["dew_point"] = int(temp_match.group(2).replace("M", "-"))

        return result
    except Exception as e:
        print(f"Ошибка METAR: {e}")
        return None


# ============ РАССВЕТ/ЗАКАТ ============
def get_sun_times(data):
    try:
        sunrise_ts = data.get("sys", {}).get("sunrise")
        sunset_ts = data.get("sys", {}).get("sunset")
        if sunrise_ts and sunset_ts:
            sunrise = datetime.fromtimestamp(sunrise_ts, tz=MINSK_TZ).strftime("%H:%M")
            sunset = datetime.fromtimestamp(sunset_ts, tz=MINSK_TZ).strftime("%H:%M")
            return sunrise, sunset
    except Exception:
        pass
    return None, None


# ============ ТЕКУЩАЯ ПОГОДА ============
def get_weather():
    try:
        cache = int(time.time())
        url = (
            f"{OWM_WEATHER_URL}?lat={MINSK_LAT}&lon={MINSK_LON}"
            f"&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&_={cache}"
        )
        data = requests.get(url, timeout=10).json()

        if data.get("cod") != 200:
            return None

        owm_temp = int(data["main"]["temp"])
        owm_wind = int(data["wind"]["speed"])
        sunrise, sunset = get_sun_times(data)

        metar = get_metar_data()

        if metar:
            temp = metar.get("temp", owm_temp)
            wind_speed = metar.get("wind_speed", owm_wind)
            cloud_emoji = metar.get("cloud_emoji", "⛅")
            cloud_text = metar.get("cloud_text", "Облачно")
            visibility = metar.get("visibility", 10000)
            weather_text = metar.get("weather_text") or ""
            weather_emoji = metar.get("weather_emoji") or ""
            dew_point = metar.get("dew_point")
            is_rain = metar.get("is_rain", False)
            is_thunder = metar.get("is_thunder", False)
            wind_gust = metar.get("wind_gust")
            source = "METAR (аэропорт Минск)"
        else:
            temp = owm_temp
            wind_speed = owm_wind
            cloud_emoji = "⛅"
            cloud_text = "—"
            visibility = 10000
            weather_text = ""
            weather_emoji = ""
            dew_point = None
            is_rain = False
            is_thunder = False
            wind_gust = None
            source = "OpenWeatherMap"

        feels_like = calculate_feels_like(temp, wind_speed)
        humidity = calculate_humidity(temp, dew_point) if dew_point is not None else None

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
            "visibility": visibility,
            "is_rain": is_rain,
            "is_thunder": is_thunder,
            "is_night": is_night_time(),
            "sunrise": sunrise,
            "sunset": sunset,
            "source": source
        }
    except Exception as e:
        print(f"Ошибка погоды: {e}")
        return None


# ============ ПРОГНОЗ НА ЗАВТРА ============
def get_forecast_tomorrow():
    try:
        url = (
            f"{OWM_FORECAST_URL}?lat={MINSK_LAT}&lon={MINSK_LON}"
            f"&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&cnt=8"
        )
        data = requests.get(url, timeout=10).json()

        if data.get("cod") != "200":
            return None

        tomorrow = datetime.now(MINSK_TZ) + timedelta(days=1)
        key = tomorrow.strftime("%Y-%m-%d")

        temps, winds, conditions = [], [], []
        rain = 0

        for item in data["list"]:
            dt = datetime.fromtimestamp(item["dt"], tz=MINSK_TZ)
            if dt.strftime("%Y-%m-%d") == key:
                temps.append(item["main"]["temp"])
                winds.append(item["wind"]["speed"])
                if "rain" in item:
                    rain += item["rain"].get("3h", 0)
                conditions.append(item["weather"][0]["id"])

        if not temps:
            return None

        return _build_forecast_result(temps, winds, rain, conditions, tomorrow)
    except Exception as e:
        print(f"Ошибка прогноза: {e}")
        return None


def _build_forecast_result(temps, winds, rain, conditions, date_obj):
    avg_temp = int(sum(temps) / len(temps))
    max_temp, min_temp = int(max(temps)), int(min(temps))
    avg_wind = int(sum(winds) / len(winds))
    wind_gust = int(max(winds) * 1.3)
    most_common = max(set(conditions), key=conditions.count) if conditions else 800

    condition, is_rain, is_thunder = _classify_condition(most_common)

    return {
        "date": date_obj.strftime("%d.%m.%Y"),
        "temp_avg": avg_temp,
        "temp_max": max_temp,
        "temp_min": min_temp,
        "wind_speed": avg_wind,
        "wind_gust": wind_gust,
        "rain_total": round(rain, 1),
        "condition": condition,
        "is_rain": is_rain,
        "is_thunder": is_thunder
    }


def _classify_condition(weather_id):
    if 200 <= weather_id < 300:
        return "⛈️ Гроза", True, True
    if 500 <= weather_id < 600:
        return ("🌧️ Сильный дождь" if weather_id >= 502 else "🌧️ Дождь"), True, False
    if 600 <= weather_id < 700:
        return "❄️ Снег", False, False
    if weather_id == 800:
        return "☀️ Ясно", False, False
    if weather_id > 800:
        return "☁️ Облачно", False, False
    return "🌤️ Переменная облачность", False, False


# ============ ПРОГНОЗ НА НЕДЕЛЮ ============
def get_weekly_forecast():
    try:
        url = (
            f"{OWM_FORECAST_URL}?lat={MINSK_LAT}&lon={MINSK_LON}"
            f"&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&cnt=40"
        )
        data = requests.get(url, timeout=10).json()

        if data.get("cod") != "200":
            return None

        days = {}
        today = datetime.now(MINSK_TZ).date()

        for item in data["list"]:
            dt = datetime.fromtimestamp(item["dt"], tz=MINSK_TZ)
            key = dt.strftime("%Y-%m-%d")

            if dt.date() == today:
                continue

            if key not in days:
                days[key] = {"temps": [], "winds": [], "rain": 0, "conditions": [], "date": dt}

            days[key]["temps"].append(item["main"]["temp"])
            days[key]["winds"].append(item["wind"]["speed"])
            if "rain" in item:
                days[key]["rain"] += item["rain"].get("3h", 0)
            days[key]["conditions"].append(item["weather"][0]["id"])

        result = []
        weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

        for key, day in sorted(days.items())[:7]:
            if not day["temps"]:
                continue

            fc = _build_forecast_result(
                day["temps"], day["winds"], day["rain"],
                day["conditions"], day["date"]
            )
            fc["weekday"] = weekdays[day["date"].weekday()]
            fc["date"] = day["date"].strftime("%d.%m")
            result.append(fc)

        return result
    except Exception as e:
        print(f"Ошибка недельного прогноза: {e}")
        return None


# ============ ТРЕНД ЗА 3 ЧАСА ============
def get_trend():
    try:
        cache = int(time.time())
        url = (
            f"{OWM_FORECAST_URL}?lat={MINSK_LAT}&lon={MINSK_LON}"
            f"&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&cnt=2&_={cache}"
        )
        data = requests.get(url, timeout=10).json()

        if data.get("cod") != "200" or not data.get("list"):
            return None

        owm = requests.get(
            f"{OWM_WEATHER_URL}?lat={MINSK_LAT}&lon={MINSK_LON}"
            f"&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru",
            timeout=10
        ).json()

        if owm.get("cod") != 200:
            return None

        cur_temp = int(owm["main"]["temp"])
        cur_wind = int(owm["wind"]["speed"])
        fc_temp = int(data["list"][0]["main"]["temp"])
        fc_wind = int(data["list"][0]["wind"]["speed"])

        temp_diff = fc_temp - cur_temp
        wind_diff = fc_wind - cur_wind

        trend = []

        if abs(temp_diff) >= 2:
            trend.append(f"🌡️ Потеплеет на +{temp_diff}°C" if temp_diff > 0
                         else f"🌡️ Похолодает на {temp_diff}°C")
        else:
            trend.append("🌡️ Температура стабильна")

        if abs(wind_diff) >= 3:
            trend.append(f"💨 Ветер усилится на +{wind_diff} м/с" if wind_diff > 0
                         else f"💨 Ветер ослабнет на {wind_diff} м/с")
        else:
            trend.append("💨 Ветер без изменений")

        if "rain" in data["list"][0]:
            trend.append("🌧️ Ожидается дождь")
        elif any("rain" in item for item in data["list"][:2]):
            trend.append("🌧️ Возможен дождь")
        else:
            trend.append("☀️ Осадков не ожидается")

        return trend
    except Exception as e:
        print(f"Ошибка тренда: {e}")
        return None