import json
import time
from datetime import datetime

import requests

from config import (
    MINSK_TZ, UPSTASH_URL, UPSTASH_TOKEN,
    FEEDBACK_TTL_DAYS, FEEDBACK_PREFIX, FEEDBACK_ANTISPAM_SEC,
)

UPSTASH_ENABLED = bool(UPSTASH_URL and UPSTASH_TOKEN)

FEEDBACK_PARAMS = {
    "visibility": {"emoji": "🌫️", "label": "Видимость"},
    "wind":       {"emoji": "💨", "label": "Ветер"},
    "rain":       {"emoji": "🌧️", "label": "Осадки"},
    "temp":       {"emoji": "🌡️", "label": "Температура"},
    "road":       {"emoji": "💧", "label": "Дорога (мокрая/скользкая)"},
    "fog":        {"emoji": "🌫️", "label": "Туман (не показан)"},
    "other":      {"emoji": "❓", "label": "Другое"},
}

FEEDBACK_DIRECTIONS = {
    "less":      {"emoji": "🔽", "label": "Реально меньше"},
    "more":      {"emoji": "🔼", "label": "Реально больше"},
    "not_shown": {"emoji": "❌", "label": "Не показано, а есть"},
    "wrong":     {"emoji": "⚠️", "label": "Другое"},
}


def _redis(cmd, *args):
    if not UPSTASH_ENABLED:
        return None
    try:
        url = f"{UPSTASH_URL}/{cmd}"
        if args:
            url += "/" + "/".join(str(a) for a in args)
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"},
            timeout=5
        )
        if r.status_code != 200:
            return None
        return r.json().get("result")
    except Exception:
        return None


def _feedback_key(ts, user_id):
    return f"{FEEDBACK_PREFIX}{ts}:{user_id}"


def save_feedback(user_id, param, direction, user_comment, weather_snapshot, shown_value=""):
    if not UPSTASH_ENABLED:
        print("⚠️ feedback: Redis отключён, жалоба не сохранена", flush=True)
        return False

    ts = int(time.time())
    key = _feedback_key(ts, user_id)

    data = {
        "user_id": user_id,
        "param": param,
        "direction": direction,
        "shown_value": shown_value,
        "user_comment": user_comment or "",
        "weather_data": weather_snapshot or {},
        "time": datetime.now(MINSK_TZ).isoformat(),
        "ts": ts,
    }

    try:
        _redis("set", key, json.dumps(data, ensure_ascii=False))
        _redis("expire", key, FEEDBACK_TTL_DAYS * 24 * 3600)
        print(f"📝 feedback saved: {param}/{direction} от {user_id}", flush=True)
        return True
    except Exception as e:
        print(f"❌ feedback save: {e}", flush=True)
        return False


def check_antispam(user_id):
    if not UPSTASH_ENABLED:
        return True, 0
    try:
        keys = _redis("keys", f"{FEEDBACK_PREFIX}*:{user_id}")
        if not keys or not isinstance(keys, list):
            return True, 0

        now = int(time.time())
        latest_ts = 0
        for k in keys:
            try:
                parts = k.split(":")
                if len(parts) >= 2:
                    ts = int(parts[1])
                    if ts > latest_ts:
                        latest_ts = ts
            except Exception:
                continue

        if latest_ts == 0:
            return True, 0

        elapsed = now - latest_ts
        if elapsed >= FEEDBACK_ANTISPAM_SEC:
            return True, 0

        return False, FEEDBACK_ANTISPAM_SEC - elapsed
    except Exception as e:
        print(f"⚠️ feedback antispam: {e}", flush=True)
        return True, 0


def get_all_feedback(days=7):
    if not UPSTASH_ENABLED:
        return []
    try:
        keys = _redis("keys", f"{FEEDBACK_PREFIX}*")
        if not keys or not isinstance(keys, list):
            return []

        now = int(time.time())
        cutoff = now - days * 24 * 3600
        result = []

        for k in keys:
            try:
                parts = k.split(":")
                if len(parts) < 3:
                    continue
                ts = int(parts[1])
                if ts < cutoff:
                    continue
                raw = _redis("get", k)
                if raw:
                    result.append(json.loads(raw))
            except Exception:
                continue

        result.sort(key=lambda x: x.get("ts", 0), reverse=True)
        return result
    except Exception as e:
        print(f"⚠️ feedback list: {e}", flush=True)
        return []


def get_feedback_stats(days=7):
    items = get_all_feedback(days)
    stats = {}

    for item in items:
        param = item.get("param", "other")
        direction = item.get("direction", "wrong")

        if param not in stats:
            stats[param] = {"total": 0, "less": 0, "more": 0,
                            "not_shown": 0, "wrong": 0, "last": None}

        stats[param]["total"] += 1
        if direction in stats[param]:
            stats[param][direction] += 1
        stats[param]["last"] = item.get("time")

    return stats


