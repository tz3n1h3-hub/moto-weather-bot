import re
import math
import time
import requests
import urllib3
from datetime import datetime, timedelta

from config import (
    MINSK_TZ,
    METAR_URL, METAR_FALLBACK_URL, OPEN_METEO_URL,
    MINSK_LAT, MINSK_LON
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============ ГЛОБАЛЬНЫЙ КЭШ ============
_open_meteo_cache = {"data": None, "ts": 0}
_wttr_cache = {"data": None, "ts": 0}


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

        emoji, text = parse_clouds(metar_text)
        result["cloud_emoji"] = emoji
        result["cloud_text"] = text

        result["visibility"] = parse_visibility(metar_text)

        w_emoji, w_text, is_rain, is_thunder = parse_weather_phenomena(metar_text)
        result["weather_emoji"] = w_emoji
        result["weather_text"] = w_text
        result["is_rain"] = is_rain
        result["is_thunder"] = is_thunder

        temp_match = re.search(r"\s(M?\d{2})/(M?\d{2})\s", metar_text)
        if temp_match:
            result["temp"] = int(temp_match.group(1).replace("M", "-"))
            result["dew_point"] = int(temp_match.group(2).replace("M", "-"))

        return result
    except Exception as e:
        print(f"Ошибка METAR: {e}", flush=True)
        return None


# ============ OPEN-METEO ============
def _fetch_open_meteo():
    global _open_meteo_cache

    if _open_meteo_cache["data"] and (time.time() - _open_meteo_cache["ts"]) < 300:
        print("Open-Meteo: из кэша", flush=True)
        return _open_meteo_cache["data"]

    try:
        url = (
            f"{OPEN_METEO_URL}"
            f"?latitude={MINSK_LAT}&longitude={MINSK_LON}"
            f"&current=temperature_2m,wind_speed_10m,wind_gusts_10m,"
            f"relative_humidity_2m,weather_code,visibility"
            f"&hourly=temperature_2m,wind_speed_10m,weather_code,precipitation_probability"
            f"&daily=temperature_2m_max,temperature_2m_min,weather_code,"
            f"wind_speed_10m_max,precipitation_sum,sunrise,sunset"
            f"&timezone=Europe/Minsk"
            f"&forecast_days=3"
            f"&wind_speed_unit=ms"
        )
        print("Open-Meteo: запрашиваю данные...", flush=True)
        r = requests.get(url, timeout=10)
        data = r.json()
        if "error" in data:
            print(f"Open-Meteo: ошибка {data.get('reason')}", flush=True)
            return None

        _open_meteo_cache["data"] = data
        _open_meteo_cache["ts"] = time.time()
        print("Open-Meteo: получено и закэшировано", flush=True)
        return data
    except Exception as e:
        print(f"Open-Meteo: ошибка запроса: {e}", flush=True)
        return None


# ============ WTTR.IN FALLBACK ============
def _fetch_wttr():
    global _wttr_cache

    if _wttr_cache["data"] and (time.time() - _wttr_cache["ts"]) < 300:
        print("wttr.in: из кэша", flush=True)
        return _wttr_cache["data"]

    try:
        url = "https://wttr.in/Minsk?format=j1"
        print("wttr.in: запрашиваю данные...", flush=True)
        r = requests.get(url, timeout=10, verify=False)
        if r.status_code != 200:
            print(f"wttr.in: status={r.status_code}", flush=True)
            return None
        data = r.json()
        _wttr_cache["data"] = data
        _wttr_cache["ts"] = time.time()
        print("wttr.in: получено и закэшировано", flush=True)
        return data
    except Exception as e:
        print(f"wttr.in: ошибка: {e}", flush=True)
        return None


def _wttr_to_hourly(wttr_data):
    if not wttr_data:
        return None
    try:
        result = {"time": [], "temperature_2m": [], "wind_speed_10m": [], "weather_code": []}
        code_map = {
            "113": 0, "116": 2, "119": 3, "122": 3, "143": 45,
            "248": 45, "260": 45, "200": 95, "386": 95, "392": 95,
            "176": 61, "263": 51, "266": 51, "293": 61, "296": 61,
            "299": 63, "302": 63, "305": 65, "308": 65, "311": 51,
            "314": 51, "353": 80, "356": 82, "359": 82,
            "227": 73, "230": 75, "320": 71, "323": 71, "326": 71,
            "329": 73, "332": 73, "335": 75, "338": 75,
            "368": 71, "371": 75, "374": 51, "377": 51,
            "179": 71, "182": 51, "185": 51, "281": 51, "284": 51,
            "350": 51, "362": 51, "365": 51,
        }
        for day in wttr_data.get("weather", [])[:3]:
            for slot in day.get("hourly", []):
                time_str = slot.get("time", "0").zfill(4)
                hh = time_str[:-2].zfill(2)
                mm = time_str[-2:]
                date = day.get("date", "")
                dt_str = f"{date}T{hh}:{mm}"
                result["time"].append(dt_str)
                result["temperature_2m"].append(float(slot.get("tempC", 0)))
                result["wind_speed_10m"].append(round(float(slot.get("windspeedKmph", 0)) / 3.6, 1))
                wttr_code = slot.get("weatherCode", "113")
                result["weather_code"].append(code_map.get(wttr_code, 0))
        return result
    except Exception as e:
        print(f"wttr.in: ошибка hourly: {e}", flush=True)
        return None


def _wttr_to_daily(wttr_data):
    if not wttr_data:
        return None
    try:
        result = {
            "time": [], "temperature_2m_max": [], "temperature_2m_min": [],
            "weather_code": [], "wind_speed_10m_max": [], "precipitation_sum": [],
            "sunrise": [], "sunset": [],
        }
        code_map = {"113": 0, "116": 2, "119": 3, "122": 3, "143": 45,
                    "248": 45, "260": 45, "200": 95, "386": 95, "392": 95,
                    "176": 61, "296": 61, "299": 63, "302": 63, "305": 65,
                    "308": 65, "353": 80, "356": 82, "359": 82}

        def to_24h(t):
            try:
                dt = datetime.strptime(t.strip(), "%I:%M %p")
                return dt.strftime("%H:%M")
            except Exception:
                return t[:5]

        for day in wttr_data.get("weather", [])[:3]:
            result["time"].append(day.get("date"))
            result["temperature_2m_max"].append(float(day.get("maxtempC", 0)))
            result["temperature_2m_min"].append(float(day.get("mintempC", 0)))

            astro = day.get("astronomy", [{}])[0]
            sunrise = astro.get("sunrise", "06:00")
            sunset = astro.get("sunset", "19:00")
            result["sunrise"].append(to_24h(sunrise))
            result["sunset"].append(to_24h(sunset))

            hourly = day.get("hourly", [{}])
            code = 0
            if hourly:
                wttr_code = hourly[0].get("weatherCode", "113")
                code = code_map.get(wttr_code, 0)
            result["weather_code"].append(code)

            max_wind = 0
            precip = 0
            for slot in day.get("hourly", []):
                w = float(slot.get("windspeedKmph", 0)) / 3.6
                if w > max_wind:
                    max_wind = w
                precip += float(slot.get("precipMM", 0))
            result["wind_speed_10m_max"].append(round(max_wind))
            result["precipitation_sum"].append(round(precip, 1))

        return result
    except Exception as e:
        print(f"wttr.in: ошибка daily: {e}", flush=True)
        return None


def _get_forecast_data():
    om = _fetch_open_meteo()
    if om and "hourly" in om:
        return om, "Open-Meteo"

    wttr = _fetch_wttr()
    if wttr:
        hourly = _wttr_to_hourly(wttr)
        daily = _wttr_to_daily(wttr)
        if hourly and daily:
            om_style = {
                "hourly": hourly,
                "daily": daily,
                "current": {
                    "temperature_2m": float(wttr["current_condition"][0]["temp_C"]),
                    "wind_speed_10m": round(float(wttr["current_condition"][0]["windspeedKmph"]) / 3.6, 1),
                    "relative_humidity_2m": int(wttr["current_condition"][0]["humidity"]),
                    "weather_code": 0,
                    "visibility": int(wttr["current_condition"][0].get("visibility", 10)) * 1000,
                    "wind_gusts_10m": None,
                }
            }
            return om_style, "wttr.in"

    return None, "none"


# ============ WMO КОДЫ ============
def _wmo_emoji(code):
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


# ============ ТЕКУЩАЯ ПОГОДА ============
def get_weather():
    try:
        metar = get_metar_data()
        forecast_data, forecast_src = _get_forecast_data()

        daily = (forecast_data or {}).get("daily", {})
        sunrise_iso = daily.get("sunrise", [None])[0] if daily.get("sunrise") else None
        sunset_iso = daily.get("sunset", [None])[0] if daily.get("sunset") else None

        def to_hm(iso):
            if not iso:
                return None
            if "T" in iso:
                return iso.split("T")[1][:5]
            return iso

        sunrise = to_hm(sunrise_iso)
        sunset = to_hm(sunset_iso)

        if metar:
            temp = metar.get("temp", 0)
            wind_speed = metar.get("wind_speed", 0)
            cloud_emoji = metar.get("cloud_emoji", "⛅")
            cloud_text = metar.get("cloud_text", "Облачно")
            visibility = metar.get("visibility", 10000)
            weather_text = metar.get("weather_text") or ""
            weather_emoji = metar.get("weather_emoji") or ""
            dew_point = metar.get("dew_point")
            is_rain = metar.get("is_rain", False)
            is_thunder = metar.get("is_thunder", False)

            wind_gust = metar.get("wind_gust")
            if wind_gust is None:
                om_cur = (forecast_data or {}).get("current", {})
                gust_om = om_cur.get("wind_gusts_10m")
                if gust_om:
                    wind_gust = round(gust_om)
            if wind_speed == 0:
                wind_gust = None

            source = "METAR (аэропорт Минск)"
        else:
            cur = (forecast_data or {}).get("current", {})
            if not cur:
                print("Нет данных ни из METAR, ни из прогноза", flush=True)
                return None

            temp = round(cur.get("temperature_2m", 0))
            wind_speed = round(cur.get("wind_speed_10m", 0))
            wind_gust_val = cur.get("wind_gusts_10m")
            wind_gust = round(wind_gust_val) if wind_gust_val else None
            weather_code = cur.get("weather_code", 0)
            emoji, text = _wmo_emoji(weather_code)

            cloud_emoji = emoji
            cloud_text = text
            weather_text = text
            weather_emoji = emoji
            dew_point = None
            visibility = int(cur.get("visibility") or 10000)
            is_rain = weather_code in (51, 53, 55, 61, 63, 65, 80, 81, 82)
            is_thunder = weather_code in (95, 96, 99)
            source = f"Прогноз ({forecast_src})"

        feels_like = calculate_feels_like(temp, wind_speed)
        humidity = calculate_humidity(temp, dew_point) if dew_point is not None else None
        if humidity is None:
            om_cur = (forecast_data or {}).get("current", {})
            humidity = round(om_cur.get("relative_humidity_2m", 0)) or None

        print(f"✅ Weather: temp={temp}, humidity={humidity}, source={source}", flush=True)

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
            "source": source,
            "forecast_source": forecast_src
        }
    except Exception as e:
        print(f"❌ Ошибка погоды: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None


# ============ ПРОГНОЗ НА ЗАВТРА ============
def get_forecast_tomorrow():
    try:
        forecast_data, src = _get_forecast_data()
        if not forecast_data:
            print("Прогноз: нет данных", flush=True)
            return None

        daily = forecast_data.get("daily", {})
        hourly = forecast_data.get("hourly", {})
        if len(daily.get("time", [])) < 2:
            print("Прогноз: недостаточно данных", flush=True)
            return None

        date_iso = daily["time"][1]
        temp_max = round(daily["temperature_2m_max"][1])
        temp_min = round(daily["temperature_2m_min"][1])
        temp_avg = round((temp_max + temp_min) / 2)
        weather_code = daily["weather_code"][1]
        precip_sum = daily.get("precipitation_sum", [0, 0])[1]

        hourly_times = hourly.get("time", [])
        hourly_winds = hourly.get("wind_speed_10m", [])
        tomorrow_winds = []
        for i, t_str in enumerate(hourly_times):
            try:
                t_dt = datetime.fromisoformat(t_str)
                if t_dt.strftime("%Y-%m-%d") == date_iso:
                    tomorrow_winds.append(hourly_winds[i])
            except Exception:
                continue

        if tomorrow_winds:
            wind_speed_avg = round(sum(tomorrow_winds) / len(tomorrow_winds))
            wind_speed_max = round(max(tomorrow_winds))
        else:
            wind_speed_avg = round(daily["wind_speed_10m_max"][1])
            wind_speed_max = round(daily["wind_speed_10m_max"][1])

        emoji, text = _wmo_emoji(weather_code)
        is_rain = weather_code in (51, 53, 55, 61, 63, 65, 80, 81, 82)
        is_thunder = weather_code in (95, 96, 99)

        # Если осадков ожидается много, но код показывает "пасмурно" — это дождь
        if precip_sum and precip_sum > 1 and not is_rain:
            is_rain = True
            if precip_sum > 5:
                emoji, text = "🌧️", "Сильный дождь"
            else:
                emoji, text = "🌧️", "Дождь"

        date_obj = datetime.strptime(date_iso, "%Y-%m-%d")

        print(f"✅ Прогноз завтра ({src}): {temp_min}–{temp_max}°C, ветер {wind_speed_avg} м/с (макс {wind_speed_max}), {text}, осадки {precip_sum}мм", flush=True)

        return {
            "date": date_obj.strftime("%d.%m.%Y"),
            "temp_avg": temp_avg,
            "temp_max": temp_max,
            "temp_min": temp_min,
            "wind_speed": wind_speed_avg,
            "wind_gust": wind_speed_max,
            "rain_total": round(precip_sum, 1) if precip_sum else 0,
            "condition": f"{emoji} {text}",
            "is_rain": is_rain,
            "is_thunder": is_thunder
        }
    except Exception as e:
        print(f"Ошибка прогноза на завтра: {e}", flush=True)
        return None


# ============ КОРОТКИЙ ПРОГНОЗ ============
def get_short_forecast():
    try:
        forecast_data, src = _get_forecast_data()
        if not forecast_data or "hourly" not in forecast_data:
            return {"next_hour": "нет данных", "next_period": "нет данных",
                    "next_period_label": "—", "source": "none", "current_temp": None}

        hourly = forecast_data["hourly"]
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        winds = hourly.get("wind_speed_10m", [])
        codes = hourly.get("weather_code", [])

        now = datetime.now(MINSK_TZ).replace(tzinfo=None)
        current_hour = now.hour
        today = now.date()

        # Определяем следующий период суток
        if 6 <= current_hour <= 11:
            next_period = "day"
            target_start, target_end = 12, 18
            target_date = today
            next_label = "ДЕНЬ"
        elif 12 <= current_hour <= 17:
            next_period = "evening"
            target_start, target_end = 18, 23
            target_date = today
            next_label = "ВЕЧЕР"
        elif 18 <= current_hour <= 22:
            next_period = "night"
            target_start, target_end = 23, 30
            target_date = today
            next_label = "НОЧЬ"
        else:
            next_period = "morning"
            target_start, target_end = 6, 12
            if current_hour <= 5:
                target_date = today
            else:
                target_date = today + timedelta(days=1)
            next_label = "УТРО"

        # Текущий час из прогноза (для дельты)
        current_idx = 0
        min_diff_cur = float("inf")
        for i, t_str in enumerate(times):
            try:
                t_dt = datetime.fromisoformat(t_str)
                diff = abs((t_dt - now).total_seconds())
                if diff < min_diff_cur:
                    min_diff_cur = diff
                    current_idx = i
            except Exception:
                continue
        current_temp = round(temps[current_idx]) if current_idx < len(temps) else None

        # Ближайший час к "сейчас + 3 часа"
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

        # Собираем следующий период
        period_temps = []
        period_winds = []
        period_codes = []
        for i, t_str in enumerate(times):
            try:
                t_dt = datetime.fromisoformat(t_str)
                if next_period == "night":
                    if t_dt.date() == target_date and t_dt.hour >= 23:
                        period_temps.append(temps[i])
                        period_winds.append(winds[i])
                        period_codes.append(codes[i])
                    elif t_dt.date() == target_date + timedelta(days=1) and t_dt.hour <= 5:
                        period_temps.append(temps[i])
                        period_winds.append(winds[i])
                        period_codes.append(codes[i])
                else:
                    if t_dt.date() == target_date and target_start <= t_dt.hour < target_end:
                        period_temps.append(temps[i])
                        period_winds.append(winds[i])
                        period_codes.append(codes[i])
            except Exception:
                continue

        if period_temps:
            avg_t = round(sum(period_temps) / len(period_temps))
            avg_w = round(sum(period_winds) / len(period_winds))
            _, cond = _wmo_emoji(period_codes[0])
            next_period_value = f"{avg_t}°C, {cond}, {avg_w} м/с"
        else:
            next_period_value = "нет данных"

        print(f"✅ Short forecast ({src}): {next_hour} | {next_label}: {next_period_value} | прогноз сейчас: {current_temp}°C", flush=True)
        return {
            "next_hour": next_hour,
            "next_period": next_period_value,
            "next_period_label": next_label,
            "source": src,
            "current_temp": current_temp
        }
    except Exception as e:
        print(f"Ошибка короткого прогноза: {e}", flush=True)
        return {"next_hour": "нет данных", "next_period": "нет данных",
                "next_period_label": "—", "source": "none", "current_temp": None}
