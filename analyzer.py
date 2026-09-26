from datetime import datetime, timedelta

from config import MINSK_TZ
from weather import get_minsk_hour


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО SEASON ─────────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def get_season(month=None):
    if month is None:
        month = datetime.now(MINSK_TZ).month
    if month in (5, 6, 7, 8, 9):
        return "summer"
    if month in (4, 10):
        return "shoulder"
    return "winter"
# ─── КОНЕЦ SEASON ──────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО ANALYZE_RISKS ──────────────────────────────────
# ═══════════════════════════════════════════════════════════
def analyze_risks(weather, is_forecast=False):
    risks, recommendations = [], []
    score = 0

    wind_gust = weather.get("wind_gust") or 0
    wind_speed = weather.get("wind_speed") or 0
    temp = weather.get("temp") or 0
    rain_total = weather.get("rain_total") or weather.get("precip_mm") or 0
    is_rain = weather.get("is_rain", False)
    is_drizzle = weather.get("is_drizzle", False)
    rain_prob_now = weather.get("rain_prob_now")
    rain_prob_day = weather.get("rain_prob_day")
    rain_sources = weather.get("rain_sources", [])
    is_thunder = weather.get("is_thunder", False)
    is_hail = weather.get("is_hail", False)
    visibility = weather.get("visibility") or 10000
    dew_point = weather.get("dew_point")
    humidity = weather.get("humidity") or 0
    clouds_pct = weather.get("clouds_pct") or 0
    soil_temp = weather.get("soil_temp")
    twilight = weather.get("twilight") or ""

    humidity_handled = False
    visibility_alerted = False
    twilight_handled = False

    # ─── RISK_HAIL ─────────────────────────────────────────
    if is_hail:
        risks.append("🧊 ГРАД — опасно для райдера и техники")
        score += 4
        recommendations.append("🚫 НЕ выезжай — град бьёт по шлему и технике")
    # ─── КОНЕЦ RISK_HAIL ───────────────────────────────────

    # ─── RISK_WIND ─────────────────────────────────────────
    wind_score = 0
    if wind_gust > 20:
        risks.append(f"🌪️ Штормовой ветер (порывы до {wind_gust:.0f} м/с)!")
        wind_score = 6
        recommendations.append("🚫 Категорически не выезжай")
    elif wind_gust >= 18:
        risks.append(f"🌪️ Критический ветер (порывы до {wind_gust:.0f} м/с)")
        wind_score = 5
        recommendations.append("🚫 Не выезжай — сорвёт с полосы")
    elif wind_gust >= 15:
        risks.append(f"💨 Очень сильный ветер (порывы до {wind_gust:.0f} м/с)")
        wind_score = 4
        recommendations.append("🛑 Рассмотри отказ от поездки")
    elif wind_gust >= 12:
        risks.append(f"💨 Опасные порывы (до {wind_gust:.0f} м/с)")
        wind_score = 3
        recommendations.append("⚠️ Осторожно на мостах и открытых участках, без обгонов фур")
    elif wind_gust >= 9:
        risks.append(f"🌬️ Сильные порывы (до {wind_gust:.0f} м/с)")
        wind_score = 2
        recommendations.append("🌬️ Держи руль крепче, снизь скорость")
    elif wind_gust >= 6:
        risks.append(f"💨 Свежий ветер (до {wind_gust:.0f} м/с)")
        wind_score = 1
        recommendations.append("💨 Руль крепче")

    speed_score = 0
    if wind_speed >= 13:
        speed_score = 3
        if not any("ветер" in r.lower() for r in risks):
            risks.append(f"🌬️ Сильный ветер {wind_speed:.0f} м/с")
    elif wind_speed >= 10:
        speed_score = 2
        if not any("ветер" in r.lower() for r in risks):
            risks.append(f"🌬️ Устойчивый ветер {wind_speed:.0f} м/с")
    elif wind_speed >= 7:
        speed_score = 1

    score += max(wind_score, speed_score)
    # ─── КОНЕЦ RISK_WIND ───────────────────────────────────

    # ─── RISK_RAIN ─────────────────────────────────────────
    if is_thunder:
        risks.append("⚡ ГРОЗА! Категорически запрещено")
        score += 5
        recommendations.append("🚫 НЕМЕДЛЕННО остановитесь, найдите укрытие (30 м от мото)")
    elif rain_total > 5:
        rain_str = f"{rain_total:.1f}".replace(".", ",")
        risks.append(f"🌧️ СИЛЬНЫЙ ДОЖДЬ ({rain_str} мм)")
        score += 4
        recommendations.append("🐢 Увеличьте дистанцию, снизьте скорость")
    elif rain_total > 1:
        rain_str = f"{rain_total:.1f}".replace(".", ",")
        risks.append(f"🌧️ Дождь ({rain_str} мм)")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию, избегайте резких манёвров")
    elif is_rain:
        risks.append("🌧️ Дождь — дорога скользкая")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию, тормози плавно")
    elif is_drizzle:
        risks.append("🌦️ Морось — скользко")
        score += 1
        recommendations.append("🐢 Осторожно на разметке, тормози плавно")
    elif rain_prob_now and rain_prob_now >= 80:
        risks.append(f"☔️ Дождь почти наверняка ({rain_prob_now}%)")
        score += 3
        recommendations.append("☔ Дождевик обязателен")
    elif rain_prob_now and rain_prob_now >= 50:
        risks.append(f"🌧️ Вероятен дождь ({rain_prob_now}%)")
        score += 2
        recommendations.append("☔ Возьми дождевик")
    elif rain_prob_now and rain_prob_now >= 40:
        risks.append(f"🌦️ Возможен дождь ({rain_prob_now}%)")
        score += 1
        recommendations.append("☔ Возьми дождевик")
    elif rain_prob_day and rain_prob_day >= 80:
        risks.append(f"☔️ Дождь почти наверняка в ближайшие часы ({rain_prob_day}%)")
        score += 2
        recommendations.append("☔ Дождевик обязателен")
    elif rain_prob_day and rain_prob_day >= 50:
        risks.append(f"🌧️ Вероятен дождь ({rain_prob_day}%)")
        score += 1
        recommendations.append("☔ Возьми дождевик")
    # ─── КОНЕЦ RISK_RAIN ───────────────────────────────────

    
    # ─── RISK_VISIBILITY ───────────────────────────────────
    big_spread = weather.get("visibility_big_spread", False)
    vis_min = weather.get("visibility_min") or visibility
    vis_max = weather.get("visibility_max") or visibility

    if big_spread and vis_min < 1000 and vis_max > 5000:
        km_max = int(vis_max / 1000) if vis_max >= 1000 else 0
        risks.append(f"🌫️ Туман в аэропорту ({int(vis_min)} м), в городе — {km_max} км")
        score += 2
        recommendations.append("💡 Возможна дымка — включите противотуманки")
        visibility_alerted = True
    elif visibility < 500:
        risks.append(f"🌫️ КРИТИЧЕСКАЯ ВИДИМОСТЬ ({int(visibility)} м)!")
        score += 5
        recommendations.append("🚫 Остановитесь в безопасном месте")
        visibility_alerted = True
    elif visibility < 1000:
        risks.append(f"🌫️ ТУМАН ({int(visibility)} м)")
        score += 3
        recommendations.append("🌫️ Противотуманки, минимальная скорость")
        visibility_alerted = True
    elif visibility < 2000:
        risks.append(f"🌫️ Плохая видимость ({int(visibility)} м)")
        score += 2
        recommendations.append("💡 Включите противотуманки")
        visibility_alerted = True
    elif visibility < 5000 and humidity >= 90:
        risks.append(f"🌫️ Дымка/туман возможен (видимость {int(visibility)} м)")
        score += 2
        recommendations.append("💡 Включите противотуманки, снизьте скорость")
        visibility_alerted = True
    elif visibility < 7000 and humidity >= 90:
        km = int(round(visibility / 1000)) if visibility >= 1000 else 1
        risks.append(f"🌫️ Дымка (видимость {km} км, влаж. {int(humidity)}%)")
        score += 2
        recommendations.append("🌫️ Противотуманки, дистанцию ×2, визор протирай")
        visibility_alerted = True
    # ─── КОНЕЦ RISK_VISIBILITY ─────────────────────────────

    # ─── RISK_HUMIDITY (мокрая дорога) ─────────────────────
    # Если уже идёт дождь или морось — дорога и так мокрая, дублировать не нужно
    rain_or_drizzle = is_rain or is_drizzle

    if dew_point is not None and not rain_or_drizzle:
        diff = temp - dew_point

        if diff <= 1:
            if humidity >= 90:
                risks.append(f"💧 Мокрая дорога / роса (влаг. {int(humidity)}%, роса)")
                score += 3
                recommendations.append("🐢 Тормози плавно, дистанцию ×2, осторожно на разметке")
                humidity_handled = True
            elif humidity >= 80:
                risks.append(f"💧 Возможна влага на дороге (влаг. {int(humidity)}%)")
                score += 1
                humidity_handled = True
        elif diff <= 2:
            if humidity >= 90:
                risks.append(f"🌫️ Влажность {int(humidity)} % — воздух близок к туману")
                score += 2
                recommendations.append("🌫️ Возможен туман — противотуманки, снизьте скорость")
                humidity_handled = True
            elif humidity >= 85:
                risks.append(f"💧 Высокая влажность {int(humidity)} %")
                score += 1
                humidity_handled = True
        elif diff <= 3:
            if humidity >= 80:
                risks.append(f"💧 Возможна влага на дороге (влаг. {int(humidity)}%)")
                score += 1
                humidity_handled = True
    # ─── КОНЕЦ RISK_HUMIDITY ───────────────────────────────

    # ─── RISK_ICE (изморозь, всегда) ───────────────────────
    if temp >= -3 and temp <= 3 and humidity >= 95:
        risks.append(f"🧊 ИЗМОРОЗЬ возможна — лёд на дороге (темп {int(temp)}°C, влаж. {int(humidity)}%)")
        score += 4
        recommendations.append("🧊 Осторожно на мостах и эстакадах, не тормози резко")
    # ─── КОНЕЦ RISK_ICE ────────────────────────────────────

    # ─── RISK_CLOUDS ───────────────────────────────────────
    if not is_rain and not is_drizzle and rain_total == 0 and clouds_pct >= 80:
        if not any("дождь" in r.lower() or "морось" in r.lower() for r in risks):
            risks.append(f"☁️ Пасмурно ({int(clouds_pct)}%) — возможен дождь")
            score += 1
            recommendations.append("☔ На всякий случай возьми дождевик")
    # ─── КОНЕЦ RISK_CLOUDS ─────────────────────────────────

    # ─── RISK_TWILIGHT ─────────────────────────────────────
    if not is_forecast:
        if twilight in ("смеркается", "темнеет"):
            risks.append("🌆 Смеркается — видимость хуже")
            score += 1
            recommendations.append("💡 Включите свет заранее")
            twilight_handled = True
    # ─── КОНЕЦ RISK_TWILIGHT ───────────────────────────────

    # ─── RISK_FORECAST_CODE ────────────────────────────────
    if is_forecast:
        weather_code = weather.get("weather_code")
        if weather_code in (45, 48):
            if not any("туман" in r.lower() for r in risks):
                risks.append("🌫️ Туман")
                score += 3
                recommendations.append("🌫️ Противотуманки, снизьте скорость")
        elif weather_code in (51, 53, 55, 56, 57):
            if not any("морос" in r.lower() for r in risks):
                risks.append("🌦️ Морось")
                score += 1
                recommendations.append("🐢 Скользко — увеличивайте дистанцию")
    # ─── КОНЕЦ RISK_FORECAST_CODE ──────────────────────────

    # ─── RISK_TEMP ─────────────────────────────────────────
    if is_forecast:
        feels_like = weather.get("feels_like") or weather.get("temp_avg") or temp
    else:
        feels_like = weather.get("feels_like", temp)

    if feels_like < 0:
        risks.append(f"❄️ Мороз (ощущается как {int(feels_like)} °C)")
        score += 4
        recommendations.append("🧊 Риск обледенения!")
    elif feels_like < 5:
        risks.append(f"🥶 Очень холодно ({int(feels_like)} °C)")
        score += 3
        recommendations.append("🧥 Тёплая экипировка, подогрев")
    elif feels_like < 10:
        risks.append(f"❄️ Холодно ({int(feels_like)} °C)")
        score += 1
        recommendations.append("🧥 Ветрозащита обязательна")
    elif feels_like > 35:
        risks.append(f"🔥 Очень жарко ({int(feels_like)} °C)")
        score += 2
        recommendations.append("💧 Пейте воду")
    # ─── КОНЕЦ RISK_TEMP ───────────────────────────────────

    # ─── RISK_SOIL ─────────────────────────────────────────
    if soil_temp is not None and soil_temp < 5 and temp > 10:
        risks.append("🧊 Почва холодная — асфальт не прогрелся")
        score += 1
        recommendations.append("🐢 Сцепление хуже, тормози плавно")
    # ─── КОНЕЦ RISK_SOIL ───────────────────────────────────

    # ─── RISK_NIGHT ────────────────────────────────────────
    night_score = weather.get("night_score")
    if night_score is None:
        night_score = 2 if weather.get("is_night", False) else 0

    if night_score == 2:
        if not any("темно" in r.lower() for r in risks):
            risks.append("🌙 Темно — плохая видимость")
            score += 2
            recommendations.append("💡 Включите свет")
    elif night_score == 1:
        if not twilight_handled and not any("темн" in r.lower() or "смеркается" in r.lower() for r in risks):
            risks.append("🌆 Частично темно — видимость хуже")
            score += 1
            recommendations.append("💡 Включите свет заранее")
    # ─── КОНЕЦ RISK_NIGHT ──────────────────────────────────

    # ─── RISK_SCALE ────────────────────────────────────────
    if score >= 9:
        color = "💀"
    elif score >= 7:
        color = "🔴"
    elif score >= 5:
        color = "🟠"
    elif score >= 3:
        color = "🟡"
    else:
        color = "🟢"
    # ─── КОНЕЦ RISK_SCALE ──────────────────────────────────

    return {
        "score": min(score, 10),
        "color": color,
        "risks": risks,
        "recommendations": recommendations,
        "feels_like": feels_like,
    }
