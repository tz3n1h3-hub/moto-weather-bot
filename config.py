import os
from datetime import timedelta, timezone

# ─── НАЧАЛО CONFIG_VERSION ─────────────────────────────────
BOT_VERSION = "2.0.4"
BOT_VERSION_DATE = "2026-10-17"
BOT_VERSION_NOTIFY = False

BOT_CHANGELOG = [
    ("2.0.4", "17.10.2026", "Отладка: print в analyze_risks и send_weather · фикс twilight (смеркается ≠ темно)", False),
    ("2.0.3", "17.10.2026", "Вердикт «СЕЙЧАС ЕХАТЬ МОЖНО» подчёркнут · ЗАВТРА подчёркнуто · ветер в периодах без оценки", False),
    ("2.0.2", "17.10.2026", "Вердикт «СЕЙЧАС ЕХАТЬ МОЖНО» подчёркнут · ЗАВТРА подчёркнуто", False),
    ("2.0.1", "17.10.2026", "Фикс: видимость fallback (OM > 20000 м) · порывы в периодах · убран «Дорога чистая»", False),
    ("2.0.0", "17.10.2026", "Архитектура: METAR вне видимости/температуры · OWM основной · локальные аномалии OM · 【G】 следующий период · 【H】 по периодам · деловой визуал · 💀×N · цитаты полные · I.Ride", True),
    ("1.9.54", "13.10.2026", "Давление QFF · METAR вне формулы видимости · средняя видимость по 5 районам · OWM-проверка · цитаты JAF/TAAS/IIHS · убран Tokyo Bay · фиксы дублей", False),
    ("1.9.53", "11.10.2026", "METAR как сигнал видимости · порог дождя 0.5 мм · синергия дождь+видимость · окно «Полезные ссылки»", True),
    ("1.9.52", "11.10.2026", "Кнопка «Полезные ссылки» (заглушка) · порог «Холодно» < 8 °C", False),
    ("1.9.51", "11.10.2026", "Фикс видимости: analyze_risks на visibility_min (из районов) · формат 【B】= 【F】", False),
    ("1.9.50", "11.10.2026", "«Хуже всего» с округлением до км · видимость 【F】= 【B】", False),
    ("1.9.49", "11.10.2026", "Фиксы: морось ≠ сильный дождь · дымка 2,4 км · 'хуже всего' · видимость 【B】= 【F】", False),
    ("1.9.48", "05.10.2026", "Кнопка 'Обновить прогноз' с маленькой буквы", False),
    ("1.9.47", "05.10.2026", "Убрана кнопка 'ЧТО-ТО НЕ ТАК?'", False),
    ("1.9.46", "05.10.2026", "Кнопка 📡 Радар осадков", False),
    ("1.9.45", "05.10.2026", "Убрана цитата NHTSA", False),
    ("1.9.44", "05.10.2026", "Убрано 'Пасмурно' из рисков", False),
    ("1.9.43", "04.10.2026", "Убраны разделители —————", False),
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
# ─── КОНЕЦ CONFIG_VERSION ──────────────────────────────────

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
    {"name": "Север",   "short": "С",  "lat": 53.9500, "lon": 27.7000},
    {"name": "Юг",      "short": "Ю",  "lat": 53.8500, "lon": 27.5000},
    {"name": "Запад",   "short": "З",  "lat": 53.9200, "lon": 27.4000},
    {"name": "Восток",  "short": "В",  "lat": 53.9000, "lon": 27.7500},
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

# ============ РЕЕСТР ПОЛЕЗНЫХ ССЫЛОК ============
LINKS_DATA = {
    "minsk_scr250": {
        "category": "🏍️ МОТОСООБЩЕСТВО",
        "label": "🏍️ Minsk Scrambler",
        "description": "Крупный канал владельцев Minsk SCR и родственных моделей (Avantis City, Fuego Scrambler, Geon Scrambler, Regulmoto Fargo). Ремонт, запчасти, FAQ и другое!",
        "buttons": [
            {"label": "🏍️ Minsk Scrambler", "url": "https://t.me/minsk_scr250"},
        ],
    },
    "iride": {
        "category": "🎓 МОТОШКОЛЫ",
        "label": "🎓 I.Ride — мотошкола",
        "description": "I.Ride — команда людей, любящих мотоциклы. Обучение на категорию А, контраварийное вождение, мотоджимхана и городское вождение. Открытые тренировки на закрытой площадке. Минск. <a href=\"https://motoschool.by\">Сайт</a> · <a href=\"https://www.instagram.com/motoschoolby\">Instagram</a>",
        "buttons": [
            {"label": "💬 I.Ride — Telegram", "url": "https://t.me/Motoschool_IRide"},
        ],
    },
}

# ============ ЛОГ ПРИ СТАРТЕ ============
print(f"ℹ️ OM режим: {_OM_MODE}", flush=True)
if OPEN_METEO_PROXY_URL:
    print(f"ℹ️ OM URL: {OPEN_METEO_URL}", flush=True)
if MINSK_POINTS_ENABLED:
    print(f"ℹ️ Многоточечный OM: {len(MINSK_POINTS)} точек Минска", flush=True)
