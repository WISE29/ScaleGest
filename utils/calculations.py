"""
Règles métier de calcul — Scale Gest V2
Les taux sont lus depuis la base de données (table settings).
Fallback sur les constantes si appelé hors contexte Flask.
"""

from datetime import date
import calendar

# ── Taux par défaut (utilisés si la DB n'est pas accessible) ─────────────────
CHATTER_COMMISSION_RATE = 0.08
MANAGER_TEAM_RATE       = 0.02
MANAGER_PERSONAL_RATE   = 0.05
RECRUITER_RATE          = 0.01


def _get_rate(key: str, default: float) -> float:
    """Lit un taux depuis la DB si possible, sinon retourne le défaut."""
    try:
        from models import get_setting
        return get_setting(key, default)
    except Exception:
        return default


# ── Chatter ──────────────────────────────────────────────────────────────────

def chatter_base_commission(ca_net: float) -> float:
    rate = _get_rate("chatter_rate", CHATTER_COMMISSION_RATE)
    return round(ca_net * rate, 2)


def chatter_final_salary(ca_net: float, total_bonuses: float, total_penalties: float) -> float:
    return round(chatter_base_commission(ca_net) - total_penalties + total_bonuses, 2)


# ── Manager ───────────────────────────────────────────────────────────────────

def manager_team_commission(ca_total_team: float) -> float:
    rate = _get_rate("manager_team_rate", MANAGER_TEAM_RATE)
    return round(ca_total_team * rate, 2)


def manager_personal_commission(ca_personal: float) -> float:
    rate = _get_rate("manager_personal_rate", MANAGER_PERSONAL_RATE)
    return round(ca_personal * rate, 2)


def manager_total_remuneration(ca_chatters: float, ca_manager: float) -> dict:
    """
    Calcule la rémunération manager complète.
    Inclut le fixe mensuel configurable.
    """
    ca_total      = ca_chatters + ca_manager
    comm_team     = manager_team_commission(ca_total)
    comm_personal = manager_personal_commission(ca_manager)
    fixed         = _get_rate("manager_fixed", 0.0)
    total         = round(comm_team + comm_personal + fixed, 2)
    return {
        "ca_chatters":         ca_chatters,
        "ca_manager":          ca_manager,
        "ca_total":            ca_total,
        "commission_team":     comm_team,
        "commission_personal": comm_personal,
        "fixed":               fixed,
        "total":               total,
    }


# ── Recruteur ─────────────────────────────────────────────────────────────────

def recruiter_commission(ca_total: float) -> float:
    rate = _get_rate("recruiter_rate", RECRUITER_RATE)
    return round(ca_total * rate, 2)


# ── Objectif / Projection ─────────────────────────────────────────────────────

def objective_stats(objective: float, ca_realised: float, month: int, year: int) -> dict:
    today         = date.today()
    days_in_month = calendar.monthrange(year, month)[1]
    first_day     = date(year, month, 1)
    last_day      = date(year, month, days_in_month)

    if today < first_day:
        days_elapsed, days_remaining = 0, days_in_month
    elif today > last_day:
        days_elapsed, days_remaining = days_in_month, 0
    else:
        days_elapsed   = (today - first_day).days + 1
        days_remaining = (last_day - today).days

    ca_remaining   = max(0.0, round(objective - ca_realised, 2))
    progression    = round(ca_realised / objective * 100, 2) if objective > 0 else 0.0
    daily_avg      = round(ca_realised / days_elapsed, 2)    if days_elapsed > 0 else 0.0
    projection     = round(daily_avg * days_in_month, 2)     if days_elapsed > 0 else 0.0
    needed_per_day = round(ca_remaining / days_remaining, 2) if days_remaining > 0 else 0.0

    return {
        "objective":      objective,
        "ca_realised":    ca_realised,
        "ca_remaining":   ca_remaining,
        "progression":    progression,
        "days_in_month":  days_in_month,
        "days_elapsed":   days_elapsed,
        "days_remaining": days_remaining,
        "daily_avg":      daily_avg,
        "projection":     projection,
        "needed_per_day": needed_per_day,
    }
