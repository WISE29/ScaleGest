"""
database.py — Chatter Manager V2
Connexion PostgreSQL partagée par requête via flask.g.
Fermeture automatique par teardown_appcontext.

En développement local sans PostgreSQL : définir DATABASE_URL=sqlite:///dev.db
dans .env pour utiliser SQLite (les requêtes SQL sont identiques sauf mention contraire).
"""

import os
import sqlite3
from flask import g

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Détecte le moteur à utiliser
_USE_SQLITE = DATABASE_URL.startswith("sqlite:///") or DATABASE_URL == ""


def _sqlite_path() -> str:
    if DATABASE_URL.startswith("sqlite:///"):
        return DATABASE_URL[len("sqlite:///"):]
    # Fallback : dev.db dans le dossier du projet
    return os.path.join(os.path.dirname(__file__), "dev.db")


# ─── Adaptateur SQLite qui expose la même interface que psycopg2 ──────────────

class _SQLiteConn:
    """Wrapper SQLite qui expose fetchone/fetchall/execute compatibles."""

    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA synchronous = NORMAL")

    def execute(self, sql: str, params=()):
        """Traduit SQL PostgreSQL → SQLite avant exécution."""
        s = sql.replace("%s", "?")
        # EXTRACT(MONTH FROM col) → CAST(strftime('%m', col) AS INTEGER)
        import re
        s = re.sub(
            r"EXTRACT\s*\(\s*MONTH\s+FROM\s+(\w+)\s*\)",
            r"CAST(strftime('%m', \1) AS INTEGER)",
            s, flags=re.IGNORECASE
        )
        # EXTRACT(YEAR FROM col) → CAST(strftime('%Y', col) AS INTEGER)
        s = re.sub(
            r"EXTRACT\s*\(\s*YEAR\s+FROM\s+(\w+)\s*\)",
            r"CAST(strftime('%Y', \1) AS INTEGER)",
            s, flags=re.IGNORECASE
        )
        # date::TEXT → CAST(date AS TEXT)
        s = re.sub(r"(\w+)::TEXT", r"CAST(\1 AS TEXT)", s, flags=re.IGNORECASE)
        # ::DATE, ::INT, ::INTEGER → supprimés (SQLite les ignore)
        s = re.sub(r"::(DATE|INT|INTEGER|NUMERIC|BOOLEAN)", "", s, flags=re.IGNORECASE)
        # NOW() → datetime('now')
        s = re.sub(r"\bNOW\s*\(\s*\)", "datetime('now')", s, flags=re.IGNORECASE)
        cur = self._conn.execute(s, params)
        return _SQLiteCursor(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


class _SQLiteCursor:
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self):
        return [dict(r) for r in self._cur.fetchall()]

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return self._cur.lastrowid


# ─── Connexion PostgreSQL ──────────────────────────────────────────────────────