# ─── КОНЕЦ ANALYZE_RISKS ───────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО VERDICTS ───────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def get_short_verdict(score):
    if score <= 0:
        return "БЕЗОПАСНО"
    if score <= 4:
        return "ОСТОРОЖНО"
    if score <= 6:
        return "РИСКОВАННО"
    if score <= 8:
        return "ОПАСНО"
    return "НЕ ВЫЕЗЖАЙ"


def get_rider_verdict(score, month=None, is_tomorrow=False):
    if score <= 0:
        season = get_season(month)
        if season == "summer":
            return "ЗАВТРА ДОРОГА ЧИСТАЯ — ГАЗУЙ" if is_tomorrow else "ДОРОГА ЧИСТАЯ — ГАЗУЙ"
        elif season == "shoulder":
            return "ЗАВТРА ЧИСТО — НО АСФАЛЬТ ХОЛОДНЫЙ" if is_tomorrow else "ДОРОГА ЧИСТАЯ — НО АСФАЛЬТ ХОЛОДНЫЙ"
        else:
            return "ЗАВТРА ЯСНО — АСФАЛЬТ ХОЛОДНЫЙ" if is_tomorrow else "ЯСНО, НО АСФАЛЬТ ХОЛОДНЫЙ — ОСТОРОЖНО"
    if score <= 4:
        return "ЗАВТРА МОЖНО ЕХАТЬ" if is_tomorrow else "ЕХАТЬ МОЖНО — ДЕРЖИ УХО ВОСТРО"
    if score <= 6:
        return "ЗАВТРА — С ОСТОРОЖНОСТЬЮ" if is_tomorrow else "С ОСТОРОЖНОСТЬЮ — НЕ ЛИХАЧЬ"
    if score <= 8:
        return "ЗАВТРА — НЕ САДИСЬ ЗА РУЛЬ" if is_tomorrow else "НЕ САДИСЬ ЗА РУЛЬ — ОПАСНО"
    return "ЗАВТРА НЕ ВЫЕЗЖАЙ — ОПАСНО" if is_tomorrow else "НЕ ВЫЕЗЖАЙ СЕГОДНЯ. ЖДИ"
