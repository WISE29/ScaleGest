"""
app.py — Chatter Manager V2
Factory pattern : create_app() initialise Flask, les blueprints, Flask-Login.
"""

import os
import csv
import hashlib
from datetime import date, datetime, timedelta
from io import StringIO

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, abort, Response, Blueprint
)
from flask_login import LoginManager, login_required
from dotenv import load_dotenv

load_dotenv()

from database import get_db, close_db, init_db, run_sql, commit
from auth import auth_bp, load_user_by_id
from chatter_space import chatter_bp
from recruiter_space import recruiter_bp
from models import (
    MONTHS_FR, log_action,
    get_all_chatters, get_chatter, create_chatter, update_chatter,
    update_chatter_shift, toggle_chatter_status, delete_chatter,
    get_shifts_history, get_shifts_overview,
    get_month_ca_chatters, get_month_ca_manager, get_chatter_month_stats,
    get_daily_sales_for_date, get_manager_ca_for_date,
    upsert_daily_sale, upsert_manager_sale,
    get_recent_sales, get_available_months,
    get_ranking,
    add_bonus, delete_bonus, add_penalty, delete_penalty,
    get_month_bonuses, get_month_penalties,
    upsert_objective, get_objective, get_all_objectives,
    get_payroll_row, is_month_locked, validate_month, unlock_month,
    get_all_users, create_user, update_user_password, toggle_user_active,
    get_all_models, get_model, create_model, update_model, toggle_model_status,
    get_chatter_models, get_model_chatters,
    assign_model, remove_model, get_unassigned_models,
    get_all_recruiters, get_recruiter, get_recruiter_chatters,
    affiliate_chatter, get_recruiter_commission,
)
from utils.calculations import manager_total_remuneration, objective_stats
from utils.payroll import compute_payroll, save_payroll
from utils.pdf import generate_payslip_pdf
from utils.auth_helpers import manager_required

BASE_DIR    = os.path.dirname(__file__)
PAYROLL_DIR = os.path.join(BASE_DIR, "exports", "payrolls")
os.makedirs(PAYROLL_DIR, exist_ok=True)

# ─── Blueprint Manager déclaré au niveau module ───────────────────────────────
# Doit être créé AVANT create_app() pour pouvoir y être enregistré.

manager_bp = Blueprint("manager", __name__, url_prefix="/manager")


