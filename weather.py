import re
import math
import time
import json
import os
import requests
import urllib3
import statistics
from datetime import datetime, timedelta

from config import (
    MINSK_TZ,
    METAR_URL, METAR_FALLBACK_URL, OPEN_METEO_URL,
    MINSK_LAT, MINSK_LON,
    OWM_API_KEY, OWM_URL, OWM_LAT, OWM_LON, OWM_UNITS, OWM_LANG,
    UPSTASH_URL, UPSTASH_TOKEN,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

NBSP = "\u00A0"


def math_round(x, digits=0):
    if x is None:
        return None
    if digits == 0:
        if x >= 0:
            return int(x + 0.5)
        return int(x - 0.5)
    from decimal import Decimal, ROUND_HALF_UP
    q = Decimal(10) ** -digits
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))


# ============ КЭШИ ============
_open_meteo_cache = {"data": None, "ts": 0, "blocked_until": 0}
_wttr_cache = {"data": None, "ts": 0}
_owm_cache = {"data": None, "ts": 0}

SOIL_CACHE_FILE = "soil_cache.json"
SOIL_CACHE_TTL = 24 * 3600
UPSTASH_ENABLED = bool(UPSTASH_URL and UPSTASH_TOKEN)


def _redis(cmd, *args):
    if not UPSTASH_ENABLED:
        return None
    try:
        url = f"{UPSTASH_URL}/{cmd}"
        if args:
            url += "/" + "/".join(str(a) for a in args)
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"},
            timeout=5
        )
        if r.status_code != 200:
            return None
        return r.json().get("result")
    except Exception:
        return None


def save_soil_cache(temp, ts=None):
    if ts is None:
        ts = int(time.time())
    if UPSTASH_ENABLED:
        _redis("set", "soil_temp:MINSK", f"{temp}|{ts}")
        _redis("expire", "soil_temp:MINSK", SOIL_CACHE_TTL)
    try:
        with open(SOIL_CACHE_FILE, "w") as f:
            json.dump({"temp": temp, "ts": ts}, f)
    except Exception as e:
        print(f"⚠️ soil cache save: {e}", flush=True)


def load_soil_cache():
    now = int(time.time())
    raw = None
    if UPSTASH_ENABLED:
        raw = _redis("get", "soil_temp:MINSK")
    if not raw:
        try:
            if os.path.exists(SOIL_CACHE_FILE):
                with open(SOIL_CACHE_FILE) as f:
                    data = json.load(f)
                    raw = f"{data['temp']}|{data['ts']}"
        except Exception:
            pass
    if not raw:
        return None, False
    try:
        temp_str, ts_str = raw.split("|")
        temp = float(temp_str)
        ts = int(ts_str)
        is_fresh = (now - ts) < SOIL_CACHE_TTL
        return temp, is_fresh
    except Exception:
        return None, False


# ============ ВСПОМОГАТЕЛЬНЫЕ ============
def get_minsk_time():
    return datetime.now(MINSK_TZ).strftime("%H:%M")


def get_minsk_hour():
    return datetime.now(MINSK_TZ).hour


def get_minsk_month():
    return datetime.now(MINSK_TZ).month


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
        return math_round(100 * math.exp(alpha), 0)
    except Exception:
        return None


def calculate_feels_like(temp, wind_speed):
    if temp <= 10 and wind_speed > 1.3:
        w = wind_speed * 3.6
        feels = 13.12 + 0.6215 * temp - 11.37 * (w ** 0.16) + 0.3965 * temp * (w ** 0.16)
        return math_round(feels, 0)
    elif temp >= 27:
        return math_round(temp + 1, 0)
    return math_round(temp, 0)


def calculate_dew_point(temp, humidity):
    if temp is None or humidity is None or humidity <= 0:
        return None
    try:
        a, b = 17.27, 237.7
        alpha = (a * temp) / (b + temp) + math.log(humidity / 100.0)
        return math_round((b * alpha) / (a - alpha), 0)
    except Exception:
        return None


def hpa_to_mmhg(hpa):
    if hpa is None:
        return None
    return math_round(hpa * 0.750062, 0)


# ============ METAR ============
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
    idx = math_round(deg / 45, 0) % 8
    return f"{dirs[idx]} ({deg}°)"


