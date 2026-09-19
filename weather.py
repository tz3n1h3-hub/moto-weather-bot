import re
import math
import time
import requests
import urllib3
from datetime import datetime, timedelta

from config import (
    MINSK_TZ,
    METAR_URL, METAR_FALLBACK_URL, OPEN_METEO_URL,
    MINSK_LAT, MINSK_LON,
    OWM_API_KEY, OWM_URL, OWM_LAT, OWM_LON, OWM_UNITS, OWM_LANG,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============ ГЛОБАЛЬНЫЙ КЭШ ============
_open_meteo_cache = {"data": None, "ts": 0}
_wttr_cache = {"data": None, "ts": 0}
_owm_cache = {"data": None, "ts": 0}


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


def _calc_sun_times():
    try:
        now = datetime.now(MINSK_TZ)
        n = now.timetuple().tm_yday
        lat = MINSK_LAT
        lon = MINSK_LON
        tz_offset = 3
        decl = -23.44 * math.cos(math.radians(360 / 365 * (n + 10)))
        cos_ha = -math.tan(math.radians(lat)) * math.tan(math.radians(decl))
        if cos_ha > 1 or cos_ha < -1:
            return None, None
        ha = math.degrees(math.acos(cos_ha))
        b = math.radians(360 / 364 * (n - 81))
        eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
        solar_noon_utc_min = 720 - 4 * lon - eot
        sunrise_min = int(solar_noon_utc_min - 4 * ha + tz_offset * 60) % 1440
        sunset_min = int(solar_noon_utc_min + 4 * ha + tz_offset * 60) % 1440
        sh, sm = sunrise_min // 60, sunrise_min % 60
        eh, em = sunset_min // 60, sunset_min % 60
        return f"{sh:02d}:{sm:02d}", f"{eh:02d}:{em:02d}"
    except Exception as e:
        print(f"⚠️ Астро-расчёт: {e}", flush=True)
        return None, None


def is_night_now(sunrise=None, sunset=None):
    if not sunrise or not sunset:
        sunrise, sunset = _calc_sun_times()
    if not sunrise or not sunset:
        return is_night_time()
    try:
        now = datetime.now(MINSK_TZ)
        h_s, m_s = map(int, sunrise.split(":"))
        h_e, m_e = map(int, sunset.split(":"))
        now_min = now.hour * 60 + now.minute
        sunrise_min = h_s * 60 + m_s
        sunset_min = h_e * 60 + m_e
        return now_min < sunrise_min or now_min >= sunset_min
    except (ValueError, AttributeError):
        return is_night_time()


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


def get_twilight_state(sunrise=None, sunset=None):
    """🌇 На улице: светло / смеркается / темнеет / темно."""
    if not sunrise or not sunset:
        return "темно" if is_night_time() else "светло"
    try:
        now = datetime.now(MINSK_TZ)
        h_s, m_s = map(int, sunrise.split(":"))
        h_e, m_e = map(int, sunset.split(":"))
        sr = now.replace(hour=h_s, minute=m_s, second=0, microsecond=0)
        ss = now.replace(hour=h_e, minute=m_e, second=0, microsecond=0)
        if sr - timedelta(hours=1) <= now < sr:
            return "рассветает"
        if sr <= now < sr + timedelta(hours=1):
            return "светает"
        if ss - timedelta(hours=1) <= now < ss:
            return "смеркается"
        if ss <= now < ss + timedelta(hours=1):
            return "темнеет"
        if now < sr - timedelta(hours=1) or now >= ss + timedelta(hours=1):
            return "темно"
        return "светло"
    except Exception:
        return "темно" if is_night_time() else "светло"


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


def calculate_dew_point(temp, humidity):
    if temp is None or humidity is None:
        return None
    try:
        return round(temp - (100 - humidity) / 5)
    except Exception:
        return None


def hpa_to_mmhg(hpa):
    if hpa is None:
        return None
    return round(hpa * 0.750062)


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
        return "🌤️", "Ясно"
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


def parse_wind_direction(metar_text):
    match = re.search(r"\b(\d{3}|VRB)(\d{2,3})(G(\d{2,3}))?(KT|MPS)\b", metar_text)
    if not match:
        return None
    direction = match.group(1)
    if direction == "VRB":
        return "переменный"
    deg = int(direction)
    if deg == 0:
        return "штиль"
    dirs = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
    idx = round(deg / 45) % 8
    return f"{dirs[idx]} ({deg}°)"


def parse_pressure_hpa(metar_text):
    match = re.search(r"\bQ(\d{4})\b", metar_text)
    if match:
        return int(match.group(1))
    match = re.search(r"\bA(\d{4})\b", metar_text)
    if match:
        inhg = int(match.group(1)) / 100
        return round(inhg * 33.8639)
    return None


def parse_trend(metar_text):
    if "NOSIG" in metar_text:
        return {"type": "NOSIG", "text": "Без изменений"}
    match = re.search(r"\b(BECMG|TEMPO)\b(?:\s+TL?\d{4})?(.+?)(?=\s+(BECMG|TEMPO|NOSIG)|$)", metar_text)
    if not match:
        return None
    trend_type = match.group(1)
    conditions = match.group(2).strip()
    prefix = "Через 2 часа" if trend_type == "BECMG" else "Временами"
    parts = []
    vis_match = re.search(r"\b(\d{4})\b", conditions)
    if vis_match:
        vis = int(vis_match.group(1))
        if vis == 9999:
            parts.append("видимость 10+ км")
        elif vis >= 1000:
            km = vis / 1000
            if km == int(km):
                parts.append(f"видимость {int(km)} км")
            else:
                parts.append(f"видимость {km:.1f} км")
        else:
            parts.append(f"видимость {vis} м")
    phenomena_map = {
        "FG": "туман", "BR": "дымка", "HZ": "мгла",
        "RA": "дождь", "SHRA": "ливневый дождь",
        "+RA": "сильный дождь", "-RA": "слабый дождь",
        "DZ": "морось", "SN": "снег", "+SN": "сильный снег",
        "-SN": "слабый снег", "SHSN": "ливневый снег",
        "TS": "гроза", "TSRA": "гроза с дождём", "GR": "град",
    }
    found = []
    for code in ["TSRA", "SHRA", "SHSN", "+RA", "-RA", "+SN", "-SN",
                 "FG", "BR", "HZ", "RA", "DZ", "SN", "TS", "GR"]:
        if code in conditions and phenomena_map[code] not in found:
            found.append(phenomena_map[code])
    if found:
        parts.append(", ".join(found))
    if parts:
        text = f"{prefix}: {', '.join(parts)}"
    else:
        text = f"{prefix}: изменения"
    return {"type": trend_type, "text": text}


def parse_observation_time(metar_text):
    match = re.search(r"\b(\d{2})(\d{2})(\d{2})Z\b", metar_text)
    if not match:
        return None
    day, hh, mm = match.group(1), int(match.group(2)), int(match.group(3))
    msk_hh = (hh + 3) % 24
    return f"{msk_hh:02d}:{mm:02d}"


def _fetch_metar_text():
    for url in (METAR_URL, METAR_FALLBACK_URL):
        try:
            print(f"METAR: {url}", flush=True)
            response = requests.get(url, timeout=10)
            if response.status_code == 200 and "UMMS" in response.text:
                return response.text.strip()
            print(f"METAR: {url} → {response.status_code}", flush=True)
        except Exception as e:
            print(f"METAR: ошибка {url}: {e}", flush=True)
    return None


def get_metar_data():
    try:
        metar_text = _fetch_metar_text()
        if not metar_text:
            print("METAR: пусто", flush=True)
            return None
        print(f"METAR OK: {metar_text}", flush=True)
        result = {}
        wind_match = re.search(r"\b(\d{3}|VRB)(\d{2,3})(G(\d{2,3}))?(KT|MPS)\b", metar_text)
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
        result["wind_direction"] = parse_wind_direction(metar_text)
        result["pressure_hpa"] = parse_pressure_hpa(metar_text)
        result["obs_time"] = parse_observation_time(metar_text)
        result["trend"] = parse_trend(metar_text)
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
            f"&current=temperature_2m,apparent_temperature,"
            f"wind_speed_10m,wind_gusts_10m,wind_direction_10m,"
            f"relative_humidity_2m,dew_point_2m,weather_code,"
            f"visibility,pressure_msl,"
            f"uv_index,cloud_cover,precipitation,soil_temperature_6cm"
            f"&hourly=temperature_2m,wind_speed_10m,weather_code,precipitation_probability"
            f"&daily=temperature_2m_max,temperature_2m_min,weather_code,"
            f"wind_speed_10m_max,wind_gusts_10m_max,precipitation_sum,sunrise,sunset"
            f"&timezone=Europe/Minsk"
            f"&forecast_days=3"
            f"&wind_speed_unit=ms"
        )
        print("Open-Meteo: запрос...", flush=True)
        r = requests.get(url, timeout=10)
        data = r.json()
        if "error" in data:
            print(f"Open-Meteo: {data.get('reason')}", flush=True)
            return None
        _open_meteo_cache["data"] = data
        _open_meteo_cache["ts"] = time.time()
        print("Open-Meteo: кэшировано", flush=True)
        return data
    except Exception as e:
        print(f"Open-Meteo: ошибка {e}", flush=True)
        return None