# ─── КОНЕЦ VERDICTS ────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО GEAR ───────────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def get_gear_short(temp, is_rain, is_night, wind_speed):
    gear = []
    if temp >= 25:
        gear.append("🧢 Вентиляция + перчатки")
    elif temp >= 15:
        gear.append("🧥 Лёгкая ветрозащита")
    elif temp >= 5:
        gear.append("🧥 Тёплая подкладка + подогрев ручек")
    else:
        gear.append("🧥 Термобельё + балаклава + подогрев")

    if is_rain:
        gear.append("☔ Дождевик / мембрана")
    if is_night:
        gear.append("💡 Дополнительный свет (обязательно)")
    return gear
# ─── КОНЕЦ GEAR ────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО TECH_CHECK ─────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def get_tech_check(temp, is_night, is_rain, humidity, dew_point):
    tech = [
        "Давление в шинах — на холодную",
        "Свет: ближний + стоп + поворотники",
    ]
    if is_night:
        tech.append("Визор — протри и обработай")
    elif is_rain or (humidity and humidity >= 80):
        tech.append("Визор — антизапотеватель обязателен")
    else:
        tech.append("Зеркала — под себя")
    return tech
# ─── КОНЕЦ TECH_CHECK ──────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО TIP ────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def get_tip(temp, humidity, is_rain, is_night, wind_speed, is_thunder, visibility,
            wind_gust=0, uv_index=0, is_drizzle=False):
    import random

    if is_thunder:
        return "💡 Гроза — глуши мотор, отойди на 30 м от мото, в укрытие"

    if temp < 3 and humidity and humidity > 85:
        return "💡 Мосты и эстакады — лёд там первым. Сбрось скорость заранее"

    if temp < 0:
        return "💡 Гололёд — тормози заранее, не в повороте"

    if is_rain and is_night:
        return "💡 Дождь ночью — вдвойне скользко, снизь скорость"

    if is_rain:
        return "💡 Мокро — тормозной путь ×2, дистанцию держи двойную"

    if is_drizzle:
        return "💡 Морось — разметка скользкая, тормози плавно"

    if visibility and visibility < 1000:
        return "💡 Туман — противотуманки, скорость минимальная"

    if humidity and humidity >= 100:
        return "💡 Влажность 100 % — роса на асфальте, тормози плавно"

    if humidity and humidity >= 95:
        return "💡 Влажно — дорога скользкая, дистанцию больше"

    if humidity and humidity >= 90:
        return "💡 Воздух близок к туману — визор протри, дистанцию больше"

    if is_night:
        return "💡 Ночь — видимость хуже. Паузы каждые два часа"

    if wind_gust and wind_gust >= 12:
        return "💡 Опасные порывы — без обгонов фур, на мостах руль крепче"

    if wind_gust and wind_gust >= 8:
        return "💡 Порывы — дистанцию от фур, руль крепче, расслабь хват"

    if wind_speed and wind_speed > 8:
        return "💡 Боковой ветер — руль крепче, обгоны отложи"

    if uv_index is not None and uv_index > 5:
        return "💡 Солнце активное — закрой шею и руки"

    if temp and temp > 30:
        return "💡 Жарко — пей воду каждые 30 минут"

    default_tips = [
        "💡 Давление в шинах проверь — пять минут спасут вечер",
        "💡 Цепь смажь — перед каждым выездом",
        "💡 Тормоза проверь — 30 секунд перед стартом",
        "💡 Свет — всегда включён",
        "💡 Зеркала — под себя",
    ]
    return random.choice(default_tips)