def parse_pressure_hpa(metar_text):
    match = re.search(r"\bQ(\d{4})\b", metar_text)
    if match:
        return int(match.group(1))
    match = re.search(r"\bA(\d{4})\b", metar_text)
    if match:
        inhg = int(match.group(1)) / 100
        return math_round(inhg * 33.8639, 0)
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
            speed_val = int(wind_match.group(2))
            gust_val = int(wind_match.group(4)) if wind_match.group(4) else None
            if unit == "KT":
                speed_val = math_round(speed_val * 0.514444, 0)
                if gust_val:
                    gust_val = math_round(gust_val * 0.514444, 0)
            result["wind_speed"] = speed_val
            result["wind_gust"] = gust_val
            result["wind_direction"] = parse_wind_direction(metar_text)

        temp_match = re.search(r"\b(M?\d{2})/(M?\d{2})\b", metar_text)
        if temp_match:
            def parse_t(s):
                return -int(s[1:]) if s.startswith("M") else int(s)
            result["temp"] = parse_t(temp_match.group(1))
            result["dew_point"] = parse_t(temp_match.group(2))
            if result.get("temp") is not None and result.get("dew_point") is not None:
                result["humidity"] = calculate_humidity(result["temp"], result["dew_point"])
                result["feels_like"] = calculate_feels_like(result["temp"], result.get("wind_speed", 0))

        emoji, text = parse_clouds(metar_text)
        result["weather_emoji"] = emoji
        result["cloud_text"] = text

        w_emoji, w_text, is_rain, is_thunder = parse_weather_phenomena(metar_text)
        if w_emoji:
            result["weather_emoji"] = w_emoji
            result["weather_text"] = w_text
        result["is_rain"] = is_rain
        result["is_thunder"] = is_thunder
        result["is_hail"] = "GR" in metar_text

        result["visibility"] = parse_visibility(metar_text)

        pressure = parse_pressure_hpa(metar_text)
        if pressure:
            result["pressure_hpa"] = pressure
            result["pressure_mmhg"] = hpa_to_mmhg(pressure)

        trend = parse_trend(metar_text)
        if trend:
            result["trend"] = trend

        obs_time = parse_observation_time(metar_text)
        if obs_time:
            result["observation_time"] = obs_time

        return result
    except Exception as e:
        print(f"❌ METAR: {e}", flush=True)
        return None


# ============ OPEN-METEO (429-safe) ============
def get_open_meteo_data():
    global _open_meteo_cache
    now = time.time()

    # 1. Кэш 5 минут
    if _open_meteo_cache["data"] and (now - _open_meteo_cache["ts"]) < 300:
        return _open_meteo_cache["data"]

    # 2. Блокировка после 429
    if _open_meteo_cache.get("blocked_until", 0) > now:
        remaining = int(_open_meteo_cache["blocked_until"] - now)
        print(f"⏸️ OM: в блоке ещё {remaining} сек", flush=True)
        return _open_meteo_cache["data"]

    params = {
        "latitude": MINSK_LAT,
        "longitude": MINSK_LON,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                   "precipitation,rain,weather_code,cloud_cover,pressure_msl,"
                   "surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "hourly": "temperature_2m,precipitation_probability,precipitation,"
                  "weather_code,wind_speed_10m,wind_gusts_10m,cloud_cover,uv_index,"
                  "soil_temperature_0cm",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                 "precipitation_probability_max,weather_code,wind_speed_10m_max,"
                 "wind_gusts_10m_max,uv_index_max,sunrise,sunset",
        "timezone": "Europe/Minsk",
        "forecast_days": 2,
        "wind_speed_unit": "ms",
    }

    headers_variants = [
        {"User-Agent": "MotoWeather/2.0 (bot)"},
        {"User-Agent": "curl/7.68.0"},
    ]

    for attempt, headers in enumerate(headers_variants, 1):
        try:
            print(f"OM: попытка {attempt}", flush=True)
            r = requests.get(OPEN_METEO_URL, params=params, headers=headers, timeout=15)

            if r.status_code == 200:
                data = r.json()
                _open_meteo_cache["data"] = data
                _open_meteo_cache["ts"] = now
                _open_meteo_cache["blocked_until"] = 0
                print(f"✅ OM OK (попытка {attempt})", flush=True)
                return data

            if r.status_code == 429:
                print(f"⚠️ OM: 429 — блок на 5 минут", flush=True)
                _open_meteo_cache["blocked_until"] = now + 300
                if _open_meteo_cache["data"]:
                    return _open_meteo_cache["data"]
                return None

            print(f"⚠️ OM: {r.status_code} (попытка {attempt})", flush=True)
        except Exception as e:
            print(f"❌ OM: {type(e).__name__}: {e} (попытка {attempt})", flush=True)

    return None


