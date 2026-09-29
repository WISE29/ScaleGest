"""
migrate_from_v1.py — Script de migration V1 SQLite → V2 PostgreSQL

Usage :
    python migrations/migrate_from_v1.py \
        --sqlite ../chatter-manager/database.db \
        --pg postgresql://user:pass@host:5432/chatter_manager_v2

Ce script :
1. Lit toutes les données depuis la base SQLite V1
2. Les insère dans la base PostgreSQL V2 (qui doit déjà avoir le schéma 001_init.sql)
3. Les shifts permanents seront NULL après migration (à définir dans l'interface)
"""

import argparse
import sqlite3
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("[ERREUR] psycopg2-binary non installé. Lancez : pip install psycopg2-binary")
    sys.exit(1)


def migrate(sqlite_path: str, pg_url: str):
    print(f"Connexion SQLite : {sqlite_path}")
    sq = sqlite3.connect(sqlite_path)
    sq.row_factory = sqlite3.Row

    if pg_url.startswith("postgres://"):
        pg_url = "postgresql://" + pg_url[len("postgres://"):]

    print(f"Connexion PostgreSQL : {pg_url[:40]}...")
    pg = psycopg2.connect(pg_url, cursor_factory=psycopg2.extras.RealDictCursor)
    pg.autocommit = False

    try:
        with pg.cursor() as cur:
            _migrate_chatters(sq, cur)
            _migrate_daily_sales(sq, cur)
            _migrate_manager_sales(sq, cur)
            _migrate_penalties(sq, cur)
            _migrate_bonuses(sq, cur)
            _migrate_objectives(sq, cur)
            _migrate_payrolls(sq, cur)
            _reset_sequences(cur)

        pg.commit()
        print("\n✓ Migration terminée avec succès.")
        print("  Les shifts permanents sont NULL — assignez-les depuis l'interface manager.")

    except Exception as e:
        pg.rollback()
        print(f"\n[ERREUR] Migration annulée : {e}")
        raise
    finally:
        sq.close()
        pg.close()


def _migrate_chatters(sq, cur):
    rows = sq.execute("SELECT * FROM chatters").fetchall()
    print(f"  chatters : {len(rows)} lignes")
    for r in rows:
        cur.execute("""
            INSERT INTO chatters (id, name, status, date_joined, notes, shift_start, shift_end)
            VALUES (%s, %s, %s, %s::DATE, %s, NULL, NULL)
            ON CONFLICT (id) DO NOTHING
        """, (r["id"], r["name"], r["status"], r["date_joined"], r["notes"]))
    if rows:
        cur.execute("SELECT setval('chatters_id_seq', (SELECT MAX(id) FROM chatters))")


def _migrate_daily_sales(sq, cur):
    rows = sq.execute("SELECT * FROM daily_sales").fetchall()
    print(f"  daily_sales : {len(rows)} lignes")
    for r in rows:
        cur.execute("""
            INSERT INTO daily_sales (chatter_id, date, amount)
            VALUES (%s, %s::DATE, %s)
            ON CONFLICT (chatter_id, date) DO UPDATE SET amount = EXCLUDED.amount
        """, (r["chatter_id"], r["date"], r["amount"]))


def _migrate_manager_sales(sq, cur):
    rows = sq.execute("SELECT * FROM manager_sales").fetchall()
    print(f"  manager_sales : {len(rows)} lignes")
    for r in rows:
        cur.execute("""
            INSERT INTO manager_sales (date, amount)
            VALUES (%s::DATE, %s)
            ON CONFLICT (date) DO UPDATE SET amount = EXCLUDED.amount
        """, (r["date"], r["amount"]))


def _migrate_penalties(sq, cur):
    rows = sq.execute("SELECT * FROM penalties").fetchall()
    print(f"  penalties : {len(rows)} lignes")
    for r in rows:
        cur.execute("""
            INSERT INTO penalties (chatter_id, date, amount, reason, comment)
            VALUES (%s, %s::DATE, %s, %s, %s)
        """, (r["chatter_id"], r["date"], r["amount"], r["reason"], r["comment"]))


def _migrate_bonuses(sq, cur):
    rows = sq.execute("SELECT * FROM bonuses").fetchall()
    print(f"  bonuses : {len(rows)} lignes")
    for r in rows:
        cur.execute("""
            INSERT INTO bonuses (chatter_id, date, amount, reason, comment)
            VALUES (%s, %s::DATE, %s, %s, %s)
        """, (r["chatter_id"], r["date"], r["amount"], r["reason"], r["comment"]))


def _migrate_objectives(sq, cur):
    rows = sq.execute("SELECT * FROM objectives").fetchall()
    print(f"  objectives : {len(rows)} lignes")
    for r in rows:
        cur.execute("""
            INSERT INTO objectives (month, year, amount)
            VALUES (%s, %s, %s)
            ON CONFLICT (month, year) DO UPDATE SET amount = EXCLUDED.amount
        """, (r["month"], r["year"], r["amount"]))


def _migrate_payrolls(sq, cur):
    rows = sq.execute("SELECT * FROM payrolls").fetchall()
    print(f"  payrolls : {len(rows)} lignes")
    for r in rows:
        cur.execute("""
            INSERT INTO payrolls
                (chatter_id, month, year, base_commission, bonuses, penalties, final_amount, validated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chatter_id, month, year) DO NOTHING
        """, (
            r["chatter_id"], r["month"], r["year"],
            r["base_commission"], r["bonuses"], r["penalties"], r["final_amount"],
            bool(r["validated"])
        ))


def _reset_sequences(cur):
    """Remet à jour toutes les séquences SERIAL après import avec IDs manuels."""
    tables = [
        "chatters", "daily_sales", "manager_sales",
        "penalties", "bonuses", "objectives", "payrolls"
    ]
    for t in tables:
        cur.execute(f"SELECT setval('{t}_id_seq', COALESCE((SELECT MAX(id) FROM {t}), 1))")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migration V1 SQLite → V2 PostgreSQL")
    parser.add_argument("--sqlite", required=True, help="Chemin vers database.db de la V1")
    parser.add_argument("--pg",     required=True, help="URL PostgreSQL V2")
    args = parser.parse_args()
    migrate(args.sqlite, args.pg)