class _PGConn:
    """Wrapper psycopg2 qui expose la même interface que _SQLiteConn."""

    def __init__(self, raw_conn):
        self._conn = raw_conn

    def execute(self, sql: str, params=()):
        import psycopg2.extras
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return _PGCursor(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


class _PGCursor:
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        rows = self._cur.fetchall()
        return [dict(r) for r in rows] if rows else []

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        # PostgreSQL : utiliser RETURNING id dans le SQL
        # lastrowid n'est pas supporté nativement — retourne None
        return None


def _pg_connect():
    import psycopg2
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    raw = psycopg2.connect(url)
    raw.autocommit = False
    return _PGConn(raw)


# ─── Interface publique ────────────────────────────────────────────────────────

def get_db():
    """Retourne la connexion liée à la requête courante (crée si absente)."""
    if "db" not in g:
        if _USE_SQLITE:
            g.db = _SQLiteConn(_sqlite_path())
        else:
            g.db = _pg_connect()
    return g.db


def close_db(e=None):
    """Ferme la connexion en fin de requête."""
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass


def run_sql(sql: str, params=(), fetch: str = "none"):
    """
    Exécute une requête sur la connexion courante.
    fetch : "one" | "all" | "none"
    Retourne le résultat ou None.
    """
    conn = get_db()
    cur = conn.execute(sql, params)
    if fetch == "one":
        return cur.fetchone()
    if fetch == "all":
        return cur.fetchall()
    return None


def commit():
    get_db().commit()


# ─── Initialisation du schéma ──────────────────────────────────────────────────

def init_db(app):
    """
    Applique migrations/001_init.sql sur la base.
    Appelé une seule fois au premier démarrage.
    """
    sql_path = os.path.join(os.path.dirname(__file__), "migrations", "001_init.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        schema = f.read()

    if _USE_SQLITE:
        conn = _SQLiteConn(_sqlite_path())
        # SQLite ne supporte pas les statements PostgreSQL-only (SERIAL etc.)
        # On utilise une version SQLite du schéma
        _apply_sqlite_schema(conn)
        conn.commit()
        conn.close()
    else:
        import psycopg2
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        conn = psycopg2.connect(url)
        conn.autocommit = True
        with conn.cursor() as cur:
            try:
                cur.execute(schema)
            except psycopg2.Error as e:
                import sys
                print(f"[init_db] Avertissement SQL : {e}", file=sys.stderr)
        conn.close()

    _ensure_manager(app)


def _apply_sqlite_schema(conn):
    """Schéma SQLite équivalent pour le développement local."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'chatter',
            chatter_id INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chatters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            date_joined TEXT NOT NULL,
            notes TEXT,
            shift_start TEXT,
            shift_end TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shifts_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chatter_id INTEGER NOT NULL,
            old_start TEXT,
            old_end TEXT,
            new_start TEXT NOT NULL,
            new_end TEXT NOT NULL,
            changed_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (chatter_id) REFERENCES chatters(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chatter_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (chatter_id) REFERENCES chatters(id) ON DELETE CASCADE,
            UNIQUE(chatter_id, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS manager_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            amount REAL NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS penalties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chatter_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            reason TEXT NOT NULL,
            comment TEXT,
            FOREIGN KEY (chatter_id) REFERENCES chatters(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bonuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chatter_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            reason TEXT NOT NULL,
            comment TEXT,
            FOREIGN KEY (chatter_id) REFERENCES chatters(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS objectives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            UNIQUE(month, year)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payrolls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chatter_id INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            base_commission REAL NOT NULL DEFAULT 0,
            bonuses REAL NOT NULL DEFAULT 0,
            penalties REAL NOT NULL DEFAULT 0,
            final_amount REAL NOT NULL DEFAULT 0,
            validated INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (chatter_id) REFERENCES chatters(id) ON DELETE CASCADE,
            UNIQUE(chatter_id, month, year)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            description TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chatter_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chatter_id INTEGER NOT NULL,
            model_id INTEGER NOT NULL,
            assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (chatter_id) REFERENCES chatters(id) ON DELETE CASCADE,
            FOREIGN KEY (model_id)   REFERENCES models(id)   ON DELETE CASCADE,
            UNIQUE(chatter_id, model_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chatter_objectives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chatter_id INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (chatter_id) REFERENCES chatters(id) ON DELETE CASCADE,
            UNIQUE(chatter_id, month, year)
        )
    """)


def _ensure_manager(app):
    """
    Crée le compte manager initial s'il n'existe pas.
    Utilise une connexion directe (pas flask.g) car appelé hors requête.
    """
    from werkzeug.security import generate_password_hash
    username = os.environ.get("INIT_MANAGER_USERNAME", "manager")
    password = os.environ.get("INIT_MANAGER_PASSWORD", "manager123")
    pwd_hash = generate_password_hash(password)

    if _USE_SQLITE:
        # SQLite : connexion directe via notre wrapper
        conn = _SQLiteConn(_sqlite_path())
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, pwd_hash, "manager")
            )
            conn.commit()
        conn.close()
    else:
        # PostgreSQL : connexion directe psycopg2 avec curseur explicite
        import psycopg2
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        conn = psycopg2.connect(url)
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM users WHERE username = %s", (username,)
                )
                existing = cur.fetchone()
                if not existing:
                    cur.execute(
                        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                        (username, pwd_hash, "manager")
                    )
            conn.commit()
        except Exception as e:
            conn.rollback()
            import sys
            print(f"[_ensure_manager] Erreur : {e}", file=sys.stderr)
        finally:
            conn.close()