# ============ OWM ============
def get_owm_data():
    global _owm_cache
    if not OWM_API_KEY:
        return None
    now = time.time()
    if _owm_cache["data"] and (now - _owm_cache["ts"]) < 300:
        return _owm_cache["data"]
    try:
        params = {
            "lat": OWM_LAT, "lon": OWM_LON,
            "appid": OWM_API_KEY, "units": OWM_UNITS, "lang": OWM_LANG,
        }
        r = requests.get(OWM_URL, params=params, timeout=10)
        if r.status_code != 200:
            print(f"⚠️ OWM: {r.status_code}", flush=True)
            return None
        data = r.json()
        _owm_cache["data"] = data
        _owm_cache["ts"] = now
        return data
    except Exception as e:
        print(f"❌ OWM: {e}", flush=True)
        return None


# ============ WTTR ============
def get_wttr_data():
    global _wttr_cache
    now = time.time()
    if _wttr_cache["data"] and (now - _wttr_cache["ts"]) < 300:
        return _wttr_cache["data"]
    try:
        r = requests.get(
            "https://wttr.in/Minsk?format=j1",
            timeout=10,
            headers={"User-Agent": "curl/7.68.0"}
        )
        if r.status_code != 200:
            print(f"⚠️ wttr: {r.status_code}", flush=True)
            return None
        data = r.json()
        _wttr_cache["data"] = data
        _wttr_cache["ts"] = now
        return data
    except Exception as e:
        print(f"❌ wttr: {e}", flush=True)
        return None


