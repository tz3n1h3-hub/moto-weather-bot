import os
from datetime import timedelta, timezone

# ============ ТОКЕНЫ ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# ============ КОНСТАНТЫ ============
MY_BOT_USERNAME = "MotoWeatherMinskBot"
MINSK_TZ = timezone(timedelta(hours=3))
USERS_FILE = "users.json"
ADMIN_ID = 8930836312

# ============ API URLs ============
METAR_URL = "https://metar.vatsim.net/UMMS"
OWM_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

# ============ КООРДИНАТЫ МИНСКА ============
MINSK_LAT = 53.9045
MINSK_LON = 27.5615