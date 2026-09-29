"""
Règles métier de calcul — Chatter Manager V2
Identique à la V1, aucune modification.
"""

from datetime import date
import calendar

CHATTER_COMMISSION_RATE = 0.08
MANAGER_TEAM_RATE       = 0.02
MANAGER_PERSONAL_RATE   = 0.05


def chatter_base_commission(ca_net: float) -> float:
    return round(ca_net * CHATTER_COMMISSION_RATE, 2)


def chatter_final_salary(ca_net: float, total_bonuses: float, total_penalties: float) -> float:
    return round(chatter_base_commission(ca_net) - total_penalties + total_bonuses, 2)


def manager_team_commission(ca_total_team: float) -> float:
    return round(ca_total_team * MANAGER_TEAM_RATE, 2)


def manager_personal_commission(ca_personal: float) -> float:
    return round(ca_personal * MANAGER_PERSONAL_RATE, 2)


def manager_total_remuneration(ca_chatters: float, ca_manager: float) -> dict:
    ca_total      = ca_chatters + ca_manager
    comm_team     = manager_team_commission(ca_total)
    comm_personal = manager_personal_commission(ca_manager)
    return {
        "ca_chatters":        ca_chatters,
        "ca_manager":         ca_manager,
        "ca_total":           ca_total,
        "commission_team":    comm_team,
        "commission_personal": comm_personal,
        "total":              round(comm_team + comm_personal, 2),
    }


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

    ca_remaining = max(0.0, round(objective - ca_realised, 2))
    progression  = round(ca_realised / objective * 100, 2) if objective > 0 else 0.0
    daily_avg    = round(ca_realised / days_elapsed, 2)    if days_elapsed > 0 else 0.0
    projection   = round(daily_avg * days_in_month, 2)     if days_elapsed > 0 else 0.0
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