def format_feedback_report(days=7, limit=5):
    items = get_all_feedback(days)
    if not items:
        return f"📊 <b>Фидбэк за {days} дней</b>\n\n<i>Пока нет жалоб.</i>"

    stats = get_feedback_stats(days)
    sorted_params = sorted(stats.items(), key=lambda x: -x[1]["total"])

    lines = [f"📊 <b>Фидбэк за {days} дней</b>\n"]
    lines.append(f"Всего жалоб: <b>{len(items)}</b>\n")

    for param, s in sorted_params[:5]:
        meta = FEEDBACK_PARAMS.get(param, {"emoji": "❓", "label": param})
        lines.append(f"{meta['emoji']} <b>{meta['label']}</b>: {s['total']}")
        if s["less"] > 0:
            lines.append(f"   🔽 меньше: {s['less']}")
        if s["more"] > 0:
            lines.append(f"   🔼 больше: {s['more']}")
        if s["not_shown"] > 0:
            lines.append(f"   ❌ не показано: {s['not_shown']}")
        lines.append("")

    lines.append(f"<b>Последние {min(limit, len(items))}:</b>")
    for item in items[:limit]:
        t = item.get("time", "?")[:16].replace("T", " ")
        meta = FEEDBACK_PARAMS.get(item.get("param"), {"emoji": "❓", "label": "?"})
        dir_meta = FEEDBACK_DIRECTIONS.get(item.get("direction"), {"emoji": "?", "label": "?"})
        comment = item.get("user_comment", "")
        comment_str = f" — «{comment}»" if comment else ""
        lines.append(f"• {t} {meta['emoji']} {meta['label']} {dir_meta['emoji']}{comment_str}")

    return "\n".join(lines)


def format_feedback_detail(user_id):
    if not UPSTASH_ENABLED:
        return "❌ Redis отключён"
    try:
        keys = _redis("keys", f"{FEEDBACK_PREFIX}*:{user_id}")
        if not keys or not isinstance(keys, list):
            return f"ℹ️ Жалоб от {user_id} нет"

        all_items = []
        for k in keys:
            raw = _redis("get", k)
            if raw:
                all_items.append(json.loads(raw))

        if not all_items:
            return f"ℹ️ Жалоб от {user_id} нет"

        all_items.sort(key=lambda x: x.get("ts", 0), reverse=True)
        item = all_items[0]

        meta = FEEDBACK_PARAMS.get(item.get("param"), {"emoji": "❓", "label": "?"})
        dir_meta = FEEDBACK_DIRECTIONS.get(item.get("direction"), {"emoji": "?", "label": "?"})
        wd = item.get("weather_data", {}) or {}

        lines = [
            f"📋 <b>Жалоба от {user_id}</b>",
            f"⏰ {item.get('time', '?')[:16].replace('T', ' ')}",
            f"❓ {meta['emoji']} {meta['label']} — {dir_meta['emoji']} {dir_meta['label']}",
        ]

        if item.get("shown_value"):
            lines.append(f"📊 Бот показал: {item['shown_value']}")
        if item.get("user_comment"):
            lines.append(f"💬 Юзер: «{item['user_comment']}»")

        lines.append("\n<b>📡 Данные на момент:</b>")
        for src, vals in wd.items():
            if isinstance(vals, dict):
                vals_str = ", ".join(f"{k}={v}" for k, v in vals.items() if v is not None)
                lines.append(f"• {src}: {vals_str}")
            else:
                lines.append(f"• {src}: {vals}")

        return "\n".join(lines)
    except Exception as e:
        return f"⚠️ Ошибка: {e}"


def build_weather_snapshot(w, a_city):
    try:
        m = w.get("m") or {}
        om = w.get("om") or {}
        ww = w.get("w") or {}
        ow = w.get("ow") or {}

        def short(d):
            keys = ["temp", "feels_like", "humidity", "wind_speed", "wind_gust",
                    "visibility", "dew_point", "precip_mm", "clouds_pct"]
            return {k: d.get(k) for k in keys if d.get(k) is not None}

        return {
            "METAR": short(m),
            "OM": short(om),
            "wttr": short(ww),
            "OWM": short(ow),
            "risk_score": a_city.get("score") if isinstance(a_city, dict) else None,
            "sunrise": w.get("sunrise"),
            "sunset": w.get("sunset"),
            "rain_prob_now": w.get("rain_prob_now"),
            "is_rain_anywhere": w.get("is_rain_anywhere"),
            "rain_sources": w.get("rain_sources"),
        }
    except Exception as e:
        print(f"⚠️ snapshot: {e}", flush=True)
        return {}
