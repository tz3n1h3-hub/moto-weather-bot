import os
from datetime import timedelta, timezone

# ============ ВЕРСИЯ ============
BOT_VERSION = "1.9.1"
BOT_VERSION_DATE = "2026-09-26"

BOT_VERSION_NOTIFY = False

BOT_CHANGELOG = [
    ("1.9.1", "26.09.2026", "Фикс: math_round в analyzer.py + убраны источники из рисков", False),
    ("1.9.0", "26.09.2026", "Дымка 5-7 км + видимость по районам", True),
    ("1.8.3", "26.09.2026", "Фиксы: осадки в 【F】, порог 【F2】, видимость, 'без осадков' в 【H】 + маркеры блоков", False),
    ("1.8.2", "25.09.2026", "Фикс: 'ясно' в периоде, когда идёт дождь", False),
    ("1.8.1", "25.09.2026", "Убрано дублирование рисков: дождь ≠ мокрая дорога", False),
    ("1.8.0", "25.09.2026", "Блоки 【A】-【J】, многоточечный OM (5 точек), фидбэк по блокам", True),
    ("1.7.5", "24.09.2026", "Морось ≠ дождь, единый блок видимости, night_score везде", False),
    ("1.7.4", "24.09.2026", "METAR-туман в аэропорту ≠ городской туман", False),
    ("1.7.3", "23.09.2026", "Фикс feels_like для прогноза + влага в периоде", False),
    ("1.7.2", "23.09.2026", "Фикс дубля влажности в analyzer.py", False),
    ("1.7.1", "23.09.2026", "Cloudflare Worker для OM — обход 429", False),
    ("1.7.0", "23.09.2026", "14 фиксов: туман, мокрая дорога, фидбэк", True),
    ("1.6.0", "21.09.2026", "Астрономические периоды (по Солнцу)", True),
    ("1.5.5", "21.09.2026", "Вердикт для ЗАВТРА, фильтр влажности", False),
    ("1.5.0", "21.09.2026", "Новый формат блоков НОЧЬ/ЗАВТРА", True),
    ("1.4.0", "21.09.2026", "Подписка на обновления бота", True),
    ("1.0.0", "19.09.2026", "Первый релиз: 4 источника, риск 0–10", False),
]

# ============ ТОКЕНЫ ============
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ============ КОНСТАНТЫ ============
MY_BOT_USERNAME = os.getenv("MY_BOT_USERNAME", "MotoWeatherMinskBot")
MINSK_TZ = timezone(timedelta(hours=3))
USERS_FILE = "users.json"
SUBSCRIBERS_FILE = "subscribers.json"
UPDATERS_FILE = "updaters.json"
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)

# ============ UPSTASH REDIS ============
UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

# ============ OPENWEATHERMAP ============
OWM_API_KEY = os.getenv("OWM_API_KEY")
OWM_URL = "https://api.openweathermap.org/data/2.5/weather"

# ============ OPEN-METEO через Cloudflare Worker ============
OPEN_METEO_DIRECT_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_PROXY_URL = os.getenv("OPEN_METEO_PROXY_URL", "").strip()

if OPEN_METEO_PROXY_URL:
    OPEN_METEO_URL = OPEN_METEO_PROXY_URL
    _OM_MODE = "Cloudflare Worker"
else:
    OPEN_METEO_URL = OPEN_METEO_DIRECT_URL
    _OM_MODE = "прямой api.open-meteo.com"

# ============ API URLs ============
METAR_URL = "https://metar.vatsim.net/UMMS"
METAR_FALLBACK_URL = "https://aviationweather.gov/api/data/metar?ids=UMMS&format=raw&hours=0&taf=false"

# ============ КООРДИНАТЫ МИНСКА (центр) ============
MINSK_LAT = 53.9045
MINSK_LON = 27.5615

OWM_LAT = MINSK_LAT
OWM_LON = MINSK_LON
OWM_UNITS = "metric"
OWM_LANG = "ru"

# ============ МНОГОТОЧЕЧНЫЙ ПРОГНОЗ OM (5 точек Минска) ============
MINSK_POINTS_ENABLED = True

MINSK_POINTS = [
    {"name": "Центр",   "short": "Ц",  "lat": 53.9045, "lon": 27.5615},
    {"name": "Север",   "short": "С",  "lat": 53.9500, "lon": 27.7000},   # Уручье
    {"name": "Юг",      "short": "Ю",  "lat": 53.8500, "lon": 27.5000},   # Малиновка
    {"name": "Запад",   "short": "З",  "lat": 53.9200, "lon": 27.4000},   # Каменная Горка
    {"name": "Восток",  "short": "В",  "lat": 53.9000, "lon": 27.7500},   # Шабаны
]

# Кэш многоточечного прогноза
OM_MULTI_CACHE_KEY = "om_multi_cache"
OM_MULTI_CACHE_TTL = 600  # 10 минут

# ============ АСТРОНОМИЧЕСКИЕ ПЕРИОДЫ ============
TWILIGHT_OFFSET_MIN = 90
EVENING_BEFORE_SUNSET_MIN = 60

# ============ ВЕСА ИСТОЧНИКОВ ============
RAIN_VOTE_WEIGHTS = {
    "METAR": 2.0,
    "OM": 2.0,
    "OWM": 1.5,
    "wttr": 1.0,
}
RAIN_VOTE_THRESHOLD = 3.0

# Морось = 0.25× веса дождя
DRIZZLE_VOTE_MULTIPLIER = 0.25

# ============ ФИДБЭК-СИСТЕМА ============
FEEDBACK_ENABLED = True
FEEDBACK_TTL_DAYS = 30
FEEDBACK_ANTISPAM_SEC = 3600
FEEDBACK_PREFIX = "feedback:"

# ============ ЛОГ ПРИ СТАРТЕ ============
print(f"ℹ️ OM режим: {_OM_MODE}", flush=True)
if OPEN_METEO_PROXY_URL:
    print(f"ℹ️ OM URL: {OPEN_METEO_URL}", flush=True)
if MINSK_POINTS_ENABLED:
    print(f"ℹ️ Многоточечный OM: {len(MINSK_POINTS)} точек Минска", flush=True)