# ============ WTTR.IN ============
def _fetch_wttr():
    global _wttr_cache
    if _wttr_cache["data"] and (time.time() - _wttr_cache["ts"]) < 300:
        print("wttr.in: из кэша", flush=True)
        return _wttr_cache["data"]
    try:
        url = "https://wttr.in/Minsk?format=j1"
        print("wttr.in: запрос...", flush=True)
        r = requests.get(url, timeout=10, verify=False)
        if r.status_code != 200:
            print(f"wttr.in: {r.status_code}", flush=True)
            return None
        data = r.json()
        _wttr_cache["data"] = data
        _wttr_cache["ts"] = time.time()
        print("wttr.in: кэшировано", flush=True)
        return data
    except Exception as e:
        print(f"wttr.in: ошибка {e}", flush=True)
        return None


def _wttr_to_current(wttr_data):
    """wttr current_condition → нормализованный dict (отдельный источник W)."""
    if not wttr_data:
        return None
    try:
        cc = wttr_data.get("current_condition", [{}])[0]
        temp = float(cc.get("temp_C", 0))
        humidity = int(cc.get("humidity", 0))
        wind_kmph = float(cc.get("windspeedKmph", 0))
        wind_ms = round(wind_kmph / 3.6, 1)
        pressure = float(cc.get("pressure", 1013))
        clouds = int(cc.get("cloudcover", 0))
        precip = float(cc.get("precipMM", 0))
        visibility_m = int(cc.get("visibility", 10)) * 1000

        dew = calculate_dew_point(round(temp), humidity)

        uv_raw = cc.get("uvIndex")
        try:
            uv = int(uv_raw) if uv_raw is not None else None
        except (ValueError, TypeError):
            uv = None

        return {
            "temp": round(temp),
            "feels_like": round(float(cc.get("FeelsLikeC", temp))),
            "humidity": humidity,
            "dew_point": dew,
            "wind_speed": round(wind_ms),
            "wind_gust": None,
            "wind_direction": cc.get("winddirDegree"),
            "visibility": visibility_m,
            "pressure_hpa": round(pressure),
            "pressure_mmhg": hpa_to_mmhg(round(pressure)),
            "clouds_pct": clouds,
            "precip_mm": round(precip, 1) if precip else 0,
            "uv_index": uv,
            "soil_temp": None,
            "is_rain": precip > 0,
            "is_thunder": False,
        }
    except Exception as e:
        print(f"wttr current: {e}", flush=True)
        return None