# ─── Factory ─────────────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    # ── Cache-busting ──────────────────────────────────────────────
    try:
        _css = os.path.join(BASE_DIR, "static", "css", "style.css")
        _js  = os.path.join(BASE_DIR, "static", "js",  "main.js")
        _src = str(os.path.getmtime(_css)) + str(os.path.getmtime(_js))
        app.config["ASSET_VERSION"] = hashlib.md5(_src.encode()).hexdigest()[:8]
    except Exception:
        app.config["ASSET_VERSION"] = "1"

    # ── DB lifecycle ───────────────────────────────────────────────
    app.teardown_appcontext(close_db)

    @app.after_request
    def no_cache_static(response):
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    # ── Flask-Login ────────────────────────────────────────────────
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Connexion requise."
    login_manager.login_message_category = "warning"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        with app.app_context():
            return load_user_by_id(int(user_id))

    # ── Context processors ─────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        return {
            "asset_version": app.config["ASSET_VERSION"],
            "months_fr":     MONTHS_FR,
            "today":         date.today(),
        }

    @app.template_filter("abs")
    def f_abs(v): return abs(v)

    @app.template_filter("min")
    def f_min(it): return min(it)

    @app.template_filter("short")
    def f_short(v, n=5):
        """Convertit en str et coupe à n caractères — remplace str(v)[:n] dans Jinja."""
        return str(v)[:n] if v is not None else ""

    @app.template_filter("money")
    def f_money(v):
        """
        Rend un montant sous forme HTML avec data-amount pour la conversion de devise JS.
        Usage dans les templates : {{ montant|money }}
        """
        from markupsafe import Markup
        try:
            val = float(v)
        except (TypeError, ValueError):
            val = 0.0
        return Markup(
            f'<span class="money" data-amount="{val:.2f}">{val:,.2f} €</span>'
        )

    @app.template_filter("date_prev")
    def f_date_prev(d):
        from datetime import date, timedelta
        try:
            return (date.fromisoformat(str(d)) - timedelta(days=1)).isoformat()
        except Exception:
            return d

    @app.template_filter("date_next")
    def f_date_next(d):
        from datetime import date, timedelta
        try:
            return (date.fromisoformat(str(d)) + timedelta(days=1)).isoformat()
        except Exception:
            return d

    # ── Blueprints ─────────────────────────────────────────────────
    app.register_blueprint(auth_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(chatter_bp)
    app.register_blueprint(recruiter_bp)

    # ── Erreurs ────────────────────────────────────────────────────
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    # ── Init DB au démarrage ───────────────────────────────────────
    with app.app_context():
        init_db(app)

    return app


# ─── Routes manager ──────────────────────────────────────────────────────────

# ── Dashboard ────────────────────────────────────────────────────────────────

@manager_bp.route("/")
@manager_required
def dashboard():
    today = date.today()
    month, year = today.month, today.year

    ca_chatters = get_month_ca_chatters(month, year)
    ca_manager  = get_month_ca_manager(month, year)
    ca_total    = ca_chatters + ca_manager

    row_today = run_sql(
        "SELECT COALESCE(SUM(amount),0) AS t FROM daily_sales WHERE date=%s",
        (today.isoformat(),), fetch="one"
    )
    ca_today_chatters = float(row_today["t"]) if row_today else 0.0
    ca_today_manager  = get_manager_ca_for_date(today.isoformat())
    ca_today          = ca_today_chatters + ca_today_manager

    yesterday = (today - timedelta(days=1)).isoformat()
    row_yest  = run_sql(
        "SELECT COALESCE(SUM(amount),0) AS t FROM daily_sales WHERE date=%s",
        (yesterday,), fetch="one"
    )
    ca_yesterday  = float(row_yest["t"]) if row_yest else 0.0
    ca_evolution  = round(ca_today_chatters - ca_yesterday, 2)

    objective = get_objective(month, year)
    obj_stats = objective_stats(objective, ca_total, month, year) if objective > 0 else None
    mgr_rem   = manager_total_remuneration(ca_chatters, ca_manager)

    active_chatters = get_all_chatters(status="active")
    payroll_mass = sum(
        get_chatter_month_stats(c["id"], month, year)["final_salary"]
        for c in active_chatters
    )

    top5          = get_ranking(month, year)[:5]
    shifts_view   = get_shifts_overview()

    return render_template(
        "manager/dashboard.html",
        month=month, year=year, month_name=MONTHS_FR[month],
        ca_today=ca_today, ca_today_chatters=ca_today_chatters,
        ca_today_manager=ca_today_manager, ca_evolution=ca_evolution,
        ca_chatters=ca_chatters, ca_manager=ca_manager, ca_total=ca_total,
        objective=objective, obj_stats=obj_stats,
        mgr_rem=mgr_rem, payroll_mass=payroll_mass,
        active_count=len(active_chatters),
        top5=top5, shifts_view=shifts_view,
    )


# ── Chatters ─────────────────────────────────────────────────────────────────

@manager_bp.route("/chatters")
@manager_required
def chatters_list():
    chatters = get_all_chatters()
    today    = date.today()
    stats    = {c["id"]: get_chatter_month_stats(c["id"], today.month, today.year)
                for c in chatters}
    return render_template("manager/chatters.html",
                           chatters=chatters, stats=stats,
                           month_name=MONTHS_FR[today.month], year=today.year)


@manager_bp.route("/chatters/add", methods=["GET", "POST"])
@manager_required
def chatter_add():
    if request.method == "POST":
        name        = request.form["name"].strip()
        status      = request.form.get("status", "active")
        date_joined = request.form.get("date_joined") or date.today().isoformat()
        notes       = request.form.get("notes", "").strip()
        shift_start = request.form.get("shift_start", "").strip()
        shift_end   = request.form.get("shift_end", "").strip()

        if not name:
            flash("Le nom est obligatoire.", "error")
            return redirect(url_for("manager.chatter_add"))

        chatter_id = create_chatter(name, status, date_joined, notes,
                                    shift_start or None, shift_end or None)
        log_action("ADD_CHATTER", f"Chatter ajouté : {name}")
        flash(f"Chatter « {name} » ajouté.", "success")
        return redirect(url_for("manager.chatters_list"))
    return render_template("manager/chatter_form.html", chatter=None, action="Ajouter")


@manager_bp.route("/chatters/<int:chatter_id>")
@manager_required
def chatter_detail(chatter_id):
    chatter = get_chatter(chatter_id)
    if not chatter:
        abort(404)
    today = date.today()
    month, year = today.month, today.year
    stats        = get_chatter_month_stats(chatter_id, month, year)
    bonuses      = get_month_bonuses(chatter_id, month, year)
    penalties    = get_month_penalties(chatter_id, month, year)
    recent_sales = get_recent_sales(chatter_id)
    shift_hist   = get_shifts_history(chatter_id)

    week_start = today - timedelta(days=today.weekday())
    row_w = run_sql(
        "SELECT COALESCE(SUM(amount),0) AS t FROM daily_sales WHERE chatter_id=%s AND date>=%s AND date<=%s",
        (chatter_id, week_start.isoformat(), today.isoformat()), fetch="one"
    )
    ca_week = float(row_w["t"]) if row_w else 0.0
    row_d   = run_sql(
        "SELECT COALESCE(amount,0) AS a FROM daily_sales WHERE chatter_id=%s AND date=%s",
        (chatter_id, today.isoformat()), fetch="one"
    )
    ca_today = float(row_d["a"]) if row_d else 0.0

    # Compte utilisateur lié
    user_row = run_sql(
        "SELECT id, username, active FROM users WHERE chatter_id=%s",
        (chatter_id,), fetch="one"
    )
    # Modèles attribués
    assigned_models   = get_chatter_models(chatter_id)
    available_models  = get_unassigned_models(chatter_id)

    return render_template(
        "manager/chatter.html",
        chatter=chatter, stats=stats,
        ca_today=ca_today, ca_week=ca_week,
        bonuses=bonuses, penalties=penalties,
        recent_sales=recent_sales, shift_hist=shift_hist,
        month_name=MONTHS_FR[month], year=year,
        user_row=user_row,
        assigned_models=assigned_models,
        available_models=available_models,
    )


@manager_bp.route("/chatters/<int:chatter_id>/edit", methods=["GET", "POST"])
@manager_required
def chatter_edit(chatter_id):
    chatter = get_chatter(chatter_id)
    if not chatter:
        abort(404)
    if request.method == "POST":
        update_chatter(
            chatter_id,
            request.form["name"].strip(),
            request.form.get("status", "active"),
            request.form.get("date_joined"),
            request.form.get("notes", "").strip(),
        )
        log_action("EDIT_CHATTER", f"Chatter modifié id={chatter_id}")
        flash("Chatter mis à jour.", "success")
        return redirect(url_for("manager.chatter_detail", chatter_id=chatter_id))
    return render_template("manager/chatter_form.html", chatter=chatter, action="Modifier")


@manager_bp.route("/chatters/<int:chatter_id>/shift", methods=["POST"])
@manager_required
def chatter_shift_update(chatter_id):
    new_start = request.form.get("shift_start", "").strip()
    new_end   = request.form.get("shift_end", "").strip()
    if not new_start or not new_end:
        flash("Heure de début et de fin requises.", "error")
    else:
        update_chatter_shift(chatter_id, new_start, new_end)
        log_action("UPDATE_SHIFT",
                   f"Shift mis à jour : chatter {chatter_id} → {new_start}–{new_end}")
        flash("Shift mis à jour.", "success")
    return redirect(url_for("manager.chatter_detail", chatter_id=chatter_id))


@manager_bp.route("/chatters/<int:chatter_id>/toggle", methods=["POST"])
@manager_required
def chatter_toggle(chatter_id):
    new_status = toggle_chatter_status(chatter_id)
    c = get_chatter(chatter_id)
    log_action("TOGGLE_CHATTER", f"{c['name']} → {new_status}")
    flash(f"Statut mis à jour : {new_status}.", "success")
    return redirect(url_for("manager.chatters_list"))


@manager_bp.route("/chatters/<int:chatter_id>/delete", methods=["POST"])
@manager_required
def chatter_delete(chatter_id):
    c = get_chatter(chatter_id)
    if c:
        delete_chatter(chatter_id)
        log_action("DELETE_CHATTER", f"Chatter supprimé : {c['name']}")
        flash(f"Chatter « {c['name']} » supprimé.", "success")
    return redirect(url_for("manager.chatters_list"))


# ── Shifts (vue permanente) ───────────────────────────────────────────────────

@manager_bp.route("/shifts")
@manager_required
def shifts():
    view     = get_shifts_overview()
    chatters = get_all_chatters(status="active")
    return render_template("manager/shifts.html",
                           view=view, chatters=chatters)


# ── CA ────────────────────────────────────────────────────────────────────────

@manager_bp.route("/sales")
@manager_required
def sales():
    sel_date  = request.args.get("date", date.today().isoformat())
    chatters  = get_all_chatters(status="active")
    sales_map = get_daily_sales_for_date(sel_date)
    mgr_ca    = get_manager_ca_for_date(sel_date)
    return render_template("manager/sales.html",
                           chatters=chatters, sales_map=sales_map,
                           manager_ca=mgr_ca, sel_date=sel_date)


@manager_bp.route("/sales/save", methods=["POST"])
@manager_required
def sales_save():
    sel_date = request.form.get("date", date.today().isoformat())
    chatters = get_all_chatters(status="active")

    for c in chatters:
        val = request.form.get(f"ca_{c['id']}", "0").replace(",", ".").strip()
        try:
            amount = float(val)
        except ValueError:
            amount = 0.0

        old_row = run_sql(
            "SELECT amount FROM daily_sales WHERE chatter_id=%s AND date=%s",
            (c["id"], sel_date), fetch="one"
        )
        upsert_daily_sale(c["id"], sel_date, amount)
        if old_row and abs(float(old_row["amount"]) - amount) > 0.001:
            log_action("EDIT_CA",
                       f"CA {c['name']} le {sel_date} : {old_row['amount']}€ → {amount}€")

    mgr_val = request.form.get("ca_manager", "0").replace(",", ".").strip()
    try:
        mgr_amount = float(mgr_val)
    except ValueError:
        mgr_amount = 0.0
    upsert_manager_sale(sel_date, mgr_amount)
    commit()
    flash(f"CA du {sel_date} enregistré.", "success")
    return redirect(url_for("manager.sales", date=sel_date))


# ── Classement ────────────────────────────────────────────────────────────────

@manager_bp.route("/ranking")
@manager_required
def ranking():
    today = date.today()
    month = int(request.args.get("month", today.month))
    year  = int(request.args.get("year",  today.year))
    sort  = request.args.get("sort", "ca")
    data  = get_ranking(month, year, sort)
    return render_template("manager/ranking.html",
                           data=data, month=month, year=year,
                           month_name=MONTHS_FR[month], sort=sort,
                           available_months=get_available_months())


# ── Primes & Malus ────────────────────────────────────────────────────────────

@manager_bp.route("/bonuses/add", methods=["POST"])
@manager_required
def bonus_add():
    chatter_id  = int(request.form["chatter_id"])
    redirect_to = request.form.get("redirect", url_for("manager.chatters_list"))
    amount_s    = request.form.get("amount", "0").replace(",", ".")
    reason      = request.form.get("reason", "").strip()
    if not reason:
        flash("Le motif est obligatoire.", "error")
        return redirect(redirect_to)
    try:
        amount = float(amount_s)
    except ValueError:
        amount = 0.0
    add_bonus(chatter_id, request.form.get("date", date.today().isoformat()),
              amount, reason, request.form.get("comment", ""))
    log_action("ADD_BONUS", f"Prime {amount}€ chatter {chatter_id} — {reason}")
    flash(f"Prime de {amount:.2f} € ajoutée.", "success")
    return redirect(redirect_to)


@manager_bp.route("/bonuses/<int:bonus_id>/delete", methods=["POST"])
@manager_required
def bonus_delete(bonus_id):
    redirect_to = request.form.get("redirect", url_for("manager.chatters_list"))
    delete_bonus(bonus_id)
    flash("Prime supprimée.", "success")
    return redirect(redirect_to)


@manager_bp.route("/penalties/add", methods=["POST"])
@manager_required
def penalty_add():
    chatter_id  = int(request.form["chatter_id"])
    redirect_to = request.form.get("redirect", url_for("manager.chatters_list"))
    amount_s    = request.form.get("amount", "0").replace(",", ".")
    reason      = request.form.get("reason", "").strip()
    if not reason:
        flash("Le motif est obligatoire.", "error")
        return redirect(redirect_to)
    try:
        amount = float(amount_s)
    except ValueError:
        amount = 0.0
    add_penalty(chatter_id, request.form.get("date", date.today().isoformat()),
                amount, reason, request.form.get("comment", ""))
    log_action("ADD_PENALTY", f"Malus {amount}€ chatter {chatter_id} — {reason}")
    flash(f"Malus de {amount:.2f} € ajouté.", "success")
    return redirect(redirect_to)


@manager_bp.route("/penalties/<int:penalty_id>/delete", methods=["POST"])
@manager_required
def penalty_delete(penalty_id):
    redirect_to = request.form.get("redirect", url_for("manager.chatters_list"))
    delete_penalty(penalty_id)
    flash("Malus supprimé.", "success")
    return redirect(redirect_to)


# ── Objectifs ─────────────────────────────────────────────────────────────────

@manager_bp.route("/objectives", methods=["GET", "POST"])
@manager_required
def objectives():
    if request.method == "POST":
        month  = int(request.form["month"])
        year   = int(request.form["year"])
        amount_s = request.form.get("amount", "0").replace(",", ".")
        try:
            amount = float(amount_s)
        except ValueError:
            amount = 0.0
        upsert_objective(month, year, amount)
        log_action("SET_OBJECTIVE", f"Objectif {MONTHS_FR[month]} {year} : {amount}€")
        flash(f"Objectif {MONTHS_FR[month]} {year} : {amount:.2f} €", "success")
        return redirect(url_for("manager.objectives"))
    today = date.today()
    return render_template("manager/objectives.html",
                           objectives_list=get_all_objectives(),
                           current_month=today.month, current_year=today.year)


# ── Paies ─────────────────────────────────────────────────────────────────────

@manager_bp.route("/payroll")
@manager_required
def payroll_list():
    return render_template("manager/payroll.html",
                           available_months=get_available_months())


@manager_bp.route("/payroll/<int:year>/<int:month>")
@manager_required
def payroll_detail(year, month):
    chatters   = get_all_chatters()
    is_locked  = is_month_locked(month, year)
    payrolls   = []
    total_mass = 0.0

    for c in chatters:
        data = compute_payroll(c["id"], month, year)
        if data["ca_net"] > 0 or data["total_bonuses"] > 0 or data["total_penalties"] > 0:
            pr = get_payroll_row(c["id"], month, year)
            data["validated"]    = bool(pr["validated"]) if pr else False
            data["chatter_name"] = c["name"]
            payrolls.append(data)
            total_mass += data["final_amount"]

    ca_chatters = get_month_ca_chatters(month, year)
    ca_manager  = get_month_ca_manager(month, year)
    mgr_rem     = manager_total_remuneration(ca_chatters, ca_manager)

    return render_template("manager/payroll_detail.html",
                           payrolls=payrolls, month=month, year=year,
                           month_name=MONTHS_FR[month],
                           is_locked=is_locked, total_mass=total_mass,
                           mgr_rem=mgr_rem)


@manager_bp.route("/payroll/<int:year>/<int:month>/generate", methods=["POST"])
@manager_required
def payroll_generate(year, month):
    for c in get_all_chatters():
        data = compute_payroll(c["id"], month, year)
        if data["ca_net"] > 0 or data["total_bonuses"] > 0 or data["total_penalties"] > 0:
            save_payroll(data)
    commit()
    log_action("GENERATE_PAYROLL", f"Paies {MONTHS_FR[month]} {year}")
    flash(f"Paies {MONTHS_FR[month]} {year} générées.", "success")
    return redirect(url_for("manager.payroll_detail", year=year, month=month))


@manager_bp.route("/payroll/<int:year>/<int:month>/validate", methods=["POST"])
@manager_required
def payroll_validate(year, month):
    validate_month(month, year)
    log_action("VALIDATE_PAYROLL", f"Paies validées — {MONTHS_FR[month]} {year}")
    flash(f"Paies {MONTHS_FR[month]} {year} verrouillées. 🔒", "success")
    return redirect(url_for("manager.payroll_detail", year=year, month=month))


@manager_bp.route("/payroll/<int:year>/<int:month>/unlock", methods=["POST"])
@manager_required
def payroll_unlock(year, month):
    unlock_month(month, year)
    log_action("UNLOCK_PAYROLL", f"Paies déverrouillées — {MONTHS_FR[month]} {year}")
    flash(f"Paies {MONTHS_FR[month]} {year} déverrouillées.", "info")
    return redirect(url_for("manager.payroll_detail", year=year, month=month))


@manager_bp.route("/payroll/<int:year>/<int:month>/pdf/<int:chatter_id>")
@manager_required
def payroll_pdf(year, month, chatter_id):
    c = get_chatter(chatter_id)
    if not c:
        abort(404)
    data     = compute_payroll(chatter_id, month, year)
    filepath = generate_payslip_pdf(data, c["name"], PAYROLL_DIR)
    return send_file(filepath, as_attachment=True)


@manager_bp.route("/payroll/<int:year>/<int:month>/pdf/all")
@manager_required
def payroll_pdf_all(year, month):
    import zipfile
    from io import BytesIO
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in get_all_chatters():
            data = compute_payroll(c["id"], month, year)
            if data["ca_net"] > 0:
                fp = generate_payslip_pdf(data, c["name"], PAYROLL_DIR)
                zf.write(fp, os.path.basename(fp))
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f"paies_{MONTHS_FR[month]}_{year}.zip",
                     mimetype="application/zip")


