from datetime import datetime, timedelta

from config import MINSK_TZ
from weather import get_minsk_hour


# ============ СЕЗОН ============
def get_season(month=None):
    if month is None:
        month = datetime.now(MINSK_TZ).month
    if month in (5, 6, 7, 8, 9):
        return "summer"
    if month in (4, 10):
        return "shoulder"
    return "winter"


# ============ АНАЛИЗ РИСКОВ ============
def analyze_risks(weather, is_forecast=False):
    risks, recommendations = [], []
    score = 0

    wind_gust = weather.get("wind_gust") or 0
    wind_speed = weather.get("wind_speed") or 0
    temp = weather.get("temp") or 0
    rain_total = weather.get("rain_total") or weather.get("precip_mm") or 0
    is_rain = weather.get("is_rain", False)
    rain_prob_now = weather.get("rain_prob_now")
    rain_sources = weather.get("rain_sources", [])
    is_thunder = weather.get("is_thunder", False)
    is_hail = weather.get("is_hail", False)
    visibility = weather.get("visibility") or 10000
    dew_point = weather.get("dew_point")
    soil_temp = weather.get("soil_temp")

    # ---- Град ----
    if is_hail:
        risks.append("🧊 ГРАД — опасно для райдера и техники")
        score += 4
        recommendations.append("🚫 НЕ выезжай — град бьёт по шлему и технике")

    # ---- ВЕТЕР (новая градация) ----
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

    # ---- ОСАДКИ (кросс-проверка) ----
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
        src_note = ""
        if rain_sources:
            src_note = f" [{', '.join(rain_sources[:2])}]"
        prob_note = f" ~{rain_prob_now}%" if rain_prob_now and rain_prob_now >= 40 else ""
        risks.append(f"🌧️ Дождь{prob_note}{src_note} — дорога скользкая")
        score += 2
        recommendations.append("🐢 Увеличьте дистанцию, тормози плавно")
    elif rain_prob_now and rain_prob_now >= 60:
        risks.append(f"🌦️ Высокая вероятность дождя ({rain_prob_now}%)")
        score += 1
        recommendations.append("☔ Возьми дождевик — может накрыть")

    # ---- ВИДИМОСТЬ (только «сейчас») ----
    visibility_alerted = False
    if not is_forecast:
        if visibility < 500:
            risks.append(f"🌫️ КРИТИЧЕСКАЯ ВИДИМОСТЬ ({int(visibility)} м)!")
            score += 5
            recommendations.append("🚫 Остановитесь в безопасном месте")
            visibility_alerted = True
        elif visibility < 1000:
            risks.append(f"🌫️ Очень плохая видимость ({int(visibility)} м)")
            score += 3
            recommendations.append("🌫️ Включите противотуманки")
            visibility_alerted = True
        elif visibility < 2000:
            risks.append(f"🌫️ Плохая видимость ({int(visibility)} м)")
            score += 2
            recommendations.append("💡 Включите ближний свет")
            visibility_alerted = True

    # ---- ТУМАН / ВЛАГА ----
    if dew_point is not None:
        diff = temp - dew_point
        humidity = weather.get("humidity") or 0

        if diff <= 0:
            if not is_forecast:
                if visibility < 1000 and not visibility_alerted:
                    risks.append(f"🌫️ ТУМАН! Точка росы = температуре (видимость {int(visibility)} м)")
                    score += 5
                    recommendations.append("🚫 Не выезжай — туман, видимость минимальная")
                elif visibility < 1000:
                    recommendations.append("🚫 Не выезжай — туман, видимость минимальная")
        elif diff <= 2:
            if humidity >= 90:
                if is_forecast:
                    risks.append(f"🌫️ Влажно {int(humidity)} % — воздух близок к туману")
                else:
                    risks.append(f"🌫️ Влажность {int(humidity)} % — воздух близок к туману")
                score += 3
                recommendations.append("🌫️ Возможен туман — противотуманки, снизьте скорость")
            else:
                if is_forecast:
                    risks.append(f"💧 Влажно — дорога может быть мокрой ({int(humidity)} %)")
                else:
                    risks.append(f"💧 Высокая влажность {int(humidity)} %")
                score += 2
                recommendations.append("🐢 Осторожно на разметке и в поворотах")
        elif diff <= 4:
            if humidity >= 85:
                if is_forecast:
                    risks.append(f"🌧️ Дорога мокрая — не высохнет ({int(humidity)} %)")
                else:
                    risks.append(f"💧 Повышенная влажность {int(humidity)} %")
                score += 1

    # ---- ПРОГНОЗ: код погоды ----
    if is_forecast:
        weather_code = weather.get("weather_code")
        if weather_code in (45, 48):
            risks.append("🌫️ Туман")
            score += 3
            recommendations.append("🌫️ Противотуманки, снизьте скорость")
        elif weather_code in (51, 53, 55, 56, 57):
            risks.append("🌦️ Морось")
            score += 1
            recommendations.append("🐢 Скользко — увеличивайте дистанцию")

    # ---- ТЕМПЕРАТУРА ----
    if is_forecast:
        feels_like = weather.get("temp_avg", temp)
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

    # ---- ХОЛОДНАЯ ПОЧВА ----
    if soil_temp is not None and soil_temp < 5 and temp > 10:
        risks.append("🧊 Почва холодная — асфальт не прогрелся")
        score += 1
        recommendations.append("🐢 Сцепление хуже, тормози плавно")

    # ---- НОЧЬ ----
    night_score = weather.get("night_score")
    if night_score is None:
        night_score = 2 if weather.get("is_night", False) else 0

    if night_score == 2:
        risks.append("🌙 Темно — плохая видимость")
        score += 2
        recommendations.append("💡 Включите свет")
    elif night_score == 1:
        risks.append("🌆 Частично темно — видимость хуже")
        score += 1
        recommendations.append("💡 Включите свет заранее")

    # ---- ШКАЛА ----
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

    return {
        "score": min(score, 10),
        "color": color,
        "risks": risks,
        "recommendations": recommendations,
        "feels_like": feels_like,
    }


# ============ КОРОТКИЙ ВЕРДИКТ ============
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


# ============ РАЙДЕРСКИЙ ВЕРДИКТ (сезонный) ============
def get_rider_verdict(score, month=None):
    if score <= 0:
        season = get_season(month)
        if season == "summer":
            return "ДОРОГА ЧИСТАЯ — ГАЗУЙ"
        elif season == "shoulder":
            return "ДОРОГА ЧИСТАЯ — НО АСФАЛЬТ ХОЛОДНЫЙ"
        else:
            return "ЯСНО, НО АСФАЛЬТ ХОЛОДНЫЙ — ОСТОРОЖНО"
    if score <= 4:
        return "ЕХАТЬ МОЖНО — ДЕРЖИ УХО ВОСТРО"
    if score <= 6:
        return "С ОСТОРОЖНОСТЬЮ — НЕ ЛИХАЧЬ"
    if score <= 8:
        return "НЕ САДИСЬ ЗА РУЛЬ — ОПАСНО"
    return "НЕ ВЫЕЗЖАЙ СЕГОДНЯ. ЖДИ"


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


# ============ СОВЕТ ============
def get_tip(temp, humidity, is_rain, is_night, wind_speed, is_thunder, visibility,
            wind_gust=0, uv_index=0):
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

    if visibility and visibility < 1000:
        return "💡 Туман — противотуманки, скорость минимальная"

    if humidity and humidity >= 100:
        return "💡 Влажность 100 % — роса на асфальте, тормози плавно"

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