def _wttr_to_hourly(wttr_data):
    if not wttr_data:
        return None
    try:
        result = {
            "time": [],
            "temperature_2m": [],
            "wind_speed_10m": [],
            "weather_code": [],
            "precipitation_probability": [],
        }
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
                try:
                    chance = int(slot.get("chanceofrain", 0))
                except (ValueError, TypeError):
                    chance = 0
                result["precipitation_probability"].append(chance)
        return result
    except Exception as e:
        print(f"wttr.in: ошибка hourly {e}", flush=True)
        return None


def _wttr_to_daily(wttr_data):
    if not wttr_data:
        return None
    try:
        result = {
            "time": [],
            "temperature_2m_max": [],
            "temperature_2m_min": [],
            "weather_code": [],
            "wind_speed_10m_max": [],
            "precipitation_sum": [],
            "precipitation_probability_max": [],
            "sunrise": [],
            "sunset": [],
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
            max_chance = 0
            for slot in day.get("hourly", []):
                try:
                    c = int(slot.get("chanceofrain", 0))
                    if c > max_chance:
                        max_chance = c
                except (ValueError, TypeError):
                    pass
            result["precipitation_probability_max"].append(max_chance)
        return result
    except Exception as e:
        print(f"wttr.in: ошибка daily {e}", flush=True)
        return None


# ============ OPENWEATHERMAP ============
def _fetch_owm():
    global _owm_cache
    if not OWM_API_KEY:
        return None
    if _owm_cache["data"] and (time.time() - _owm_cache["ts"]) < 300:
        print("OWM: из кэша", flush=True)
        return _owm_cache["data"]
    try:
        url = (
            f"{OWM_URL}"
            f"?lat={OWM_LAT}&lon={OWM_LON}"
            f"&units={OWM_UNITS}&lang={OWM_LANG}"
            f"&appid={OWM_API_KEY}"
        )
        print("OWM: запрос...", flush=True)
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            print(f"OWM: {r.status_code}", flush=True)
            return None
        data = r.json()
        _owm_cache["data"] = data
        _owm_cache["ts"] = time.time()
        print("OWM: кэшировано", flush=True)
        return data
    except Exception as e:
        print(f"OWM: ошибка {e}", flush=True)
        return None


def _owm_to_current(owm_data):
    if not owm_data:
        return None
    try:
        main = owm_data.get("main", {})
        wind = owm_data.get("wind", {})
        clouds = owm_data.get("clouds", {})
        rain = owm_data.get("rain", {}) or {}
        snow = owm_data.get("snow", {}) or {}
        precip = rain.get("1h", 0) + snow.get("1h", 0)

        temp = main.get("temp")
        humidity = main.get("humidity")
        dew = None
        if temp is not None and humidity is not None:
            dew = calculate_dew_point(round(temp), humidity)

        pressure_hpa = main.get("pressure")

        return {
            "temp": round(temp) if temp is not None else None,
            "feels_like": round(main.get("feels_like")) if main.get("feels_like") is not None else None,
            "humidity": humidity,
            "dew_point": dew,
            "wind_speed": round(wind.get("speed")) if wind.get("speed") is not None else None,
            "wind_gust": round(wind.get("gust")) if wind.get("gust") is not None else None,
            "wind_direction": wind.get("deg"),
            "visibility": owm_data.get("visibility"),
            "pressure_hpa": pressure_hpa,
            "pressure_mmhg": hpa_to_mmhg(pressure_hpa),
            "clouds_pct": clouds.get("all"),
            "precip_mm": round(precip, 1) if precip else 0,
            "uv_index": None,
            "soil_temp": None,
            "is_rain": precip > 0,
            "is_thunder": False,
        }
    except Exception as e:
        print(f"OWM: парсинг {e}", flush=True)
        return None


# ============ ПРОГНОЗ: OM или wttr (fallback) ============
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
                    "apparent_temperature": float(wttr["current_condition"][0].get("FeelsLikeC", wttr["current_condition"][0]["temp_C"])),
                    "wind_speed_10m": round(float(wttr["current_condition"][0]["windspeedKmph"]) / 3.6, 1),
                    "wind_direction_10m": None,
                    "relative_humidity_2m": int(wttr["current_condition"][0]["humidity"]),
                    "dew_point_2m": None,
                    "weather_code": 0,
                    "visibility": int(wttr["current_condition"][0].get("visibility", 10)) * 1000,
                    "pressure_msl": float(wttr["current_condition"][0].get("pressure", 1013)),
                    "wind_gusts_10m": None,
                    "uv_index": None,
                    "cloud_cover": None,
                    "precipitation": None,
                    "soil_temperature_6cm": None,
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
        wttr_raw = _fetch_wttr()
        owm_raw = _fetch_owm()

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
        is_night = is_night_now(sunrise, sunset)

        # ---- M ----
        m_data = None
        if metar:
            m_temp = metar.get("temp", 0)
            m_dew = metar.get("dew_point")
            m_wind = metar.get("wind_speed", 0)
            m_humidity = calculate_humidity(m_temp, m_dew) if m_dew is not None else None
            m_feels = calculate_feels_like(m_temp, m_wind)
            m_pressure = metar.get("pressure_hpa")
            m_data = {
                "temp": m_temp,
                "dew_point": m_dew,
                "humidity": m_humidity,
                "feels_like": m_feels,
                "wind_speed": m_wind,
                "wind_gust": metar.get("wind_gust"),
                "wind_direction": metar.get("wind_direction"),
                "visibility": metar.get("visibility", 10000),
                "cloud_text": metar.get("cloud_text", "Облачно"),
                "cloud_emoji": metar.get("cloud_emoji", "⛅"),
                "weather_emoji": metar.get("weather_emoji") or "",
                "weather_text": metar.get("weather_text") or "",
                "is_rain": metar.get("is_rain", False),
                "is_thunder": metar.get("is_thunder", False),
                "pressure_hpa": m_pressure,
                "pressure_mmhg": hpa_to_mmhg(m_pressure),
                "clouds_pct": None,
                "precip_mm": None,
                "uv_index": None,
                "soil_temp": None,
                "trend": metar.get("trend"),
                "obs_time": metar.get("obs_time"),
            }

        # ---- OM ----
        om_data = None
        cur = (forecast_data or {}).get("current", {})
        if cur and forecast_src == "Open-Meteo":
            om_temp = round(cur.get("temperature_2m", 0))
            om_dew = cur.get("dew_point_2m")
            om_pressure = cur.get("pressure_msl")
            om_visibility = cur.get("visibility")
            om_humidity = round(cur.get("relative_humidity_2m", 0)) or None
            om_data = {
                "temp": om_temp,
                "dew_point": round(om_dew) if om_dew is not None else None,
                "humidity": om_humidity,
                "feels_like": round(cur.get("apparent_temperature", om_temp)),
                "wind_speed": round(cur.get("wind_speed_10m", 0)),
                "wind_gust": round(cur["wind_gusts_10m"]) if cur.get("wind_gusts_10m") else None,
                "wind_direction": cur.get("wind_direction_10m"),
                "visibility": int(om_visibility) if om_visibility else None,
                "pressure_hpa": round(om_pressure) if om_pressure else None,
                "pressure_mmhg": hpa_to_mmhg(round(om_pressure)) if om_pressure else None,
                "clouds_pct": cur.get("cloud_cover"),
                "precip_mm": round(cur.get("precipitation", 0), 1),
                "uv_index": round(cur.get("uv_index")) if cur.get("uv_index") is not None else None,
                "soil_temp": round(cur["soil_temperature_6cm"]) if cur.get("soil_temperature_6cm") is not None else None,
                "is_rain": (cur.get("precipitation") or 0) > 0,
                "is_thunder": cur.get("weather_code") in (95, 96, 99),
            }
            if om_data["dew_point"] is None and om_humidity is not None:
                om_data["dew_point"] = calculate_dew_point(om_temp, om_humidity)

        # ---- W ----
        w_data = _wttr_to_current(wttr_raw)

        # ---- OW ----
        ow_data = _owm_to_current(owm_raw)

        if not any([m_data, om_data, w_data, ow_data]):
            print("Нет данных вообще", flush=True)
            return None

        sources_live = []
        if m_data: sources_live.append("M")
        if om_data: sources_live.append("OM")
        if w_data: sources_live.append("W")
        if ow_data: sources_live.append("OW")
        formula = "(" + " + ".join(sources_live) + f") / {len(sources_live)}"

        print(f"✅ Weather: M={m_data.get('temp') if m_data else None}°C, "
              f"OM={om_data.get('temp') if om_data else None}°C, "
              f"W={w_data.get('temp') if w_data else None}°C, "
              f"OW={ow_data.get('temp') if ow_data else None}°C, "
              f"live={sources_live}", flush=True)

        return {
            "m": m_data,
            "om": om_data,
            "w": w_data,
            "ow": ow_data,
            "sources_live": sources_live,
            "formula": formula,
            "forecast_source": forecast_src,
            "sunrise": sunrise,
            "sunset": sunset,
            "is_night": is_night,
        }
    except Exception as e:
        print(f"❌ Ошибка погоды: {e}", flush=True)
        return None


# ============ ПРОГНОЗ НА ЗАВТРА ============
def get_forecast_tomorrow():
    try:
        forecast_data, src = _get_forecast_data()
        if not forecast_data:
            return None
        daily = forecast_data.get("daily", {})
        hourly = forecast_data.get("hourly", {})
        if len(daily.get("time", [])) < 2:
            return None
        date_iso = daily["time"][1]
        temp_max = round(daily["temperature_2m_max"][1])
        temp_min = round(daily["temperature_2m_min"][1])
        temp_avg = round((temp_max + temp_min) / 2)
        weather_code = daily["weather_code"][1]
        precip_sum = daily.get("precipitation_sum", [0, 0])[1]
        # Проценты дождя на завтра
        daily_probs = daily.get("precipitation_probability_max", [])
        rain_prob = daily_probs[1] if len(daily_probs) > 1 else None
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
        else:
            wind_speed_avg = round(daily["wind_speed_10m_max"][1])
        daily_gusts = daily.get("wind_gusts_10m_max", [])
        if len(daily_gusts) > 1 and daily_gusts[1] is not None:
            wind_gust = round(daily_gusts[1])
        else:
            wind_gust = None
        emoji, text = _wmo_emoji(weather_code)
        is_rain = weather_code in (51, 53, 55, 61, 63, 65, 80, 81, 82)
        is_thunder = weather_code in (95, 96, 99)
        if precip_sum and precip_sum > 1 and not is_rain:
            is_rain = True
            if precip_sum > 5:
                emoji, text = "🌧️", "Сильный дождь"
            else:
                emoji, text = "🌧️", "Дождь"
        date_obj = datetime.strptime(date_iso, "%Y-%m-%d")
        return {
            "date": date_obj.strftime("%d.%m.%Y"),
            "temp_avg": temp_avg,
            "temp_max": temp_max,
            "temp_min": temp_min,
            "wind_speed": wind_speed_avg,
            "wind_gust": wind_gust,
            "rain_total": round(precip_sum, 1) if precip_sum else 0,
            "rain_prob": rain_prob,
            "condition": f"{emoji} {text}",
            "condition_emoji": emoji,
            "condition_text": text,
            "weather_code": weather_code,
            "is_rain": is_rain,
            "is_thunder": is_thunder,
            "source": src,
        }
    except Exception as e:
        print(f"Ошибка завтра: {e}", flush=True)
        return None


# ============ КОРОТКИЙ ПРОГНОЗ ============
def get_short_forecast():
    try:
        forecast_data, src = _get_forecast_data()
        if not forecast_data or "hourly" not in forecast_data:
            return {"next_hour": "нет данных", "next_period": "нет данных",
                    "next_period_label": "—", "next_period_title": "—",
                    "source": "none", "current_temp": None, "show_next_hour": False}
        hourly = forecast_data["hourly"]
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        winds = hourly.get("wind_speed_10m", [])
        codes = hourly.get("weather_code", [])
        probs = hourly.get("precipitation_probability", [])
        now = datetime.now(MINSK_TZ).replace(tzinfo=None)
        current_hour = now.hour
        today = now.date()
        if 6 <= current_hour <= 11:
            next_period = "day"
            target_start, target_end = 12, 18
            target_date = today
            next_label = "ДЕНЬ"
            next_title = "☀️ ДНЁМ"
        elif 12 <= current_hour <= 17:
            next_period = "evening"
            target_start, target_end = 18, 24
            target_date = today
            next_label = "ВЕЧЕР"
            next_title = "🌆 ВЕЧЕРОМ"
        elif 18 <= current_hour <= 23:
            next_period = "night"
            target_start, target_end = 0, 6
            target_date = today + timedelta(days=1)
            next_label = "НОЧЬ"
            next_title = "🌙 НОЧЬЮ"
        else:
            next_period = "morning"
            target_start, target_end = 6, 12
            target_date = today
            next_label = "УТРО"
            next_title = "🌅 УТРОМ"
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
            prob = probs[next_idx] if next_idx < len(probs) else None
            if prob is not None and prob > 30:
                next_hour = f"{t}°C, {cond} · {w}м/с · дождь {prob}%"
            else:
                next_hour = f"{t}°C, {cond} · {w}м/с"
        else:
            next_hour = "нет данных"
        target_hour = (current_hour + 3) % 24
        show_next_hour = True
        if next_period == "day" and 12 <= target_hour < 18:
            show_next_hour = False
        elif next_period == "evening" and 18 <= target_hour < 24:
            show_next_hour = False
        elif next_period == "night" and 0 <= target_hour < 6:
            show_next_hour = False
        elif next_period == "morning" and 6 <= target_hour < 12:
            show_next_hour = False
        period_temps = []
        period_winds = []
        period_codes = []
        period_probs = []
        for i, t_str in enumerate(times):
            try:
                t_dt = datetime.fromisoformat(t_str)
                if t_dt.date() == target_date and target_start <= t_dt.hour < target_end:
                    period_temps.append(temps[i])
                    period_winds.append(winds[i])
                    period_codes.append(codes[i])
                    if i < len(probs):
                        period_probs.append(probs[i])
            except Exception:
                continue
        if period_temps:
            avg_t = round(sum(period_temps) / len(period_temps))
            avg_w = round(sum(period_winds) / len(period_winds))
            _, cond = _wmo_emoji(period_codes[0])
            max_prob = max(period_probs) if period_probs else None
            if max_prob is not None and max_prob > 30:
                next_period_value = f"{avg_t}°C, {cond} · {avg_w}м/с · дождь {max_prob}%"
            else:
                next_period_value = f"{avg_t}°C, {cond} · {avg_w}м/с"
        else:
            next_period_value = "нет данных"
        print(f"✅ Short ({src}): {next_hour} | {next_title}: {next_period_value}", flush=True)
        return {
            "next_hour": next_hour,
            "next_period": next_period_value,
            "next_period_label": next_label,
            "next_period_title": next_title,
            "source": src,
            "current_temp": current_temp,
            "show_next_hour": show_next_hour,
        }
    except Exception as e:
        print(f"Ошибка short: {e}", flush=True)
        return {"next_hour": "нет данных", "next_period": "нет данных",
                "next_period_label": "—", "next_period_title": "—",
                "source": "none", "current_temp": None, "show_next_hour": False}


# ============ УСРЕДНЕНИЕ ПО ЖИВЫМ ИСТОЧНИКАМ ============
def merge_weather_data(w):
    """Среднее по живым источникам M / OM / W / OW. Формула — динамическая."""
    if not w:
        return None
    m = w.get("m") or {}
    om = w.get("om") or {}
    ww = w.get("w") or {}
    ow = w.get("ow") or {}

    sources = [s for s in (m, om, ww, ow) if s]
    if not sources:
        return None

    def merge_field(key):
        vals = [s.get(key) for s in sources if s.get(key) is not None]
        if not vals:
            return None
        return round(sum(vals) / len(vals), 1) if len(vals) > 1 else vals[0]

    def merge_bool(key):
        return any(s.get(key) for s in sources)

    return {
        "temp": merge_field("temp"),
        "dew_point": merge_field("dew_point"),
        "humidity": merge_field("humidity"),
        "feels_like": merge_field("feels_like"),
        "wind_speed": merge_field("wind_speed"),
        "wind_gust": merge_field("wind_gust"),
        "visibility": merge_field("visibility"),
        "pressure_hpa": merge_field("pressure_hpa"),
        "pressure_mmhg": merge_field("pressure_mmhg"),
        "clouds_pct": merge_field("clouds_pct"),
        "precip_mm": merge_field("precip_mm"),
        "uv_index": merge_field("uv_index"),
        "soil_temp": merge_field("soil_temp"),
        "cloud_text": m.get("cloud_text"),
        "cloud_emoji": m.get("cloud_emoji"),
        "weather_emoji": m.get("weather_emoji") or "",
        "weather_text": m.get("weather_text") or "",
        "is_rain": merge_bool("is_rain"),
        "is_thunder": merge_bool("is_thunder"),
        "is_night": w.get("is_night", False),
        "trend": m.get("trend"),
        "obs_time": m.get("obs_time"),
        "sources_live": w.get("sources_live", []),
        "formula": w.get("formula", ""),
        "sunrise": w.get("sunrise"),
        "sunset": w.get("sunset"),
    }