# ── Historique ────────────────────────────────────────────────────────────────

@manager_bp.route("/history")
@manager_required
def history():
    today = date.today()
    month = int(request.args.get("month", today.month))
    year  = int(request.args.get("year",  today.year))

    chatters_data = []
    for c in get_all_chatters():
        s = get_chatter_month_stats(c["id"], month, year)
        if s["ca"] > 0 or s["days"] > 0:
            chatters_data.append({"chatter": c, **s})
    chatters_data.sort(key=lambda x: x["ca"], reverse=True)

    ca_chatters = get_month_ca_chatters(month, year)
    ca_manager  = get_month_ca_manager(month, year)
    mgr_rem     = manager_total_remuneration(ca_chatters, ca_manager)
    objective   = get_objective(month, year)

    logs = run_sql(
        "SELECT * FROM audit_log WHERE timestamp LIKE %s ORDER BY timestamp DESC LIMIT 100",
        (f"{year}-{month:02d}%",), fetch="all"
    ) or []

    return render_template("manager/history.html",
                           month=month, year=year, month_name=MONTHS_FR[month],
                           chatters_data=chatters_data,
                           ca_chatters=ca_chatters, ca_manager=ca_manager,
                           mgr_rem=mgr_rem, objective=objective, logs=logs,
                           available_months=get_available_months())


