from datetime import datetime, timedelta

from config import MINSK_TZ
from weather import get_minsk_hour


# ============ АНАЛИЗ РИСКОВ ============
def analyze_risks(weather, is_forecast=False):
    risks, recommendations = [], []
    score = 0

    wind_gust = weather.get("wind_gust") or 0
    wind_speed = weather.get("wind_speed") or 0
    temp = weather.get("temp") or 0
    rain_total = weather.get("rain_total") or 0
    is_rain = weather.get("is_rain", False)
    is_thunder = weather.get("is_thunder", False)
    visibility = weather.get("visibility") or 10000
    dew_point = weather.get("dew_point")

    if wind_gust > 20:
        risks.append(f"🌪️ КРИТИЧЕСКИЙ ВЕТЕР (порывы до {wind_gust:.0f} м/с)!")
        score += 5
        recommendations.append("🚫 Откажитесь от поездки")
    elif wind_gust > 15:
        risks.append(f"💨 Сильный ветер (порывы до {wind_gust:.0f} м/с)")
        score += 3
        recommendations.append("🛑 Держите руль крепче, снизьте скорость")
    elif wind_speed > 10:
        risks.append(f"🌬️ Умеренный ветер {wind_speed:.0f} м/с")
        score += 1

    if is_thunder:
        risks.append("⚡ ГРОЗА! Категорически запрещено")
        score += 5
        recommendations.append("🚫 НЕМЕДЛЕННО остановитесь, найдите укрытие")
    elif rain_total > 5:
        risks.append(f"🌧️ СИЛЬНЫЙ ДОЖДЬ ({rain_total:.1f} мм)")
        score += 4
        recommendations.append("🐢 Увеличьте дистанцию, снизьте скорость")
    elif rain_total > 1:
        risks.append(f"🌧️ Дождь ({rain_total:.1f} мм)")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию, избегайте резких манёвров")
    elif is_rain:
        risks.append("🌧️ Дождь (дорога скользкая)")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию")

    if not is_forecast:
        if visibility < 500:
            risks.append(f"🌫️ КРИТИЧЕСКАЯ ВИДИМОСТЬ ({visibility} м)!")
            score += 5
            recommendations.append("🚫 Остановитесь в безопасном месте")
        elif visibility < 1000:
            risks.append(f"🌫️ Очень плохая видимость ({visibility} м)")
            score += 3
            recommendations.append("🌫️ Включите противотуманки")
        elif visibility < 2000:
            risks.append(f"🌫️ Плохая видимость ({visibility} м)")
            score += 2
            recommendations.append("💡 Включите ближний свет")

    if not is_forecast and dew_point is not None:
        diff = temp - dew_point
        humidity = weather.get("humidity") or 0

        if diff <= 0:
            if visibility < 1000:
                risks.append(f"🌫️ ТУМАН! Точка росы = температуре (видимость {visibility} м)")
                score += 5
                recommendations.append("🚫 Не выезжай — туман, видимость минимальная")
            else:
                risks.append(f"🌫️ Влажность {humidity}% — роса на асфальте")
                score += 3
                recommendations.append("🐢 Асфальт мокрый — не закладывай в поворотах")
        elif diff <= 2:
            if humidity >= 90:
                risks.append(f"🌫️ Влажность {humidity}% — воздух близок к туману")
                score += 3
                recommendations.append("🌫️ Возможен туман — противотуманки, снизьте скорость")
            else:
                risks.append(f"💧 Высокая влажность {humidity}%")
                score += 2
                recommendations.append("🐢 Осторожно на разметке и в поворотах")
        elif diff <= 4:
            if humidity >= 80:
                risks.append(f"💧 Повышенная влажность {humidity}%")
                score += 1

    if is_forecast:
        feels_like = weather.get("temp_avg", temp)
    else:
        feels_like = weather.get("feels_like", temp)

    if feels_like < 0:
        risks.append(f"❄️ Мороз (ощущается как {feels_like}°C)")
        score += 4
        recommendations.append("🧊 Риск обледенения!")
    elif feels_like < 5:
        risks.append(f"🥶 Очень холодно ({feels_like}°C)")
        score += 3
        recommendations.append("🧥 Тёплая экипировка, подогрев")
    elif feels_like < 10:
        risks.append(f"❄️ Холодно ({feels_like}°C)")
        score += 1
        recommendations.append("🧥 Ветрозащита обязательна")
    elif feels_like > 35:
        risks.append(f"🔥 Очень жарко ({feels_like}°C)")
        score += 2
        recommendations.append("💧 Пейте воду")

    if not is_forecast and weather.get("is_night", False):
        risks.append("🌙 Темно — плохая видимость")
        score += 2
        recommendations.append("💡 Включите свет")

    if score >= 8:
        verdict, color = "⛔️ ОПАСНОСТЬ! НЕ РЕКОМЕНДУЕТСЯ!", "🔴"
    elif score >= 5:
        verdict, color = "⚠️ РИСКОВАННО — с осторожностью", "🟠"
    elif score >= 2:
        verdict, color = "🟡 ОСТОРОЖНО — есть нюансы", "🟡"
    else:
        verdict, color = "✅ БЕЗОПАСНО — отличная погода!", "🟢"

    return {
        "score": min(score, 10),
        "verdict": verdict,
        "color": color,
        "risks": risks,
        "recommendations": recommendations,
        "feels_like": feels_like
    }


