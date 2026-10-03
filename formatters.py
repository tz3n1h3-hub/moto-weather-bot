from decimal import Decimal, ROUND_HALF_UP

NBSP = "\u00A0"
INDENT = "     "


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО MATH_ROUND ─────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def math_round(x, digits=0):
    if x is None:
        return None
    if digits == 0:
        if x >= 0:
            return int(x + 0.5)
        return int(x - 0.5)
    q = Decimal(10) ** -digits
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))
# ─── КОНЕЦ MATH_ROUND ──────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО NUM_FORMAT ─────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def fmt_num(v):
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        return str(math_round(v, 0))
    return str(v)


def fmt_avg(values, unit=""):
    vals = [v for v in values if v is not None]
    if not vals:
        return f"—{NBSP}{unit}" if unit else "—"
    avg = sum(vals) / len(vals)
    s = str(math_round(avg, 0))
    return f"{s}{NBSP}{unit}" if unit else s


def format_visibility(v):
    if v is None:
        return "—"
    if v >= 10000:
        return f"10+{NBSP}км"
    if v >= 1000:
        km = v / 1000
        if km == int(km):
            return f"{int(km)}{NBSP}км"
        return f"{km:.1f}{NBSP}км".replace(".", ",")
    return f"{int(v)}{NBSP}м"


def fmt_spread(agree_values):
    if not agree_values:
        return None
    filtered = [(v, u) for v, u in agree_values if v and v >= 2]
    if len(filtered) < 2:
        return None
    parts = []
    for v, unit in filtered:
        v_str = str(math_round(v, 0)) if v == int(v) else f"{v:.1f}".replace(".", ",")
        parts.append(f"±{v_str}{NBSP}{unit}")
    return "📊 Разброс: " + " · ".join(parts)
# ─── КОНЕЦ NUM_FORMAT ──────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО COND_CLOUDS ────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def shorten_cond(cond):
    if not cond:
        return "—"
    cond_lower = cond.lower()
    replacements = {
        "преимущественно ясно": "ясно",
        "переменная облачность": "переменно",
        "значительная облачность": "облачно",
        "облачно с прояснениями": "прояснения",
        "преимущественно облачно": "облачно",
    }
    for k, v in replacements.items():
        if k in cond_lower:
            return v
    return cond_lower


def classify_clouds(avg_cloud_pct, metar_text):
    if avg_cloud_pct is None:
        return metar_text or "—"
    if avg_cloud_pct >= 85:
        return "пасмурно"
    if avg_cloud_pct >= 70:
        return "облачно"
    if avg_cloud_pct >= 40:
        return "переменно"
    if avg_cloud_pct >= 15:
        return "малооблачно"
    return "ясно"
# ─── КОНЕЦ COND_CLOUDS ─────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО RISK_BAR ───────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def build_risk_bar(score):
    score = max(0, min(10, score))
    if score == 0:
        return ""
    return "💀" * score
# ─── КОНЕЦ RISK_BAR ────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО UV ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def avg_uv(live_values):
    vals = [v for v in live_values if v is not None]
    if not vals:
        return None
    return math_round(sum(vals) / len(vals), 0)


def uv_level(uv):
    if uv is None:
        return ""
    if uv <= 2:
        return "низкий"
    if uv <= 5:
        return "умеренный"
    if uv <= 7:
        return "высокий"
    if uv <= 10:
        return "очень высокий"
    return "экстремальный"


def uv_advice(uv):
    if uv is None:
        return ""
    if uv <= 2:
        return "хоть в майке"
    if uv <= 5:
        return "прикрой шею"
    if uv <= 7:
        return "солнце злое — в тень"
    if uv <= 10:
        return "злое солнце — закрой всё"
    return "пекло — не выезжай днём"
# ─── КОНЕЦ UV ──────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО WIND_DIR ───────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def wind_dir_short(full):
    if not full or not isinstance(full, str):
        return None
    m = {
        "С": "С", "СВ": "С-В", "В": "В", "ЮВ": "Ю-В",
        "Ю": "Ю", "ЮЗ": "Ю-З", "З": "З", "СЗ": "С-З",
    }
    part = full.split(" ")[0]
    if part in m:
        return m[part]
    if part == "переменный":
        return "перем."
    if part == "штиль":
        return "штиль"
    return None
# ─── КОНЕЦ WIND_DIR ────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО INDENT ─────────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def indent_multiline(text, indent=INDENT):
    if not text:
        return ""
    lines = text.split("\n")
    return "\n".join(f"{indent}{line}" for line in lines)
# ─── КОНЕЦ INDENT ──────────────────────────────────────────


# ═══════════════════════════════════════════════════════════
# ─── НАЧАЛО FILTER_RAIN ────────────────────────────────────
# ═══════════════════════════════════════════════════════════
def filter_rain_risks(risks):
    if not risks:
        return []
    keywords = ("дождь", "осадк", "морось", "ливн", "влажн", "мокро")
    return [
        r for r in risks
        if not any(kw in r.lower() for kw in keywords)
    ]
# ─── КОНЕЦ FILTER_RAIN ─────────────────────────────────────
