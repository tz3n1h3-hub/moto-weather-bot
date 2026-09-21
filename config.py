import os
from datetime import timedelta, timezone

# ============ ВЕРСИЯ ============
BOT_VERSION = "1.5.2"
BOT_VERSION_DATE = "2026-09-21"

# Флаг: уведомлять ли об этой версии
BOT_VERSION_NOTIFY = False

BOT_CHANGELOG = [
    ("1.5.2", "21.09.2026", "Убрал codetabs (тормозил 20 сек), анти-спам 60 сек", False),
    ("1.5.1", "21.09.2026", "Убрал дубли про дождь в блоках НОЧЬ/ЗАВТРА", False),
    ("1.5.0", "21.09.2026", "Новый формат блоков НОЧЬ/ЗАВТРА, фикс отображения дождя", True),
    ("1.4.0", "21.09.2026", "Подписка на обновления бота", True),
    ("1.3.0", "21.09.2026", "Ночь с 22:00, фикс rain_total, wind chill до 15 °C", False),
    ("1.2.0", "20.09.2026", "Fallback wttr, прокси OM, кэш Redis", False),
    ("1.1.0", "20.09.2026", "Кросс-проверка дождя, новая градация ветра", False),
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

# OWM использует те же координаты
OWM_LAT = MINSK_LAT
OWM_LON = MINSK_LON
OWM_UNITS = "metric"
OWM_LANG = "ru"
