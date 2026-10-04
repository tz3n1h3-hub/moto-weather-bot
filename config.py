import os
from datetime import timedelta, timezone

# ============ ВЕРСИЯ ============
BOT_VERSION = "1.9.43"
BOT_VERSION_DATE = "2026-10-04"
BOT_VERSION_NOTIFY = False

BOT_CHANGELOG = [
    ("1.9.43", "04.10.2026", "Убраны разделители ————— из сообщения", False),
    ("1.9.42", "04.10.2026", "【J】: Версия бота + цитата автора", False),
    ("1.9.41", "04.10.2026", "【B】+【C】объединены", False),
    ("1.9.40", "04.10.2026", "【G】/【H】: риск как в 【B】", False),
    ("1.9.39", "04.10.2026", "Дизайн риска · цитаты · облачность: спутники", False),
    ("1.9.38", "04.10.2026", "【F2】видимость: только выбросы", False),
    ("1.9.37", "04.10.2026", "Фикс отступа block_de", False),
    ("1.9.36", "03.10.2026", "✈️ иконка", False),
    ("1.9.35", "03.10.2026", "texts.py + formatters.py", False),
    ("1.9.34", "03.10.2026", "Порядок блоков", False),
    ("1.9.33", "03.10.2026", "ПРЕДПОЛЁТНАЯ: '+ '", False),
    ("1.9.32", "03.10.2026", "ПРЕДПОЛЁТНАЯ: +перед каждой", False),
    ("1.9.31", "03.10.2026", "ПРЕДПОЛЁТНАЯ: с новой строки", False),
    ("1.9.30", "03.10.2026", "【D】+【E】= ПРЕДПОЛЁТНАЯ", False),
    ("1.9.29", "03.10.2026", "Порядок блоков", False),
    ("1.9.28", "03.10.2026", "Убраны рекомендации из 【C】", False),
    ("1.9.27", "03.10.2026", "night_score по twilight", False),
    ("1.9.26", "03.10.2026", "Убран дубль 'Доп. свет'", False),
    ("1.9.25", "03.10.2026", "Маркеры 【A】-【J】 в <code>", False),
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
