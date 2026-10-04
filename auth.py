"""
auth.py — Authentification Flask-Login
Routes : /login, /logout
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from database import run_sql, commit

auth_bp = Blueprint("auth", __name__)


# ─── Modèle User pour Flask-Login ────────────────────────────────────────────

class User:
    """Objet User minimal compatible Flask-Login."""

    def __init__(self, row: dict):
        self.id         = row["id"]
        self.username   = row["username"]
        self.role       = row["role"]
        self.chatter_id = row.get("chatter_id")
        self.active     = bool(row.get("active", True))

    # ── Interface Flask-Login ──────────────────────────────────────
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self.active

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    # ── Helpers ────────────────────────────────────────────────────
    @property
    def is_manager(self):
        return self.role == "manager"

    @property
    def is_chatter(self):
        return self.role == "chatter"


def load_user_by_id(user_id: int):
    """Charge un User depuis la DB (utilisé par login_manager.user_loader)."""
    row = run_sql(
        "SELECT * FROM users WHERE id = %s AND active = %s",
        (user_id, True), fetch="one"
    )
    return User(row) if row else None


def load_user_by_username(username: str):
    row = run_sql(
        "SELECT * FROM users WHERE username = %s",
        (username,), fetch="one"
    )
    return User(row) if row else None


# ─── Routes ──────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_after_login(current_user)

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Identifiant et mot de passe requis.", "error")
            return render_template("auth/login.html")

        row = run_sql(
            "SELECT * FROM users WHERE username = %s",
            (username,), fetch="one"
        )

        if not row or not check_password_hash(row["password_hash"], password):
            flash("Identifiant ou mot de passe incorrect.", "error")
            return render_template("auth/login.html")

        if not row.get("active", True):
            flash("Compte désactivé. Contactez le manager.", "error")
            return render_template("auth/login.html")

        user = User(row)
        login_user(user, remember=False)
        return _redirect_after_login(user)

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for("auth.login"))


def _redirect_after_login(user: User):
    if user.is_manager:
        return redirect(url_for("manager.dashboard"))
    if user.role == "recruiter":
        return redirect(url_for("recruiter_space.dashboard"))
    return redirect(url_for("chatter_space.dashboard"))