# ── Export CSV ────────────────────────────────────────────────────────────────

@manager_bp.route("/export/csv/<int:year>/<int:month>")
@manager_required
def export_csv(year, month):
    output = StringIO()
    w = csv.writer(output, delimiter=";")
    w.writerow(["Chatter","CA (€)","Jours","Moyenne/jour (€)",
                "Commission (€)","Primes (€)","Malus (€)","Rémunération (€)"])
    for c in get_all_chatters():
        s = get_chatter_month_stats(c["id"], month, year)
        w.writerow([c["name"], s["ca"], s["days"], s["avg"],
                    s["base_commission"], s["total_bonuses"],
                    s["total_penalties"], s["final_salary"]])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f"attachment; filename=export_{MONTHS_FR[month]}_{year}.csv"}
    )


# ── Gestion des comptes utilisateurs ─────────────────────────────────────────

@manager_bp.route("/users")
@manager_required
def users_list():
    return render_template("manager/users.html", users=get_all_users(),
                           chatters=get_all_chatters())


@manager_bp.route("/users/add", methods=["POST"])
@manager_required
def user_add():
    username   = request.form.get("username", "").strip()
    password   = request.form.get("password", "").strip()
    role       = request.form.get("role", "chatter")
    chatter_id = request.form.get("chatter_id") or None
    if not username or not password:
        flash("Identifiant et mot de passe requis.", "error")
        return redirect(url_for("manager.users_list"))
    try:
        create_user(username, password, role,
                    int(chatter_id) if chatter_id else None)
        log_action("ADD_USER", f"Compte créé : {username} ({role})")
        flash(f"Compte « {username} » créé.", "success")
    except Exception:
        flash("Cet identifiant est déjà utilisé.", "error")
    return redirect(url_for("manager.users_list"))