# ============ ГЛАВНАЯ СБОРКА ============
def get_weather():
    m = get_metar_data()
    om_raw = get_open_meteo_data()
    w_raw = get_wttr_data()
    ow_raw = get_owm_data()

    om = None
    soil_temp_now = None
    if om_raw and om_raw.get("current"):
        cur = om_raw["current"]
        om = {
            "temp": math_round(cur.get("temperature_2m"), 0),
            "feels_like": math_round(cur.get("apparent_temperature"), 0),
            "humidity": math_round(cur.get("relative_humidity_2m"), 0),
            "wind_speed": math_round(cur.get("wind_speed_10m"), 0),
            "wind_gust": math_round(cur.get("wind_gusts_10m"), 0) if cur.get("wind_gusts_10m") else None,
            "wind_direction": cur.get("wind_direction_10m"),
            "visibility": None,
            "pressure_mmhg": hpa_to_mmhg(cur.get("pressure_msl")),
            "pressure_hpa": cur.get("pressure_msl"),
            "clouds_pct": cur.get("cloud_cover"),
            "precip_mm": cur.get("precipitation"),
            "is_rain": (cur.get("precipitation") or 0) > 0 or (cur.get("rain") or 0) > 0,
            "weather_code": cur.get("weather_code"),
            "soil_temp": None,
            "uv_index": None,
        }

    if om_raw and om_raw.get("hourly") and om_raw["hourly"].get("time"):
        try:
            now_iso = datetime.now(MINSK_TZ).strftime("%Y-%m-%dT%H:00")
            times = om_raw["hourly"]["time"]
            soil_vals = om_raw["hourly"].get("soil_temperature_0cm", [])
            if now_iso in times and soil_vals:
                idx = times.index(now_iso)
                if idx < len(soil_vals) and soil_vals[idx] is not None:
                    soil_temp_now = math_round(soil_vals[idx], 0)
        except Exception as e:
            print(f"⚠️ soil parse: {e}", flush=True)

    if soil_temp_now is not None:
        save_soil_cache(soil_temp_now)
    else:
        cached, is_fresh = load_soil_cache()
        if cached is not None:
            soil_temp_now = cached

    if om:
        om["soil_temp"] = soil_temp_now

    w = None
    if w_raw and w_raw.get("current_condition"):
        cc = w_raw["current_condition"][0]
        w = {
            "temp": math_round(float(cc.get("temp_C", 0)), 0),
            "feels_like": math_round(float(cc.get("FeelsLikeC", 0)), 0),
            "humidity": math_round(float(cc.get("humidity", 0)), 0),
            "wind_speed": math_round(float(cc.get("windspeedKmph", 0)) / 3.6, 0),
            "wind_gust": math_round(float(cc.get("WindGustKmph", 0)) / 3.6, 0) if cc.get("WindGustKmph") else None,
            "wind_direction": cc.get("winddir16Point"),
            "visibility": math_round(float(cc.get("visibility", 10)) * 1000, 0),
            "pressure_mmhg": math_round(float(cc.get("pressure", 1013)) * 0.750062, 0),
            "clouds_pct": math_round(float(cc.get("cloudcover", 0)), 0),
            "precip_mm": float(cc.get("precipMM", 0) or 0),
            "is_rain": any(x in (cc.get("weatherDesc", [{}])[0].get("value", "") or "").lower()
                          for x in ["rain", "drizzle", "shower"]),
            "uv_index": math_round(float(cc.get("uvIndex", 0)), 0) if cc.get("uvIndex") else None,
        }

    ow = None
    if ow_raw:
        try:
            main = ow_raw.get("main", {})
            wind = ow_raw.get("wind", {})
            clouds = ow_raw.get("clouds", {})
            vis = ow_raw.get("visibility")
            ow = {
                "temp": math_round(main.get("temp"), 0),
                "feels_like": math_round(main.get("feels_like"), 0),
                "humidity": math_round(main.get("humidity"), 0),
                "wind_speed": math_round(wind.get("speed"), 0),
                "wind_gust": math_round(wind.get("gust"), 0) if wind.get("gust") else None,
                "wind_direction": wind.get("deg"),
                "visibility": vis,
                "pressure_mmhg": hpa_to_mmhg(main.get("pressure")),
                "clouds_pct": clouds.get("all"),
                "precip_mm": (ow_raw.get("rain", {}) or {}).get("1h", 0),
                "is_rain": "rain" in [w.get("main", "").lower() for w in ow_raw.get("weather", [])],
                "uv_index": None,
            }
        except Exception as e:
            print(f"⚠️ OWM parse: {e}", flush=True)

    rain_prob_now = None
    rain_prob_day = None
    om_says_rain_now = False

    if om_raw and om_raw.get("hourly") and om_raw["hourly"].get("time"):
        try:
            now_dt = datetime.now(MINSK_TZ)
            times = om_raw["hourly"]["time"]
            probs = om_raw["hourly"].get("precipitation_probability", [])
            precs = om_raw["hourly"].get("precipitation", [])
            codes = om_raw["hourly"].get("weather_code", [])

            now_iso = now_dt.strftime("%Y-%m-%dT%H:00")
            if now_iso in times:
                idx = times.index(now_iso)
                if idx < len(probs):
                    rain_prob_now = probs[idx]
                if idx < len(precs) and (precs[idx] or 0) > 0.1:
                    om_says_rain_now = True
                if idx < len(codes) and codes[idx] in (51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99):
                    om_says_rain_now = True

            future_probs = []
            for i, t in enumerate(times):
                try:
                    t_dt = datetime.fromisoformat(t).replace(tzinfo=MINSK_TZ)
                except Exception:
                    continue
                if now_dt <= t_dt <= now_dt + timedelta(hours=6) and i < len(probs):
                    if probs[i] is not None:
                        future_probs.append(probs[i])
            if future_probs:
                rain_prob_day = max(future_probs)
        except Exception as e:
            print(f"⚠️ rain_prob: {e}", flush=True)

    is_rain_anywhere = om_says_rain_now
    rain_sources = []
    if m and m.get("is_rain"):
        is_rain_anywhere = True
        rain_sources.append("METAR")
    if w and w.get("is_rain"):
        is_rain_anywhere = True
        rain_sources.append("wttr")
    if ow and ow.get("is_rain"):
        is_rain_anywhere = True
        rain_sources.append("OWM")
    if om_says_rain_now:
        rain_sources.append("OM")

    if not is_rain_anywhere and rain_prob_now and rain_prob_now >= 40:
        is_rain_anywhere = True
        rain_sources.append(f"OM ({rain_prob_now}%)")

    sunrise, sunset = None, None
    if om_raw and om_raw.get("daily"):
        try:
            sunrise = om_raw["daily"]["sunrise"][0].split("T")[1][:5]
            sunset = om_raw["daily"]["sunset"][0].split("T")[1][:5]
        except Exception:
            pass

    if not sunrise or not sunset:
        sunrise, sunset = _calc_sun_times()

    result = {
        "m": m,
        "om": om,
        "w": w,
        "ow": ow,
        "sunrise": sunrise,
        "sunset": sunset,
        "is_night": is_night_now(sunrise, sunset),
        "rain_prob_now": rain_prob_now,
        "rain_prob_day": rain_prob_day,
        "is_rain_anywhere": is_rain_anywhere,
        "rain_sources": rain_sources,
        "sources_live": [],
        "formula": "(M + OM + W + OW) / 4",
    }

    for code, src in [("M", m), ("OM", om), ("W", w), ("OW", ow)]:
        if src:
            result["sources_live"].append(code)

    return result


