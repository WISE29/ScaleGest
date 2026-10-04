"""
recruiter_space.py — Espace recruteur — Scale Gest V2
Routes préfixées /recruiter/
Le recruteur voit uniquement les chatters qui lui sont affiliés.
Il perçoit 1 % du CA de ses chatters.
"""

from datetime import date
from flask import Blueprint, render_template, request, abort
from flask_login import current_user

from utils.auth_helpers import chatter_required  # on crée recruiter_required ci-dessous
from database import run_sql
from models import (
    MONTHS_FR,
    get_chatter, get_chatter_month_stats, get_chatter_rank,
    get_month_bonuses, get_month_penalties,
    get_available_months, get_chatter_payrolls, get_payroll_row,
    get_recruiter_chatters, get_recruiter_commission,
)
from utils.payroll import compute_payroll
from utils.calculations import objective_stats

recruiter_bp = Blueprint("recruiter_space", __name__, url_prefix="/recruiter")


# ── Décorateur recruiter_required ────────────────────────────────────────────

from functools import wraps
from flask import redirect, url_for, flash


def recruiter_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Connexion requise.", "warning")
            return redirect(url_for("auth.login"))
        if current_user.role != "recruiter":
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ─────────────────────────────────────────────────────────────────

@recruiter_bp.route("/")
@recruiter_required
def dashboard():
    today = date.today()
    month, year = today.month, today.year
    recruiter_id = current_user.id

    commission_data = get_recruiter_commission(recruiter_id, month, year)

    # CA équipe du jour (chatters affiliés seulement)
    chatters = get_recruiter_chatters(recruiter_id)
    ca_today = 0.0
    for c in chatters:
        row = run_sql(
            "SELECT COALESCE(amount,0) AS a FROM daily_sales WHERE chatter_id=%s AND date=%s",
            (c["id"], today.isoformat()), fetch="one"
        )
        ca_today += float(row["a"]) if row else 0.0

    return render_template(
        "recruiter/dashboard.html",
        commission_data=commission_data,
        ca_today=ca_today,
        month=month, year=year, month_name=MONTHS_FR[month],
        months_fr=MONTHS_FR,
    )


# ── Mes chatters ──────────────────────────────────────────────────────────────

@recruiter_bp.route("/chatters")
@recruiter_required
def my_chatters():
    today = date.today()
    month, year = today.month, today.year
    chatters = get_recruiter_chatters(current_user.id)
    stats = {c["id"]: get_chatter_month_stats(c["id"], month, year) for c in chatters}
    return render_template(
        "recruiter/chatters.html",
        chatters=chatters, stats=stats,
        month=month, year=year, month_name=MONTHS_FR[month],
        months_fr=MONTHS_FR,
    )


# ── Fiche d'un chatter affilié ───────────────────────────────────────────────

@recruiter_bp.route("/chatters/<int:chatter_id>")
@recruiter_required
def chatter_detail(chatter_id):
    # Vérification : ce chatter est bien affilié à CE recruteur
    chatter = get_chatter(chatter_id)
    if not chatter or chatter.get("recruiter_id") != current_user.id:
        abort(403)

    today = date.today()
    month = int(request.args.get("month", today.month))
    year  = int(request.args.get("year",  today.year))

    stats    = get_chatter_month_stats(chatter_id, month, year)
    rank     = get_chatter_rank(chatter_id, month, year)
    bonuses  = get_month_bonuses(chatter_id, month, year)
    penalties = get_month_penalties(chatter_id, month, year)
    payrolls = get_chatter_payrolls(chatter_id)
    avail    = get_available_months()

    # CA du jour
    row = run_sql(
        "SELECT COALESCE(amount,0) AS a FROM daily_sales WHERE chatter_id=%s AND date=%s",
        (chatter_id, today.isoformat()), fetch="one"
    )
    ca_today = float(row["a"]) if row else 0.0

    return render_template(
        "recruiter/chatter_detail.html",
        chatter=chatter, stats=stats, rank=rank,
        bonuses=bonuses, penalties=penalties,
        payrolls=payrolls, ca_today=ca_today,
        month=month, year=year, month_name=MONTHS_FR[month],
        available_months=avail, months_fr=MONTHS_FR,
    )


# ── Ma commission ─────────────────────────────────────────────────────────────

@recruiter_bp.route("/commission")
@recruiter_required
def my_commission():
    today = date.today()
    month = int(request.args.get("month", today.month))
    year  = int(request.args.get("year",  today.year))

    commission_data = get_recruiter_commission(current_user.id, month, year)
    avail = get_available_months()

    return render_template(
        "recruiter/commission.html",
        commission_data=commission_data,
        month=month, year=year, month_name=MONTHS_FR[month],
        available_months=avail, months_fr=MONTHS_FR,
    )