@manager_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@manager_required
def user_reset_password(user_id):
    new_pwd = request.form.get("password", "").strip()
    if not new_pwd:
        flash("Mot de passe vide.", "error")
    else:
        update_user_password(user_id, new_pwd)
        log_action("RESET_PASSWORD", f"Mot de passe réinitialisé user {user_id}")
        flash("Mot de passe réinitialisé.", "success")
    return redirect(url_for("manager.users_list"))


@manager_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@manager_required
def user_toggle(user_id):
    active = toggle_user_active(user_id)
    flash("Compte " + ("activé" if active else "désactivé") + ".", "success")
    return redirect(url_for("manager.users_list"))


@manager_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@manager_required
def user_delete(user_id):
    """Supprime le compte de connexion uniquement — les données chatter sont conservées."""
    from database import run_sql, commit
    row = run_sql("SELECT username, role FROM users WHERE id=%s", (user_id,), fetch="one")
    if not row:
        flash("Compte introuvable.", "error")
        return redirect(url_for("manager.users_list"))
    if row["role"] == "manager":
        flash("Impossible de supprimer le compte manager.", "error")
        return redirect(url_for("manager.users_list"))
    run_sql("DELETE FROM users WHERE id=%s", (user_id,))
    commit()
    log_action("DELETE_USER", f"Compte supprimé : {row['username']}")
    flash(f"Compte « {row['username']} » supprimé. Les données associées sont conservées.", "success")
    return redirect(url_for("manager.users_list"))


