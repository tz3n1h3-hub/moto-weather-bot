def analyze_risks(weather, is_forecast=False):
    risks, recommendations = [], []
    score = 0

    wind_gust = weather.get("wind_gust") or 0
    wind_speed = weather.get("wind_speed", 0)
    temp = weather.get("temp", 0)
    rain_total = weather.get("rain_total", 0)
    is_rain = weather.get("is_rain", False)
    is_thunder = weather.get("is_thunder", False)
    visibility = weather.get("visibility", 10000)
    dew_point = weather.get("dew_point")

    # ВЕТЕР
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

    # ОСАДКИ
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

    # ВИДИМОСТЬ
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

    # РОСА/ТУМАН
    if not is_forecast and dew_point is not None:
        diff = temp - dew_point
        if diff <= 0:
            risks.append("🌫️ Точка росы = температуре! Туман, роса")
            score += 3
            recommendations.append("🐢 Снизьте скорость, дорога мокрая")
        elif diff <= 2:
            risks.append(f"💧 Высокая влажность (разница {diff}°C)")
            score += 2
            recommendations.append("🐢 Осторожно на разметке и в поворотах")
        elif diff <= 4:
            risks.append(f"💧 Повышенная влажность (разница {diff}°C)")
            score += 1

    # ТЕМПЕРАТУРА
    feels_like = weather.get("temp_avg", temp) if is_forecast else weather.get("feels_like", temp)

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

    # НОЧЬ
    if not is_forecast and weather.get("is_night", False):
        risks.append("🌙 Темно - плохая видимость")
        score += 2
        recommendations.append("💡 Включите свет")

    # ВЕРДИКТ
    if score >= 8:
        verdict, color = "⛔️ ОПАСНОСТЬ! НЕ РЕКОМЕНДУЕТСЯ!", "🔴"
    elif score >= 5:
        verdict, color = "⚠️ РИСКОВАННО - с осторожностью", "🟡"
    elif score >= 2:
        verdict, color = "🟡 УМЕРЕННЫЙ РИСК", "🟠"
    else:
        verdict, color = "✅ БЕЗОПАСНО - отличная погода!", "🟢"

    return {
        "score": min(score, 10),
        "verdict": verdict,
        "color": color,
        "risks": risks,
        "recommendations": recommendations,
        "feels_like": feels_like
    }


def get_detailed_gear(temp, wind_speed, is_night, is_rain, dew_point):
    gear = []

    if temp >= 25:
        gear.append("🟢 Лёгкая экипировка с сеткой")
    elif temp >= 18:
        gear.append("🟢 Стандартная экипировка")
    elif temp >= 10:
        gear.append("🟡 Ветрозащита + тёплая подкладка")
    elif temp >= 5:
        gear.append("🟠 Тёплая экипировка")
        gear.append("🔥 Подогрев ручек")
    elif temp >= 0:
        gear.append("🔴 Термобельё + полный подогрев")
    else:
        gear.append("❄️ Зимняя экипировка")

    if wind_speed > 10:
        gear.append("💨 Плотная ветрозащита")

    if is_night:
        gear.append("💡 Дополнительный свет")
        gear.append("🪞 Чистый визор")

    if is_rain:
        gear.append("🌧️ Дождевик / мембрана")
        gear.append("🧤 Водонепроницаемые перчатки")
    elif dew_point is not None and temp - dew_point <= 2:
        gear.append("💧 Антизапотеватель для визора")

    return gear


def get_best_time(sunrise=None, sunset=None):
    from weather import get_minsk_hour, MINSK_TZ
    hour = get_minsk_hour()
    now = datetime_now = __import__("datetime").datetime.now(MINSK_TZ)

    if 9 <= hour <= 18:
        return "🕐 Лучшее время для поездки: с 9:00 до 18:00 ☀️"
    elif 7 <= hour <= 9:
        return "🕐 Утро (7:00–9:00) — будьте осторожны 🌅"
    elif 18 <= hour <= 22:
        return f"🕐 Вечер — закат был в {sunset}, включите свет 🌆" if sunset else "🕐 Вечер — включите свет 🌆"
    elif 22 <= hour or hour <= 5:
        if sunrise:
            from datetime import datetime as dt, timedelta as td
            sr = dt.strptime(sunrise, "%H:%M").replace(
                year=now.year, month=now.month, day=now.day, tzinfo=MINSK_TZ
            )
            if now.hour >= 22:
                sr += td(days=1)
            elif now.hour < 6 and sr < now:
                sr += td(days=1)
            delta = sr - now
            h = int(delta.total_seconds() // 3600)
            m = int((delta.total_seconds() % 3600) // 60)
            return f"🕐 Ночь — до рассвета ещё {h} ч {m} мин 🌙"
        return "🕐 Ночь — только с хорошим светом 🌙"
    return "🕐 Раннее утро — будьте внимательны 🌄"