# ============ СЛИЯНИЕ ============
def merge_weather_data(w):
    if not w:
        return None

    sources = [s for s in [w.get("m"), w.get("om"), w.get("w"), w.get("ow")] if s]

    if not sources:
        return None

    def gather(key):
        return [s.get(key) for s in sources if s.get(key) is not None]

    def filter_outliers(values, threshold=2.0):
        if len(values) < 3:
            return values
        try:
            mean = statistics.mean(values)
            stdev = statistics.stdev(values) if len(values) > 1 else 0
            if stdev == 0:
                return values
            return [v for v in values if abs(v - mean) <= threshold * stdev]
        except Exception:
            return values

    def avg(values):
        if not values:
            return None
        return sum(values) / len(values)

    result = {}
    keys = ["temp", "feels_like", "humidity", "wind_speed", "wind_gust",
            "visibility", "pressure_mmhg", "clouds_pct", "precip_mm",
            "dew_point", "uv_index", "soil_temp"]

    for key in keys:
        vals = gather(key)
        if not vals:
            result[key] = None
            continue
        filtered = filter_outliers(vals)
        result[key] = math_round(avg(filtered), 0) if key != "precip_mm" else round(avg(filtered), 1)

    result["is_rain"] = w.get("is_rain_anywhere", False)
    result["rain_sources"] = w.get("rain_sources", [])
    result["rain_prob_now"] = w.get("rain_prob_now")
    result["rain_prob_day"] = w.get("rain_prob_day")

    result["is_thunder"] = any(s.get("is_thunder") for s in sources)
    result["is_hail"] = any(s.get("is_hail") for s in sources)
    result["wind_direction"] = (w.get("m") or {}).get("wind_direction")

    uv_vals = gather("uv_index")
    if uv_vals:
        result["uv_index"] = math_round(sum(uv_vals) / len(uv_vals), 0)

    result["sources_live"] = w.get("sources_live", [])
    result["formula"] = w.get("formula", "")
    result["sunrise"] = w.get("sunrise")
    result["sunset"] = w.get("sunset")
    result["is_night"] = w.get("is_night", False)

    agree_values = []
    for key, unit in [("temp", "°C"), ("wind_speed", "м/с"),
                       ("humidity", "%"), ("dew_point", "°C"), ("visibility", "км")]:
        vals = gather(key)
        if len(vals) >= 2:
            spread = max(vals) - min(vals)
            if spread > 0:
                agree_values.append((spread, unit))
    result["agree_values"] = agree_values

    if len(sources) >= 4:
        result["agreement"] = "высокое"
    elif len(sources) == 3:
        result["agreement"] = "среднее"
    else:
        result["agreement"] = "низкое"

    return result