# ============ КОРОТКИЙ ВЕРДИКТ ============
def get_short_verdict(score):
    if score <= 1:
        return "БЕЗОПАСНО"
    if score <= 4:
        return "ОСТОРОЖНО"
    if score <= 7:
        return "РИСКОВАННО"
    return "ОПАСНО"


# ============ РАЙДЕРСКИЙ ВЕРДИКТ ============
def get_rider_verdict(score):
    if score <= 2:
        return "🟢 ДОРОГА ЧИСТАЯ — ГАЗУЙ"
    if score <= 5:
        return "🟡 ЕХАТЬ МОЖНО — ДЕРЖИ УХО ВСТРО"
    if score <= 7:
        return "🟠 С ОСТОРОЖНОСТЬЮ — НЕ ЛИХАЧЬ"
    if score <= 9:
        return "🔴 НЕ САДИСЬ ЗА РУЛЬ — ОПАСНО"
    return "⛔ НЕ ВЫЕЗЖАЙ СЕГОДНЯ. ЖДИ"


# ============ ЭКИПИРОВКА ============
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


# ============ ПОДГОТОВКА ТЕХНИКИ ============
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


# ============ ОДИН СОВЕТ ============
def get_tip(temp, humidity, is_rain, is_night, wind_speed, is_thunder, visibility):
    if is_thunder:
        return "Гроза — глуши мотор и в укрытие. Молния шуток не понимает"
    if temp < 5 and humidity and humidity > 85:
        return "Мосты и эстакады — там лёд первым. Сбрось скорость заранее"
    if temp < 0:
        return "Гололёд — не закладывай в повороты, дожми тормоз заранее"
    if is_rain:
        return "Мокро — тормозной путь ×2, дистанцию держи двойную"
    if visibility and visibility < 1000:
        return "Туман — противотуманки, скорость как по яйцам"
    if humidity and humidity >= 100:
        return "Влажность 100% — роса на асфальте, не закладывай в поворотах"
    if humidity and humidity >= 90:
        return "Воздух близок к туману — визор вниз, дистанцию больше"
    if is_night:
        return "Ночь — сова не ты. Через 2 часа устанешь, делай паузы"
    if wind_speed and wind_speed > 8:
        return "Боковой ветер — руль крепче, обгоны отложи"
    return "Давление в шинах проверь — 5 минут спасут вечер"


# ============ ЛУЧШЕЕ ВРЕМЯ ============
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