# ─── КОНЕЦ TIP ─────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО BEST_TIME ──────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def get_best_time(sunrise=None, sunset=None):
    hour = get_minsk_hour()

    if 9 <= hour <= 18:
        return "🕐 Лучшее время для поездки: с 9:00 до 18:00 ☀️"
    elif 7 <= hour <= 9:
        return "🕐 Утро (7:00–9:00) — будьте осторожны 🌅"
    elif 18 <= hour <= 22:
        if sunset:
            return f"🕐 Вечер — закат был в {sunset}, включите свет 🌆"
        return "🕐 Вечер — включите свет 🌆"
    elif hour >= 22 or hour <= 5:
        if sunrise:
            now = datetime.now(MINSK_TZ)
            sr = now.replace(hour=0, minute=0, second=0, microsecond=0)
            try:
                h, m = map(int, sunrise.split(":"))
                sr = sr.replace(hour=h, minute=m)
            except (ValueError, AttributeError):
                return "🕐 Ночь — только с хорошим светом 🌙"

            if sr <= now:
                sr += timedelta(days=1)

            delta = sr - now
            total_min = max(0, int(delta.total_seconds() // 60))
            hours = total_min // 60
            mins = total_min % 60
            return f"🕐 Ночь — до рассвета ещё {hours} ч {mins} мин 🌙"
        return "🕐 Ночь — только с хорошим светом 🌙"

    return "🕐 Раннее утро — будьте внимательны 🌄"
# ─── КОНЕЦ BEST_TIME ───────────────────────────────────────
