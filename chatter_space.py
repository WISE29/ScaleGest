"""
chatter_space.py — Espace personnel du chatter — V2
Routes préfixées /chatter/
"""

from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user

from utils.auth_helpers import chatter_required
from database import run_sql
from models import (
    MONTHS_FR,
    get_chatter, get_chatter_month_stats, get_chatter_rank,
    get_recent_sales, get_month_bonuses, get_month_penalties,
    get_available_months, get_chatter_payrolls,
    get_month_ca_chatters, get_month_ca_manager,
    get_shifts_history, get_payroll_row,
    get_chatter_models, get_objective, get_ranking,
    get_chatter_objective, upsert_chatter_objective, get_all_chatter_objectives,
)
from utils.payroll import compute_payroll
from utils.calculations import objective_stats

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

    # Stats personnelles du mois
    stats = get_chatter_month_stats(chatter["id"], month, year)
    rank  = get_chatter_rank(chatter["id"], month, year)

    # Dernière fiche de paie validée
    payrolls     = get_chatter_payrolls(chatter["id"])
    last_payroll = payrolls[0] if payrolls else None

    # Shift permanent formaté
    shift_start = str(chatter.get("shift_start") or "")[:5] or None
    shift_end   = str(chatter.get("shift_end")   or "")[:5] or None

    # ── Données globales équipe (visibles par le chatter) ──────────────────
    # CA de l'équipe du jour
    row_today = run_sql(
        "SELECT COALESCE(SUM(amount),0) AS t FROM daily_sales WHERE date=%s",
        (today.isoformat(),), fetch="one"
    )
    ca_equipe_today = float(row_today["t"]) if row_today else 0.0

    # CA personnel du chatter aujourd'hui
    row_perso = run_sql(
        "SELECT COALESCE(amount,0) AS a FROM daily_sales WHERE chatter_id=%s AND date=%s",
        (chatter["id"], today.isoformat()), fetch="one"
    )
    ca_today_perso = float(row_perso["a"]) if row_perso else 0.0

    # CA équipe du mois
    ca_equipe_mois  = get_month_ca_chatters(month, year)
    ca_manager_mois = get_month_ca_manager(month, year)
    ca_total_mois   = ca_equipe_mois + ca_manager_mois

    # Objectif mensuel de l'équipe
    objectif = get_objective(month, year)
    obj_stats = objective_stats(objectif, ca_total_mois, month, year) if objectif > 0 else None

    # Classement top 5 du mois (noms uniquement, pas de salaires)
    top5 = get_ranking(month, year)[:5]

    # Moyenne CA journalière équipe (depuis le début du mois)
    rows_avg = run_sql(
        """SELECT COALESCE(AVG(daily_total),0) AS avg_ca
           FROM (
               SELECT date, SUM(amount) AS daily_total
               FROM daily_sales
               WHERE EXTRACT(MONTH FROM date)=%s AND EXTRACT(YEAR FROM date)=%s
               GROUP BY date
           ) sub""",
        (month, year), fetch="one"
    )
    avg_journaliere = float(rows_avg["avg_ca"]) if rows_avg else 0.0

    return render_template(
        "chatter/dashboard.html",
        chatter=chatter, stats=stats, rank=rank,
        month=month, year=year, month_name=MONTHS_FR[month],
        shift_start=shift_start, shift_end=shift_end,
        last_payroll=last_payroll,
        # Données équipe
        ca_equipe_today=ca_equipe_today,
        ca_today_perso=ca_today_perso,
        ca_equipe_mois=ca_equipe_mois,
        ca_total_mois=ca_total_mois,
        objectif=objectif,
        obj_stats=obj_stats,
        avg_journaliere=avg_journaliere,
        top5=top5,
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


# ── Mes objectifs personnels ──────────────────────────────────────────────────

@chatter_bp.route("/objectives", methods=["GET", "POST"])
@chatter_required
def my_objectives():
    chatter = _current_chatter()
    today   = date.today()

    if request.method == "POST":
        month_val  = int(request.form.get("month", today.month))
        year_val   = int(request.form.get("year",  today.year))
        amount_str = request.form.get("amount", "0").replace(",", ".")
        try:
            amount = float(amount_str)
        except ValueError:
            amount = 0.0
        if amount > 0:
            upsert_chatter_objective(chatter["id"], month_val, year_val, amount)
        flash(f"Objectif de {MONTHS_FR[month_val]} {year_val} mis à jour.", "success")
        return redirect(url_for("chatter_space.my_objectives"))

    # Mois sélectionné
    month = int(request.args.get("month", today.month))
    year  = int(request.args.get("year",  today.year))

    # Objectif perso du mois sélectionné
    objectif_perso = get_chatter_objective(chatter["id"], month, year)

    # Stats CA du chatter pour ce mois
    stats = get_chatter_month_stats(chatter["id"], month, year)

    # Progression vers objectif perso
    obj_stats_perso = objective_stats(objectif_perso, stats["ca"], month, year) \
                      if objectif_perso > 0 else None

    # Historique de tous ses objectifs
    historique = get_all_chatter_objectives(chatter["id"])

    avail = get_available_months()

    return render_template(
        "chatter/objectives.html",
        chatter=chatter,
        month=month, year=year, month_name=MONTHS_FR[month],
        objectif_perso=objectif_perso,
        stats=stats,
        obj_stats_perso=obj_stats_perso,
        historique=historique,
        available_months=avail,
        months_fr=MONTHS_FR,
        today=today,
    )