# ── Paramètres ────────────────────────────────────────────────────────────────

@manager_bp.route("/settings")
@manager_required
def settings():
    logs = run_sql(
        "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 50",
        fetch="all"
    ) or []
    return render_template("manager/settings.html", logs=logs)


# ── API JSON pour Chart.js ────────────────────────────────────────────────────

@manager_bp.route("/api/daily_ca/<int:year>/<int:month>")
@manager_required
def api_daily_ca(year, month):
    rows = run_sql(
        """SELECT date::TEXT AS d, SUM(amount) AS ca
           FROM daily_sales
           WHERE EXTRACT(YEAR FROM date)=%s AND EXTRACT(MONTH FROM date)=%s
           GROUP BY date ORDER BY date""",
        (year, month), fetch="all"
    ) or []
    mgr_rows = run_sql(
        """SELECT date::TEXT AS d, amount FROM manager_sales
           WHERE EXTRACT(YEAR FROM date)=%s AND EXTRACT(MONTH FROM date)=%s
           ORDER BY date""",
        (year, month), fetch="all"
    ) or []
    mgr_map = {r["d"]: float(r["amount"]) for r in mgr_rows}
    dates   = [r["d"] for r in rows]
    ca_ch   = [float(r["ca"]) for r in rows]
    ca_tot  = [cc + mgr_map.get(d, 0) for d, cc in zip(dates, ca_ch)]
    return jsonify({"dates": dates, "ca_chatters": ca_ch, "ca_total": ca_tot})


