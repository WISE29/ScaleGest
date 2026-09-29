"""
Décorateurs et helpers d'autorisation — V2.
"""

from functools import wraps
from flask import abort, redirect, url_for, flash
from flask_login import current_user


def manager_required(f):
    """Route accessible uniquement par le manager."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Connexion requise.", "warning")
            return redirect(url_for("auth.login"))
        if current_user.role != "manager":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def chatter_required(f):
    """Route accessible uniquement par un chatter connecté."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Connexion requise.", "warning")
            return redirect(url_for("auth.login"))
        if current_user.role != "chatter":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def login_required_any(f):
    """Route accessible par tout utilisateur connecté (manager ou chatter)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Connexion requise.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated
