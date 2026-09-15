import re
import math
import time
import requests
from datetime import datetime, timedelta

from config import (
    OPENWEATHER_API_KEY, MINSK_TZ,
    METAR_URL, METAR_FALLBACK_URL, OWM_WEATHER_URL, OWM_FORECAST_URL,
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


def get_daylight_info(sunrise, sunset):
    """Возвращает с эмодзи по времени суток."""
    if not sunrise or not sunset:
        return "—"
    try:
        now = datetime.now(MINSK_TZ)
        h_s, m_s = map(int, sunrise.split(":"))
        h_e, m_e = map(int, sunset.split(":"))

        sunrise_dt = now.replace(hour=h_s, minute=m_s, second=0, microsecond=0)
        sunset_dt = now.replace(hour=h_e, minute=m_e, second=0, microsecond=0)

        if now < sunrise_dt:
            delta = sunrise_dt - now
            h = int(delta.total_seconds() // 3600)
            m = int((delta.total_seconds() % 3600) // 60)
            return f"🌅 Рассвет через {h} ч {m} мин"
        elif now < sunset_dt:
            delta = sunset_dt - now
            h = int(delta.total_seconds() // 3600)
            m = int((delta.total_seconds() % 3600) // 60)
            return f"☀️ Светло, осталось {h} ч {m} мин (закат {sunset})"
        else:
            return f"🌇 Темно (закат {sunset})"
    except Exception:
        return "—"


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


def _fetch_metar_text():
    """Пробует основной источник METAR, при неудаче — резервный."""
    for url in (METAR_URL, METAR_FALLBACK_URL):
        try:
            print(f"METAR: пробую {url}", flush=True)
            response = requests.get(url, timeout=10)
            if response.status_code == 200 and "UMMS" in response.text:
                return response.text.strip()
            print(f"METAR: {url} вернул status={response.status_code}", flush=True)
        except Exception as e:
            print(f"METAR: ошибка {url}: {e}", flush=True)
    return None


def get_metar_data():
    try:
        metar_text = _fetch_metar_text()
        if not metar_text:
            print("METAR: пусто, возвращаю None", flush=True)
            return None

        print(f"METAR OK: {metar_text}", flush=True)
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
        print(f"Ошибка METAR: {e}", flush=True)
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
        print(f"OWM: запрашиваю погоду...", flush=True)
        data = requests.get(url, timeout=10).json()
        print(f"OWM: получено, cod={data.get('cod')}", flush=True)

        if data.get("cod") != 200:
            print(f"OWM: ошибка {data.get('message', 'unknown')}", flush=True)
            return None

        owm_temp = int(data["main"]["temp"])
        owm_wind = int(data["wind"]["speed"])
        owm_gust = data.get("wind", {}).get("gust")
        if owm_gust is not None:
            owm_gust = round(owm_gust)
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

            if wind_speed == 0:
                wind_gust = None
            else:
                wind_gust = metar.get("wind_gust") or owm_gust

            source = "METAR (аэропорт Минск)"
        else:
            print("METAR: не получил, использую OWM", flush=True)
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
            wind_gust = owm_gust
            source = "OpenWeatherMap"

        feels_like = calculate_feels_like(temp, wind_speed)
        humidity = calculate_humidity(temp, dew_point) if dew_point is not None else None

        print(f"✅ Weather собрана: temp={temp}, humidity={humidity}", flush=True)

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
        print(f"❌ Ошибка погоды: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None


# ============ ПРОГНОЗ НА ЗАВТРА ============
def get_forecast_tomorrow():
    try:
        url = (
            f"{OWM_FORECAST_URL}?lat={MINSK_LAT}&lon={MINSK_LON}"
            f"&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru&cnt=8"
        )
        print("OWM: запрашиваю прогноз на завтра...", flush=True)
        data = requests.get(url, timeout=10).json()
        print(f"OWM forecast: cod={data.get('cod')}", flush=True