"""
Génération des fiches de paie — V2 (PostgreSQL compatible).
Utilise run_sql() de database.py (placeholders %s).
"""

from database import run_sql
from utils.calculations import chatter_base_commission, chatter_final_salary


def compute_payroll(chatter_id: int, month: int, year: int) -> dict:
    row = run_sql(
        """SELECT COALESCE(SUM(amount), 0) AS total FROM daily_sales
           WHERE chatter_id = %s
             AND EXTRACT(MONTH FROM date) = %s
             AND EXTRACT(YEAR  FROM date) = %s""",
        (chatter_id, month, year), fetch="one"
    )
    ca_net = float(row["total"])

    row = run_sql(
        """SELECT COALESCE(SUM(amount), 0) AS total FROM bonuses
           WHERE chatter_id = %s
             AND EXTRACT(MONTH FROM date) = %s
             AND EXTRACT(YEAR  FROM date) = %s""",
        (chatter_id, month, year), fetch="one"
    )
    total_bonuses = float(row["total"])

    row = run_sql(
        """SELECT COALESCE(SUM(amount), 0) AS total FROM penalties
           WHERE chatter_id = %s
             AND EXTRACT(MONTH FROM date) = %s
             AND EXTRACT(YEAR  FROM date) = %s""",
        (chatter_id, month, year), fetch="one"
    )
    total_penalties = float(row["total"])

    base  = chatter_base_commission(ca_net)
    final = chatter_final_salary(ca_net, total_bonuses, total_penalties)

    return {
        "chatter_id":     chatter_id,
        "month":          month,
        "year":           year,
        "ca_net":         ca_net,
        "base_commission": base,
        "total_bonuses":  total_bonuses,
        "total_penalties": total_penalties,
        "final_amount":   final,
    }


def save_payroll(data: dict) -> None:
    run_sql(
        """INSERT INTO payrolls
               (chatter_id, month, year, base_commission, bonuses, penalties, final_amount)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (chatter_id, month, year) DO UPDATE SET
               base_commission = EXCLUDED.base_commission,
               bonuses         = EXCLUDED.bonuses,
               penalties       = EXCLUDED.penalties,
               final_amount    = EXCLUDED.final_amount""",
        (
            data["chatter_id"], data["month"], data["year"],
            data["base_commission"], data["total_bonuses"],
            data["total_penalties"], data["final_amount"],
        )
    )