@manager_bp.route("/api/chatter_breakdown/<int:year>/<int:month>")
@manager_required
def api_chatter_breakdown(year, month):
    rows = run_sql(
        """SELECT c.name, COALESCE(SUM(ds.amount),0) AS total
           FROM chatters c
           LEFT JOIN daily_sales ds ON ds.chatter_id=c.id
               AND EXTRACT(YEAR FROM ds.date)=%s
               AND EXTRACT(MONTH FROM ds.date)=%s
           WHERE c.status='active'
           GROUP BY c.id, c.name ORDER BY total DESC""",
        (year, month), fetch="all"
    ) or []
    return jsonify({
        "labels": [r["name"] for r in rows],
        "values": [float(r["total"]) for r in rows],
    })


# ─── Routes Recruteurs ───────────────────────────────────────────────────────

@manager_bp.route("/recruiters")
@manager_required
def recruiters_list():
    today  = date.today()
    month, year = today.month, today.year
    recruiters = get_all_recruiters()
    commissions = {}
    for r in recruiters:
        commissions[r["id"]] = get_recruiter_commission(r["id"], month, year)
    return render_template(
        "manager/recruiters.html",
        recruiters=recruiters, commissions=commissions,
        month_name=MONTHS_FR[month], year=year,
    )


@manager_bp.route("/recruiters/<int:recruiter_id>")
@manager_required
def recruiter_detail(recruiter_id):
    recruiter = get_recruiter(recruiter_id)
    if not recruiter:
        abort(404)
    today = date.today()
    month = int(request.args.get("month", today.month))
    year  = int(request.args.get("year",  today.year))
    commission_data = get_recruiter_commission(recruiter_id, month, year)
    all_active = get_all_chatters(status="active")
    affiliated_ids = {c["chatter"]["id"] for c in commission_data["details"]}
    available = [c for c in all_active if c["id"] not in affiliated_ids]
    return render_template(
        "manager/recruiter_detail.html",
        recruiter=recruiter,
        commission_data=commission_data,
        available=available,
        month=month, year=year, month_name=MONTHS_FR[month],
        available_months=get_available_months(),
        months_fr=MONTHS_FR,
    )


@manager_bp.route("/recruiters/<int:recruiter_id>/affiliate", methods=["POST"])
@manager_required
def recruiter_affiliate(recruiter_id):
    chatter_id = request.form.get("chatter_id")
    if not chatter_id:
        flash("Chatter requis.", "error")
        return redirect(url_for("manager.recruiter_detail", recruiter_id=recruiter_id))
    affiliate_chatter(int(chatter_id), recruiter_id)
    c = get_chatter(int(chatter_id))
    log_action("AFFILIATE", f"Chatter {c['name']} affilié au recruteur {recruiter_id}")
    flash(f"« {c['name']} » affilié.", "success")
    return redirect(url_for("manager.recruiter_detail", recruiter_id=recruiter_id))


@manager_bp.route("/recruiters/<int:recruiter_id>/unaffiliate/<int:chatter_id>", methods=["POST"])
@manager_required
def recruiter_unaffiliate(recruiter_id, chatter_id):
    affiliate_chatter(chatter_id, None)
    flash("Affiliation retirée.", "success")
    return redirect(url_for("manager.recruiter_detail", recruiter_id=recruiter_id))


# ─── Routes Modèles ──────────────────────────────────────────────────────────

@manager_bp.route("/models")
@manager_required
def models_list():
    models = get_all_models()
    # Compte les chatters par modèle
    counts = {}
    for m in models:
        rows = get_model_chatters(m["id"])
        counts[m["id"]] = len(rows)
    return render_template("manager/models.html", models=models, counts=counts)


@manager_bp.route("/models/add", methods=["GET", "POST"])
@manager_required
def model_add():
    if request.method == "POST":
        name  = request.form.get("name", "").strip()
        notes = request.form.get("notes", "").strip()
        if not name:
            flash("Le nom est obligatoire.", "error")
            return redirect(url_for("manager.model_add"))
        create_model(name, notes)
        log_action("ADD_MODEL", f"Modèle créé : {name}")
        flash(f"Modèle « {name} » créé.", "success")
        return redirect(url_for("manager.models_list"))
    return render_template("manager/model_form.html", model=None, action="Ajouter")