# ============ КРАТКИЙ ПРОГНОЗ ============
def get_short_forecast():
    om_raw = get_open_meteo_data()
    if not om_raw or not om_raw.get("hourly"):
        return {"next_period": "нет данных", "next_period_title": "—", "rain_prob": None}

    try:
        now_dt = datetime.now(MINSK_TZ)
        times = om_raw["hourly"]["time"]
        temps = om_raw["hourly"].get("temperature_2m", [])
        probs = om_raw["hourly"].get("precipitation_probability", [])
        precs = om_raw["hourly"].get("precipitation", [])
        winds = om_raw["hourly"].get("wind_speed_10m", [])
        gusts = om_raw["hourly"].get("wind_gusts_10m", [])
        codes = om_raw["hourly"].get("weather_code", [])

        target_indices = []
        for i, t in enumerate(times):
            try:
                t_dt = datetime.fromisoformat(t).replace(tzinfo=MINSK_TZ)
            except Exception:
                continue
            if now_dt < t_dt <= now_dt + timedelta(hours=6):
                target_indices.append(i)

        if not target_indices:
            return {"next_period": "нет данных", "next_period_title": "—", "rain_prob": None}

        avg_temp = math_round(sum(temps[i] for i in target_indices if i < len(temps)) / len(target_indices), 0)
        avg_wind = math_round(sum(winds[i] for i in target_indices if i < len(winds)) / len(target_indices), 0)
        max_gust = max((gusts[i] for i in target_indices if i < len(gusts) and gusts[i] is not None), default=None)
        max_prob = max((probs[i] for i in target_indices if i < len(probs) and probs[i] is not None), default=None)
        sum_precip = sum(precs[i] for i in target_indices if i < len(precs) and precs[i] is not None)

        hour_now = now_dt.hour
        if 6 <= hour_now < 12:
            title = "🌅 УТРОМ"
        elif 12 <= hour_now < 18:
            title = "☀️ ДНЁМ"
        elif 18 <= hour_now < 24:
            title = "🌆 ВЕЧЕРОМ"
        else:
            title = "🌙 НОЧЬЮ"

        cond = "ясно"
        if max_prob and max_prob >= 50:
            cond = "дождь"
        elif sum_precip > 0.5:
            cond = "дождь"

        text_parts = [f"{avg_temp} °C", f"{avg_wind} м/с"]
        if max_gust and max_gust > avg_wind:
            text_parts.append(f"(до {max_gust} м/с)")
        text_parts.append(cond)
        next_period = " · ".join(text_parts)

        return {
            "next_period": next_period,
            "next_period_title": title,
            "rain_prob": max_prob,
        }
    except Exception as e:
        print(f"⚠️ short_forecast: {e}", flush=True)
        return {"next_period": "нет данных", "next_period_title": "—", "rain_prob": None}


# ============ ПРОГНОЗ НА ЗАВТРА ============
def get_forecast_tomorrow():
    om_raw = get_open_meteo_data()
    if not om_raw or not om_raw.get("daily"):
        return None

    try:
        d = om_raw["daily"]
        if len(d.get("time", [])) < 2:
            return None

        idx = 1
        tmin = math_round(d["temperature_2m_min"][idx], 0)
        tmax = math_round(d["temperature_2m_max"][idx], 0)
        wind = math_round(d["wind_speed_10m_max"][idx], 0)
        gust = math_round(d["wind_gusts_10m_max"][idx], 0) if d.get("wind_gusts_10m_max") else None
        rain_prob = d.get("precipitation_probability_max", [None, None])[idx]
        rain_sum = d.get("precipitation_sum", [0, 0])[idx]
        weather_code = d.get("weather_code", [0, 0])[idx]
        uv_max = d.get("uv_index_max", [0, 0])[idx]

        cond_map = {
            0: ("Ясно", "☀️"), 1: ("Преимущественно ясно", "🌤️"),
            2: ("Переменная облачность", "⛅"), 3: ("Пасмурно", "☁️"),
            45: ("Туман", "🌫️"), 48: ("Изморозь", "🌫️"),
            51: ("Лёгкая морось", "🌦️"), 53: ("Морось", "🌦️"), 55: ("Сильная морось", "🌧️"),
            61: ("Слабый дождь", "🌦️"), 63: ("Дождь", "🌧️"), 65: ("Сильный дождь", "🌧️"),
            71: ("Слабый снег", "🌨️"), 73: ("Снег", "❄️"), 75: ("Сильный снег", "❄️"),
            80: ("Ливни", "🌧️"), 95: ("Гроза", "⛈️"),
            96: ("Гроза с градом", "⛈️"), 99: ("Сильная гроза с градом", "⛈️"),
        }
        cond_text, cond_emoji = cond_map.get(weather_code, ("—", ""))

        return {
            "temp_min": tmin,
            "temp_max": tmax,
            "temp_avg": math_round((tmin + tmax) / 2, 0),
            "wind_speed": wind,
            "wind_gust": gust,
            "rain_prob": rain_prob,
            "rain_sum": round(rain_sum, 1) if rain_sum else 0,
            "condition_text": cond_text,
            "condition_emoji": cond_emoji,
            "weather_code": weather_code,
            "uv_index": math_round(uv_max, 0) if uv_max is not None else None,
        }
    except Exception as e:
        print(f"⚠️ forecast_tomorrow: {e}", flush=True)
        return None
