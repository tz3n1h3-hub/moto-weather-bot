import os
from datetime import timedelta, timezone

# ============ ВЕРСИЯ ============
BOT_VERSION = "1.6.0"
BOT_VERSION_DATE = "2026-09-21"

BOT_VERSION_NOTIFY = True  # major-изменение (астрономические периоды)

BOT_CHANGELOG = [
    ("1.6.0", "21.09.2026", "Астрономические периоды (по Солнцу), диапазоны в заголовках", True),
    ("1.5.5", "21.09.2026", "Вердикт для ЗАВТРА не путает с СЕГОДНЯ, фильтр влажности", False),
    ("1.5.4", "21.09.2026", "Кнопка «ОБНОВИТЬ ПРОГНОЗ», анти-спам 3 сек", False),
    ("1.5.3", "21.09.2026", "Redis-кэш OM 30 мин, timeout 5 сек", False),
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

# ============ API URLs ============
METAR_URL = "https://metar.vatsim.net/UMMS"
METAR_FALLBACK_URL = "https://aviationweather.gov/api/data/metar?ids=UMMS&format=raw&hours=0&taf=false"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# ============ КООРДИНАТЫ МИНСКА ============
MINSK_LAT = 53.9045
MINSK_LON = 27.5615

OWM_LAT = MINSK_LAT
OWM_LON = MINSK_LON
OWM_UNITS = "metric"
OWM_LANG = "ru"

# ============ АСТРОНОМИЧЕСКИЕ ПЕРИОДЫ ============
# Смещение для сумерек (в минутах): рассвет/закат ± 90 мин
TWILIGHT_OFFSET_MIN = 90