@manager_bp.route("/models/<int:model_id>")
@manager_required
def model_detail(model_id):
    model    = get_model(model_id)
    if not model:
        abort(404)
    chatters  = get_model_chatters(model_id)
    all_active = get_all_chatters(status="active")
    # Chatters non encore associés
    assigned_ids = {c["id"] for c in chatters}
    available = [c for c in all_active if c["id"] not in assigned_ids]
    return render_template("manager/model_detail.html",
                           model=model, chatters=chatters, available=available)


@manager_bp.route("/models/<int:model_id>/edit", methods=["GET", "POST"])
@manager_required
def model_edit(model_id):
    model = get_model(model_id)
    if not model:
        abort(404)
    if request.method == "POST":
        name  = request.form.get("name", "").strip()
        notes = request.form.get("notes", "").strip()
        if not name:
            flash("Le nom est obligatoire.", "error")
            return redirect(url_for("manager.model_edit", model_id=model_id))
        update_model(model_id, name, notes)
        log_action("EDIT_MODEL", f"Modèle modifié : {name} (id={model_id})")
        flash(f"Modèle « {name} » mis à jour.", "success")
        return redirect(url_for("manager.model_detail", model_id=model_id))
    return render_template("manager/model_form.html", model=model, action="Modifier")


@manager_bp.route("/models/<int:model_id>/toggle", methods=["POST"])
@manager_required
def model_toggle(model_id):
    new_status = toggle_model_status(model_id)
    m = get_model(model_id)
    log_action("TOGGLE_MODEL", f"{m['name']} → {new_status}")
    flash(f"Modèle « {m['name']} » : {new_status}.", "success")
    return redirect(url_for("manager.models_list"))


@manager_bp.route("/models/<int:model_id>/assign", methods=["POST"])
@manager_required
def model_assign_chatter(model_id):
    chatter_id = request.form.get("chatter_id")
    if not chatter_id:
        flash("Chatter requis.", "error")
        return redirect(url_for("manager.model_detail", model_id=model_id))
    assign_model(int(chatter_id), model_id)
    c = get_chatter(int(chatter_id))
    log_action("ASSIGN_MODEL", f"Modèle {model_id} → chatter {c['name']}")
    flash(f"« {c['name'] if c else chatter_id} » associé au modèle.", "success")
    return redirect(url_for("manager.model_detail", model_id=model_id))


@manager_bp.route("/models/<int:model_id>/remove/<int:chatter_id>", methods=["POST"])
@manager_required
def model_remove_chatter(model_id, chatter_id):
    remove_model(chatter_id, model_id)
    flash("Association retirée.", "success")
    return redirect(url_for("manager.model_detail", model_id=model_id))


# ─── Routes attribution depuis la fiche chatter ───────────────────────────────

@manager_bp.route("/chatters/<int:chatter_id>/models/assign", methods=["POST"])
@manager_required
def chatter_assign_model(chatter_id):
    model_id = request.form.get("model_id")
    if not model_id:
        flash("Modèle requis.", "error")
        return redirect(url_for("manager.chatter_detail", chatter_id=chatter_id))
    assign_model(chatter_id, int(model_id))
    m = get_model(int(model_id))
    log_action("ASSIGN_MODEL", f"Chatter {chatter_id} → modèle {m['name'] if m else model_id}")
    flash(f"Modèle « {m['name'] if m else model_id} » attribué.", "success")
    return redirect(url_for("manager.chatter_detail", chatter_id=chatter_id))


@manager_bp.route("/chatters/<int:chatter_id>/models/remove/<int:model_id>", methods=["POST"])
@manager_required
def chatter_remove_model(chatter_id, model_id):
    remove_model(chatter_id, model_id)
    flash("Modèle retiré.", "success")
    return redirect(url_for("manager.chatter_detail", chatter_id=chatter_id))


# ─── Redirection racine → login ───────────────────────────────────────────────

def _root_redirect():
    from flask_login import current_user
    if current_user.is_authenticated:
        if current_user.role == "manager":
            return redirect(url_for("manager.dashboard"))
        if current_user.role == "recruiter":
            return redirect(url_for("recruiter_space.dashboard"))
        return redirect(url_for("chatter_space.dashboard"))
    return redirect(url_for("auth.login"))


# ─── Point d'entrée ───────────────────────────────────────────────────────────

app = create_app()

# Route racine enregistrée après create_app()
@app.route("/")
def root():
    return _root_redirect()


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "True").lower() == "true"
    app.run(debug=debug, host="127.0.0.1", port=5000)
