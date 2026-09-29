"""
chatter_space.py — Espace personnel du chatter — V2
Routes préfixées /chatter/
"""

from datetime import date
from flask import Blueprint, render_template, request, abort
from flask_login import current_user

from utils.auth_helpers import chatter_required
from models import (
    MONTHS_FR,
    get_chatter, get_chatter_month_stats, get_chatter_rank,
    get_recent_sales, get_month_bonuses, get_month_penalties,
    get_available_months, get_chatter_payrolls,
    get_month_ca_chatters, get_month_ca_manager,
    get_shifts_history, get_payroll_row,
    get_chatter_models,
)
from utils.payroll import compute_payroll

chatter_bp = Blueprint("chatter_space", __name__, url_prefix="/chatter")


def _current_chatter():
    """Retourne le dict chatter de l'utilisateur connecté, ou 404."""
    if not current_user.chatter_id:
        abort(403)
    c = get_chatter(current_user.chatter_id)
    if not c:
        abort(404)
    return c


# ── Dashboard ────────────────────────────────────────────────────────────────

@chatter_bp.route("/")
@chatter_required
def dashboard():
    chatter = _current_chatter()
    today   = date.today()
    month, year = today.month, today.year

    stats = get_chatter_month_stats(chatter["id"], month, year)
    rank  = get_chatter_rank(chatter["id"], month, year)

    # Dernière fiche de paie validée
    payrolls    = get_chatter_payrolls(chatter["id"])
    last_payroll = payrolls[0] if payrolls else None

    # Shift permanent formaté
    shift_start = str(chatter.get("shift_start") or "")[:5] or None
    shift_end   = str(chatter.get("shift_end")   or "")[:5] or None

    return render_template(
        "chatter/dashboard.html",
        chatter=chatter, stats=stats, rank=rank,
        month=month, year=year, month_name=MONTHS_FR[month],
        shift_start=shift_start, shift_end=shift_end,
        last_payroll=last_payroll,
        months_fr=MONTHS_FR,
    )


# ── Mon CA ────────────────────────────────────────────────────────────────────

@chatter_bp.route("/ca")
@chatter_required
def my_ca():
    chatter = _current_chatter()
    today   = date.today()
    month   = int(request.args.get("month", today.month))
    year    = int(request.args.get("year",  today.year))

    stats        = get_chatter_month_stats(chatter["id"], month, year)
    recent_sales = get_recent_sales(chatter["id"], limit=60)
    avail        = get_available_months()

    return render_template(
        "chatter/ca.html",
        chatter=chatter, stats=stats,
        recent_sales=recent_sales,
        month=month, year=year, month_name=MONTHS_FR[month],
        available_months=avail, months_fr=MONTHS_FR,
    )


# ── Mon shift ─────────────────────────────────────────────────────────────────

@chatter_bp.route("/shift")
@chatter_required
def my_shift():
    chatter = _current_chatter()
    shift_start = str(chatter.get("shift_start") or "")[:5] or None
    shift_end   = str(chatter.get("shift_end")   or "")[:5] or None
    history     = get_shifts_history(chatter["id"])
    return render_template(
        "chatter/shift.html",
        chatter=chatter,
        shift_start=shift_start, shift_end=shift_end,
        history=history,
    )


# ── Ma rémunération ───────────────────────────────────────────────────────────

@chatter_bp.route("/remuneration")
@chatter_required
def my_remuneration():
    chatter = _current_chatter()
    today   = date.today()
    month   = int(request.args.get("month", today.month))
    year    = int(request.args.get("year",  today.year))

    stats    = get_chatter_month_stats(chatter["id"], month, year)
    bonuses  = get_month_bonuses(chatter["id"], month, year)
    penalties = get_month_penalties(chatter["id"], month, year)
    avail    = get_available_months()

    return render_template(
        "chatter/remuneration.html",
        chatter=chatter, stats=stats,
        bonuses=bonuses, penalties=penalties,
        month=month, year=year, month_name=MONTHS_FR[month],
        available_months=avail, months_fr=MONTHS_FR,
    )


# ── Mes fiches de paie ────────────────────────────────────────────────────────

@chatter_bp.route("/payslips")
@chatter_required
def my_payslips():
    chatter  = _current_chatter()
    payrolls = get_chatter_payrolls(chatter["id"])
    return render_template(
        "chatter/payslips.html",
        chatter=chatter, payrolls=payrolls,
        months_fr=MONTHS_FR,
    )


@chatter_bp.route("/payslips/<int:year>/<int:month>")
@chatter_required
def my_payslip_detail(year, month):
    chatter = _current_chatter()
    pr = get_payroll_row(chatter["id"], month, year)
    if not pr or not pr.get("validated"):
        abort(404)
    data = compute_payroll(chatter["id"], month, year)
    return render_template(
        "chatter/payslip_detail.html",
        chatter=chatter, data=data,
        month=month, year=year, month_name=MONTHS_FR[month],
    )


# ── Mes modèles ───────────────────────────────────────────────────────────────

@chatter_bp.route("/models")
@chatter_required
def my_models():
    chatter = _current_chatter()
    models  = get_chatter_models(chatter["id"])
    return render_template(
        "chatter/models.html",
        chatter=chatter,
        models=models,
    )
