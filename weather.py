import re
import math
import requests
from datetime import datetime, timedelta

from config import (
    MINSK_TZ,
    METAR_URL, METAR_FALLBACK_URL, OPEN_METEO_URL,
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


# ============ OPEN-METEO: ОБЩИЙ ЗАПРОС ============
def _fetch_open_meteo():
    """Запрашивает у Open-Meteo текущую погоду + прогноз на 24 часа."""
    try:
        url = (
            f"{OPEN_METEO_URL}"
            f"?latitude={MINSK_LAT}&longitude={MINSK_LON}"
            f"&current=temperature_2m,wind_speed_10m,wind_gusts_10m,"
            f"relative_humidity_2m,weather_code,visibility"
            f"&hourly=temperature_2m,wind_speed_10m,weather_code,precipitation_probability"
            f"&daily=temperature_2m_max,temperature_2m_min,weather_code,"
            f"wind_speed_10m_max,precipitation_sum"
            f"&timezone=Europe/Minsk"
            f"&forecast_days=3"
        )
        print("Open-Meteo: запрашиваю данные...", flush=True)
        r = requests.get(url, timeout=10)
        data = r.json()
        if "error" in data:
            print(f"Open-Meteo: ошибка {data.get('reason')}", flush=True)
            return None
        print("Open-Meteo: получено", flush=True)
        return data
    except Exception as e:
        print(f"Open-Meteo: ошибка запроса: {e}", flush=True)
        return None


def _wmo_emoji(code):
    """WMO weather code → (emoji, description)."""
    if code == 0:
        return "☀️", "Ясно"
    if code in (1, 2):
        return "🌤️", "Переменная облачность"
    if code == 3:
        return "☁️", "Пасмурно"
    if code in (45, 48):
        return "🌫️", "Туман"
    if code in (51, 53, 55, 56, 57):
        return "🌦️", "Морось"
    if code in (61, 63):
        return "🌧️", "Дождь"
    if code == 65:
        return "🌧️", "Сильный дождь"
    if code in (66, 67):
        return "🌧️", "Ледяной дождь"
    if code in (71, 73, 75, 77):
        return "🌨️", "Снег"
    if code in (80, 81, 82):
        return "🌧️", "Ливень"
    if code in (85, 86):
        return "🌨️", "Снегопад"
    if code in (95, 96, 99):
        return "⛈️", "Гроза"
    return "🌤️", "Переменно"


# ============ ТЕКУЩАЯ ПОГОДА (METAR + Open-Meteo fallback) ============
def get_weather():
    try:
        metar = get_metar_data()
        om = _fetch_open_meteo()

        if not metar and not om:
            print("Нет данных ни из METAR, ни из Open-Meteo", flush=True)
            return None

        # Если METAR нет — используем Open-Meteo как основной
        if not metar and om:
            cur = om.get("current", {})
            temp = round(cur.get("temperature_2m", 0))
            wind_speed = round(cur.get("wind_speed_10m", 0))
            wind_gust_val = cur.get("wind_gusts_10m")
            wind_gust = round(wind_gust_val) if wind_gust_val else None
            humidity = round(cur.get("relative_humidity_2m", 0))
            visibility = int(cur.get("visibility") or 10000)
            weather_code = cur.get("weather_code", 0)
            emoji, text = _wmo_emoji(weather_code)

            # sunrise/sunset из daily
            daily = om.get("daily", {})
            sunrise_iso = daily.get("sunrise", [None])[0] if daily.get("sunrise") else None
            sunset_iso = daily.get("sunset", [None])[0] if daily.get("sunset") else None
            sunrise = sunrise_iso.split("T")[1][:5] if sunrise_iso else None
            sunset = sunset_iso.split("T")[1][:5] if sunset_iso else None

            feels_like = calculate_feels_like(temp, wind_speed)

            return {
                "temp": temp,
                "feels_like": feels_like,
                "cloud_emoji": emoji,
                "cloud_text": text,
                "weather_text": text,
                "weather_emoji": emoji,
                "dew_point": None,
                "humidity": humidity,
                "wind_speed": wind_speed,
                "wind_gust": wind_gust,
                "visibility": visibility,
                "is_rain": weather_code in (51, 53, 55, 61, 63, 65, 80, 81, 82),
                "is_thunder": weather_code in (95, 96, 99),
                "is_night": is_night_time(),
                "sunrise": sunrise,
                "sunset": sunset,
                "source": "Open-Meteo"
            }

        # Основной путь — METAR
        om_cur = (om or {}).get("current", {})
        # Sunrise/sunset из Open-Meteo daily
        daily = (om or {}).get("daily", {})
        sunrise_iso = daily.get("sunrise", [None])[0] if daily.get("sunrise") else None
        sunset_iso = daily.get("sunset", [None])[0] if daily.get("sunset") else None
        sunrise = sunrise_iso.split("T")[1][:5] if sunrise_iso else None
        sunset = sunset_iso.split("T")[1][:5] if sunset_iso else None

        temp = metar.get("temp", round(om_cur.get("temperature_2m", 0)))
        wind_speed = metar.get("wind_speed", round(om_cur.get("wind_speed_10m", 0)))
        cloud_emoji = metar.get("cloud_emoji", "⛅")
        cloud_text = metar.get("cloud_text", "Облачно")
        visibility = metar.get("visibility", 10000)
        weather_text = metar.get("weather_text") or ""
        weather_emoji = metar.get("weather_emoji") or ""
        dew_point = metar.get("dew_point")
        is_rain = metar.get("is_rain", False)
        is_thunder = metar.get("is_thunder", False)

        # Густоты: METAR → Open-Meteo → None
        wind_gust = metar.get("wind_gust")
        if wind_gust is None:
            gust_om = om_cur.get("wind_gusts_10m")
            wind_gust = round(gust_om) if gust_om else None
        if wind_speed == 0:
            wind_gust = None

        feels_like = calculate_feels_like(temp, wind_speed)
        humidity = calculate_humidity(temp, dew_point) if dew_point is not None else None
        if humidity is None:
            humidity = round(om_cur.get("relative_humidity_2m", 0)) or None

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
            "source": "METAR (аэропорт Минск)"
        }
    except Exception as e:
        print(f"❌ Ошибка погоды: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None


# ============ ПРОГНОЗ НА ЗАВТРА (Open-Meteo) ============
def get_forecast_tomorrow():
    try:
        om = _fetch_open_meteo()
        if not om or "daily" not in om:
            return None

        daily = om["daily"]
        # Индекс 1 = завтра (0 = сегодня)
        if len(daily.get("time", [])) < 2:
            return None

        date_iso = daily["time"][1]
        temp_max = round(daily["temperature_2m_max"][1])
        temp_min = round(daily["temperature_2m_min"][1])
        temp_avg = round((temp_max + temp_min) / 2)
        weather_code = daily["weather_code"][1]
        wind_speed_max = round(daily["wind_speed_10m_max"][1])
        precip_sum = daily.get("precipitation_sum", [0, 0])[1]

        emoji, text = _wmo_emoji(weather_code)
        is_rain = weather_code in (51, 53, 55, 61, 63, 65, 80, 81, 82)
        is_thunder = weather_code in (95, 96, 99)

        date_obj = datetime.strptime(date_iso, "%Y-%m-%d")

        return {
            "date": date_obj.strftime("%d.%m.%Y"),
            "temp_avg": temp_avg,
            "temp_max": temp_max,
            "temp_min": temp_min,
            "wind_speed": wind_speed_max,
            "wind_gust": round(wind_speed_max * 1.3),
            "rain_total": round(precip_sum, 1) if precip_sum else 0,
            "condition": f"{emoji} {text}",
            "is_rain": is_rain,
            "is_thunder": is_thunder
        }
    except Exception as e:
        print(f"Ошибка прогноза на завтра: {e}", flush=True)
        return None


# ============ КОРОТКИЙ ПРОГНОЗ: БЛИЖАЙШИЙ ЧАС + УТРО (Open-Meteo) ============
def get_short_forecast():
    """Возвращает {next_hour, morning} из Open-Meteo hourly."""
    try:
        om = _fetch_open_meteo()
        if not om or "hourly" not in om:
            return {"next_hour": "нет данных", "morning": "нет данных"}

        hourly = om["hourly"]
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        winds = hourly.get("wind_speed_10m", [])
        codes = hourly.get("weather_code", [])

        now = datetime.now(MINSK_TZ).replace(tzinfo=None)

        # Индекс ближайшего часа к "сейчас + 3 часа"
        target = now + timedelta(hours=3)
        next_idx = 0
        min_diff = float("inf")
        for i, t_str in enumerate(times):
            try:
                t_dt = datetime.fromisoformat(t_str)
                diff = abs((t_dt - target).total_seconds())
                if diff < min_diff:
                    min_diff = diff
                    next_idx = i
            except Exception:
                continue

        if next_idx < len(temps):
            t = round(temps[next_idx])
            w = round(winds[next_idx])
            code = codes[next_idx]
            _, cond = _wmo_emoji(code)
            next_hour = f"{t}°C, {cond}, {w} м/с"
        else:
            next_hour = "нет данных"

        # Утро завтра (6:00–9:00)
        tomorrow_date = (now + timedelta(days=1)).date()
        morning_temps = []
        morning_winds = []
        morning_codes = []
        for i, t_str in enumerate(times):
            try:
                t_dt = datetime.fromisoformat(t_str)
                if t_dt.date() == tomorrow_date and 6 <= t_dt.hour <= 9:
                    morning_temps.append(temps[i])
                    morning_winds.append(winds[i])
                    morning_codes.append(codes[i])
            except Exception:
                continue

        if morning_temps:
            avg_t = round(sum(morning_temps) / len(morning_temps))
            avg_w = round(sum(morning_winds) / len(morning_winds))
            _, cond = _wmo_emoji(morning_codes[0])
            morning = f"{avg_t}°C, {cond}, {avg_w} м/с"
        else:
            morning = "нет данных"

        return {"next_hour": next_hour, "morning": morning}
    except Exception as e:
        print(f"Ошибка короткого прогноза: {e}", flush=True)
        return {"next_hour": "нет данных", "morning": "нет данных"}