"""
models.py — Helpers DB pour toutes les entités — V2
Toutes les requêtes SQL passent par run_sql() / commit() de database.py.
Compatibles PostgreSQL (%s) et SQLite (traduit automatiquement).
"""

from datetime import date, datetime
from database import run_sql, commit
from utils.calculations import (
    chatter_base_commission, chatter_final_salary,
    manager_total_remuneration, objective_stats
)

MONTHS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}


# ─── Audit ────────────────────────────────────────────────────────────────────

def log_action(action: str, description: str) -> None:
    run_sql(
        "INSERT INTO audit_log (timestamp, action, description) VALUES (%s, %s, %s)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), action, description)
    )
    commit()


# ─── Chatters ────────────────────────────────────────────────────────────────

def get_all_chatters(status: str = None) -> list:
    if status:
        return run_sql(
            "SELECT * FROM chatters WHERE status = %s ORDER BY name",
            (status,), fetch="all"
        ) or []
    return run_sql(
        "SELECT * FROM chatters ORDER BY status, name", fetch="all"
    ) or []


def get_chatter(chatter_id: int) -> dict | None:
    return run_sql(
        "SELECT * FROM chatters WHERE id = %s", (chatter_id,), fetch="one"
    )


def create_chatter(name: str, status: str, date_joined: str,
                   notes: str, shift_start: str, shift_end: str) -> int:
    """Crée un chatter et retourne son id. Compatible PostgreSQL et SQLite."""
    from database import _USE_SQLITE, get_db
    if _USE_SQLITE:
        # SQLite < 3.35 ne supporte pas RETURNING
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO chatters (name, status, date_joined, notes, shift_start, shift_end) VALUES (?, ?, ?, ?, ?, ?)",
            (name, status, date_joined, notes or None, shift_start or None, shift_end or None)
        )
        commit()
        return cur.lastrowid
    else:
        row = run_sql(
            """INSERT INTO chatters (name, status, date_joined, notes, shift_start, shift_end)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (name, status, date_joined, notes or None,
             shift_start or None, shift_end or None),
            fetch="one"
        )
        commit()
        return row["id"] if row else None


def update_chatter(chatter_id: int, name: str, status: str,
                   date_joined: str, notes: str) -> None:
    run_sql(
        "UPDATE chatters SET name=%s, status=%s, date_joined=%s, notes=%s WHERE id=%s",
        (name, status, date_joined, notes or None, chatter_id)
    )
    commit()


def update_chatter_shift(chatter_id: int, new_start: str, new_end: str) -> None:
    """Met à jour le shift permanent et enregistre l'historique."""
    old = get_chatter(chatter_id)
    if old:
        run_sql(
            """INSERT INTO shifts_history
                   (chatter_id, old_start, old_end, new_start, new_end)
               VALUES (%s, %s, %s, %s, %s)""",
            (chatter_id,
             str(old.get("shift_start")) if old.get("shift_start") else None,
             str(old.get("shift_end"))   if old.get("shift_end")   else None,
             new_start, new_end)
        )
    run_sql(
        "UPDATE chatters SET shift_start=%s, shift_end=%s WHERE id=%s",
        (new_start, new_end, chatter_id)
    )
    commit()


def toggle_chatter_status(chatter_id: int) -> str:
    c = get_chatter(chatter_id)
    if not c:
        return ""
    new_status = "inactive" if c["status"] == "active" else "active"
    run_sql("UPDATE chatters SET status=%s WHERE id=%s", (new_status, chatter_id))
    commit()
    return new_status


def delete_chatter(chatter_id: int) -> None:
    run_sql("DELETE FROM chatters WHERE id=%s", (chatter_id,))
    commit()


def get_shifts_history(chatter_id: int) -> list:
    return run_sql(
        """SELECT * FROM shifts_history WHERE chatter_id=%s
           ORDER BY changed_at DESC""",
        (chatter_id,), fetch="all"
    ) or []


# ─── CA ───────────────────────────────────────────────────────────────────────

def get_month_ca_chatters(month: int, year: int) -> float:
    row = run_sql(
        """SELECT COALESCE(SUM(amount), 0) AS total FROM daily_sales
           WHERE EXTRACT(MONTH FROM date)=%s AND EXTRACT(YEAR FROM date)=%s""",
        (month, year), fetch="one"
    )
    return float(row["total"]) if row else 0.0


def get_month_ca_manager(month: int, year: int) -> float:
    row = run_sql(
        """SELECT COALESCE(SUM(amount), 0) AS total FROM manager_sales
           WHERE EXTRACT(MONTH FROM date)=%s AND EXTRACT(YEAR FROM date)=%s""",
        (month, year), fetch="one"
    )
    return float(row["total"]) if row else 0.0


def get_chatter_month_stats(chatter_id: int, month: int, year: int) -> dict:
    row = run_sql(
        """SELECT COALESCE(SUM(amount),0) AS ca, COUNT(*) AS days
           FROM daily_sales
           WHERE chatter_id=%s
             AND EXTRACT(MONTH FROM date)=%s
             AND EXTRACT(YEAR  FROM date)=%s""",
        (chatter_id, month, year), fetch="one"
    )
    ca   = float(row["ca"])   if row else 0.0
    days = int(row["days"])   if row else 0

    bon = run_sql(
        """SELECT COALESCE(SUM(amount),0) AS total FROM bonuses
           WHERE chatter_id=%s
             AND EXTRACT(MONTH FROM date)=%s
             AND EXTRACT(YEAR  FROM date)=%s""",
        (chatter_id, month, year), fetch="one"
    )
    pen = run_sql(
        """SELECT COALESCE(SUM(amount),0) AS total FROM penalties
           WHERE chatter_id=%s
             AND EXTRACT(MONTH FROM date)=%s
             AND EXTRACT(YEAR  FROM date)=%s""",
        (chatter_id, month, year), fetch="one"
    )
    total_bonuses   = float(bon["total"]) if bon else 0.0
    total_penalties = float(pen["total"]) if pen else 0.0
    avg             = round(ca / days, 2) if days > 0 else 0.0

    return {
        "ca": ca, "days": days, "avg": avg,
        "base_commission":  chatter_base_commission(ca),
        "total_bonuses":    total_bonuses,
        "total_penalties":  total_penalties,
        "final_salary":     chatter_final_salary(ca, total_bonuses, total_penalties),
    }


def get_daily_sales_for_date(sel_date: str) -> dict:
    rows = run_sql(
        "SELECT chatter_id, amount FROM daily_sales WHERE date=%s",
        (sel_date,), fetch="all"
    ) or []
    return {r["chatter_id"]: float(r["amount"]) for r in rows}


def get_manager_ca_for_date(sel_date: str) -> float:
    row = run_sql(
        "SELECT amount FROM manager_sales WHERE date=%s", (sel_date,), fetch="one"
    )
    return float(row["amount"]) if row else 0.0


def upsert_daily_sale(chatter_id: int, sale_date: str, amount: float) -> None:
    run_sql(
        """INSERT INTO daily_sales (chatter_id, date, amount) VALUES (%s, %s, %s)
           ON CONFLICT (chatter_id, date) DO UPDATE SET amount=EXCLUDED.amount""",
        (chatter_id, sale_date, amount)
    )


def upsert_manager_sale(sale_date: str, amount: float) -> None:
    run_sql(
        """INSERT INTO manager_sales (date, amount) VALUES (%s, %s)
           ON CONFLICT (date) DO UPDATE SET amount=EXCLUDED.amount""",
        (sale_date, amount)
    )


def get_recent_sales(chatter_id: int, limit: int = 30) -> list:
    return run_sql(
        """SELECT date, amount FROM daily_sales WHERE chatter_id=%s
           ORDER BY date DESC LIMIT %s""",
        (chatter_id, limit), fetch="all"
    ) or []


def get_available_months() -> list:
    rows = run_sql(
        """SELECT DISTINCT
               EXTRACT(YEAR  FROM date)::INT AS y,
               EXTRACT(MONTH FROM date)::INT AS m
           FROM daily_sales ORDER BY y DESC, m DESC""",
        fetch="all"
    ) or []
    today = date.today()
    result = [{"month": today.month, "year": today.year}]
    for r in rows:
        entry = {"month": r["m"], "year": r["y"]}
        if entry not in result:
            result.append(entry)
    return result


# ─── Classement ───────────────────────────────────────────────────────────────

def get_ranking(month: int, year: int, sort: str = "ca") -> list:
    chatters = get_all_chatters()
    data = []
    for c in chatters:
        s = get_chatter_month_stats(c["id"], month, year)
        if s["ca"] > 0 or s["days"] > 0:
            data.append({"chatter": c, **s})

    key = {"avg": "avg", "days": "days"}.get(sort, "ca")
    data.sort(key=lambda x: x[key], reverse=True)

    # Ajoute le rang
    for i, item in enumerate(data):
        item["rank"] = i + 1
    return data


def get_chatter_rank(chatter_id: int, month: int, year: int) -> int:
    ranking = get_ranking(month, year)
    for item in ranking:
        if item["chatter"]["id"] == chatter_id:
            return item["rank"]
    return 0


# ─── Primes & Malus ───────────────────────────────────────────────────────────

def add_bonus(chatter_id: int, b_date: str, amount: float,
              reason: str, comment: str = "") -> None:
    run_sql(
        "INSERT INTO bonuses (chatter_id, date, amount, reason, comment) VALUES (%s,%s,%s,%s,%s)",
        (chatter_id, b_date, amount, reason, comment or None)
    )
    commit()


def delete_bonus(bonus_id: int) -> None:
    run_sql("DELETE FROM bonuses WHERE id=%s", (bonus_id,))
    commit()


def add_penalty(chatter_id: int, p_date: str, amount: float,
                reason: str, comment: str = "") -> None:
    run_sql(
        "INSERT INTO penalties (chatter_id, date, amount, reason, comment) VALUES (%s,%s,%s,%s,%s)",
        (chatter_id, p_date, amount, reason, comment or None)
    )
    commit()


def delete_penalty(penalty_id: int) -> None:
    run_sql("DELETE FROM penalties WHERE id=%s", (penalty_id,))
    commit()


def get_month_bonuses(chatter_id: int, month: int, year: int) -> list:
    return run_sql(
        """SELECT * FROM bonuses WHERE chatter_id=%s
           AND EXTRACT(MONTH FROM date)=%s AND EXTRACT(YEAR FROM date)=%s
           ORDER BY date DESC""",
        (chatter_id, month, year), fetch="all"
    ) or []


def get_month_penalties(chatter_id: int, month: int, year: int) -> list:
    return run_sql(
        """SELECT * FROM penalties WHERE chatter_id=%s
           AND EXTRACT(MONTH FROM date)=%s AND EXTRACT(YEAR FROM date)=%s
           ORDER BY date DESC""",
        (chatter_id, month, year), fetch="all"
    ) or []


# ─── Objectifs ────────────────────────────────────────────────────────────────

def upsert_objective(month: int, year: int, amount: float) -> None:
    run_sql(
        """INSERT INTO objectives (month, year, amount) VALUES (%s,%s,%s)
           ON CONFLICT (month, year) DO UPDATE SET amount=EXCLUDED.amount""",
        (month, year, amount)
    )
    commit()


def get_objective(month: int, year: int) -> float:
    row = run_sql(
        "SELECT amount FROM objectives WHERE month=%s AND year=%s",
        (month, year), fetch="one"
    )
    return float(row["amount"]) if row else 0.0


def get_all_objectives() -> list:
    return run_sql(
        "SELECT * FROM objectives ORDER BY year DESC, month DESC",
        fetch="all"
    ) or []


# ─── Paies ────────────────────────────────────────────────────────────────────

def get_payroll_row(chatter_id: int, month: int, year: int) -> dict | None:
    return run_sql(
        "SELECT * FROM payrolls WHERE chatter_id=%s AND month=%s AND year=%s",
        (chatter_id, month, year), fetch="one"
    )


def is_month_locked(month: int, year: int) -> bool:
    row = run_sql(
        "SELECT 1 FROM payrolls WHERE month=%s AND year=%s AND validated=%s LIMIT 1",
        (month, year, True), fetch="one"
    )
    return row is not None


def validate_month(month: int, year: int) -> None:
    run_sql(
        "UPDATE payrolls SET validated=%s WHERE month=%s AND year=%s",
        (True, month, year)
    )
    commit()


def unlock_month(month: int, year: int) -> None:
    run_sql(
        "UPDATE payrolls SET validated=%s WHERE month=%s AND year=%s",
        (False, month, year)
    )
    commit()


def get_chatter_payrolls(chatter_id: int) -> list:
    """Retourne toutes les fiches de paie validées d'un chatter, les plus récentes en premier."""
    return run_sql(
        """SELECT * FROM payrolls WHERE chatter_id=%s AND validated=%s
           ORDER BY year DESC, month DESC""",
        (chatter_id, True), fetch="all"
    ) or []


# ─── Users ────────────────────────────────────────────────────────────────────

def get_all_users() -> list:
    return run_sql(
        """SELECT u.*, c.name AS chatter_name
           FROM users u
           LEFT JOIN chatters c ON c.id = u.chatter_id
           ORDER BY u.role, u.username""",
        fetch="all"
    ) or []


def get_user(user_id: int) -> dict | None:
    return run_sql("SELECT * FROM users WHERE id=%s", (user_id,), fetch="one")


def create_user(username: str, password: str, role: str,
                chatter_id: int = None) -> None:
    from werkzeug.security import generate_password_hash
    run_sql(
        """INSERT INTO users (username, password_hash, role, chatter_id)
           VALUES (%s, %s, %s, %s)""",
        (username, generate_password_hash(password), role, chatter_id)
    )
    commit()


def update_user_password(user_id: int, new_password: str) -> None:
    from werkzeug.security import generate_password_hash
    run_sql(
        "UPDATE users SET password_hash=%s WHERE id=%s",
        (generate_password_hash(new_password), user_id)
    )
    commit()


def toggle_user_active(user_id: int) -> bool:
    row = run_sql("SELECT active FROM users WHERE id=%s", (user_id,), fetch="one")
    if not row:
        return False
    new_val = not bool(row["active"])
    run_sql("UPDATE users SET active=%s WHERE id=%s", (new_val, user_id))
    commit()
    return new_val


# ─── Dashboard helpers ────────────────────────────────────────────────────────

def get_shifts_overview() -> dict:
    """Retourne les chatters regroupés par shift pour la vue planning."""
    chatters = run_sql(
        """SELECT id, name, shift_start, shift_end
           FROM chatters WHERE status='active'
           ORDER BY shift_start NULLS LAST, name""",
        fetch="all"
    ) or []

    groups = {}
    no_shift = []
    for c in chatters:
        s = c.get("shift_start")
        e = c.get("shift_end")
        if s and e:
            key = f"{str(s)[:5]} → {str(e)[:5]}"
            groups.setdefault(key, []).append(c)
        else:
            no_shift.append(c)
    return {"groups": groups, "no_shift": no_shift}


# ─── Modèles ──────────────────────────────────────────────────────────────────

def get_all_models(active_only: bool = False) -> list:
    if active_only:
        return run_sql(
            "SELECT * FROM models WHERE status='active' ORDER BY name",
            fetch="all"
        ) or []
    return run_sql(
        "SELECT * FROM models ORDER BY status, name", fetch="all"
    ) or []


def get_model(model_id: int) -> dict | None:
    return run_sql(
        "SELECT * FROM models WHERE id=%s", (model_id,), fetch="one"
    )


def create_model(name: str, notes: str = "") -> int:
    """Crée un modèle et retourne son id (compatible SQLite + PostgreSQL)."""
    from database import _USE_SQLITE, get_db
    if _USE_SQLITE:
        cur = get_db().execute(
            "INSERT INTO models (name, notes) VALUES (?, ?)",
            (name.strip(), notes.strip() or None)
        )
        commit()
        return cur.lastrowid
    else:
        row = run_sql(
            "INSERT INTO models (name, notes) VALUES (%s, %s) RETURNING id",
            (name.strip(), notes.strip() or None), fetch="one"
        )
        commit()
        return row["id"] if row else None


def update_model(model_id: int, name: str, notes: str) -> None:
    run_sql(
        "UPDATE models SET name=%s, notes=%s WHERE id=%s",
        (name.strip(), notes.strip() or None, model_id)
    )
    commit()


def toggle_model_status(model_id: int) -> str:
    m = get_model(model_id)
    if not m:
        return ""
    new_status = "inactive" if m["status"] == "active" else "active"
    run_sql("UPDATE models SET status=%s WHERE id=%s", (new_status, model_id))
    commit()
    return new_status


# ─── Associations chatter ↔ modèle ────────────────────────────────────────────

def get_chatter_models(chatter_id: int) -> list:
    """Modèles attribués à un chatter (actifs + inactifs)."""
    return run_sql(
        """SELECT m.*, cm.assigned_at
           FROM models m
           JOIN chatter_models cm ON cm.model_id = m.id
           WHERE cm.chatter_id = %s
           ORDER BY m.name""",
        (chatter_id,), fetch="all"
    ) or []


def get_model_chatters(model_id: int) -> list:
    """Chatters assignés à un modèle."""
    return run_sql(
        """SELECT c.*, cm.assigned_at
           FROM chatters c
           JOIN chatter_models cm ON cm.chatter_id = c.id
           WHERE cm.model_id = %s
           ORDER BY c.name""",
        (model_id,), fetch="all"
    ) or []


def assign_model(chatter_id: int, model_id: int) -> None:
    """Attribue un modèle à un chatter (ignore si déjà présent)."""
    run_sql(
        """INSERT INTO chatter_models (chatter_id, model_id)
           VALUES (%s, %s)
           ON CONFLICT (chatter_id, model_id) DO NOTHING""",
        (chatter_id, model_id)
    )
    commit()


def remove_model(chatter_id: int, model_id: int) -> None:
    """Retire l'association chatter ↔ modèle."""
    run_sql(
        "DELETE FROM chatter_models WHERE chatter_id=%s AND model_id=%s",
        (chatter_id, model_id)
    )
    commit()


def get_unassigned_models(chatter_id: int) -> list:
    """Modèles actifs non encore attribués à ce chatter."""
    return run_sql(
        """SELECT m.* FROM models m
           WHERE m.status = 'active'
             AND m.id NOT IN (
                 SELECT model_id FROM chatter_models WHERE chatter_id = %s
             )
           ORDER BY m.name""",
        (chatter_id,), fetch="all"
    ) or []


# ─── Objectifs personnels des chatters ───────────────────────────────────────

def get_chatter_objective(chatter_id: int, month: int, year: int) -> float:
    row = run_sql(
        "SELECT amount FROM chatter_objectives WHERE chatter_id=%s AND month=%s AND year=%s",
        (chatter_id, month, year), fetch="one"
    )
    return float(row["amount"]) if row else 0.0


def upsert_chatter_objective(chatter_id: int, month: int, year: int, amount: float) -> None:
    run_sql(
        """INSERT INTO chatter_objectives (chatter_id, month, year, amount)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (chatter_id, month, year) DO UPDATE SET amount=EXCLUDED.amount""",
        (chatter_id, month, year, amount)
    )
    commit()


def get_all_chatter_objectives(chatter_id: int) -> list:
    return run_sql(
        """SELECT * FROM chatter_objectives WHERE chatter_id=%s
           ORDER BY year DESC, month DESC""",
        (chatter_id,), fetch="all"
    ) or []
