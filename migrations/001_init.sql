-- ═══════════════════════════════════════════════════════════════
-- Chatter Manager V2 — Schéma PostgreSQL initial
-- À appliquer une seule fois sur une base vide.
-- ═══════════════════════════════════════════════════════════════

-- ── Users ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'chatter'
                      CHECK (role IN ('manager', 'chatter')),
    chatter_id    INTEGER,               -- NULL pour le manager
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Chatters ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chatters (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'inactive')),
    date_joined DATE NOT NULL,
    notes       TEXT,
    shift_start TIME,       -- shift permanent ex: '00:00'
    shift_end   TIME        -- shift permanent ex: '08:00'
);

-- FK différée pour éviter la dépendance circulaire users ↔ chatters
-- DO block : ignore si la contrainte existe déjà (redéploiements successifs)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_chatter'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT fk_users_chatter
            FOREIGN KEY (chatter_id) REFERENCES chatters(id)
            ON DELETE SET NULL
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

-- ── Historique des changements de shift ──────────────────────────
CREATE TABLE IF NOT EXISTS shifts_history (
    id          SERIAL PRIMARY KEY,
    chatter_id  INTEGER NOT NULL REFERENCES chatters(id) ON DELETE CASCADE,
    old_start   TIME,
    old_end     TIME,
    new_start   TIME NOT NULL,
    new_end     TIME NOT NULL,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Ventes quotidiennes chatters ─────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_sales (
    id          SERIAL PRIMARY KEY,
    chatter_id  INTEGER NOT NULL REFERENCES chatters(id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    amount      NUMERIC(12,2) NOT NULL DEFAULT 0,
    UNIQUE (chatter_id, date)
);

-- ── Ventes quotidiennes manager ──────────────────────────────────
CREATE TABLE IF NOT EXISTS manager_sales (
    id      SERIAL PRIMARY KEY,
    date    DATE NOT NULL UNIQUE,
    amount  NUMERIC(12,2) NOT NULL DEFAULT 0
);

-- ── Malus ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS penalties (
    id          SERIAL PRIMARY KEY,
    chatter_id  INTEGER NOT NULL REFERENCES chatters(id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    amount      NUMERIC(10,2) NOT NULL DEFAULT 0,
    reason      TEXT NOT NULL,
    comment     TEXT
);

-- ── Primes ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bonuses (
    id          SERIAL PRIMARY KEY,
    chatter_id  INTEGER NOT NULL REFERENCES chatters(id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    amount      NUMERIC(10,2) NOT NULL DEFAULT 0,
    reason      TEXT NOT NULL,
    comment     TEXT
);

-- ── Objectifs mensuels ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS objectives (
    id      SERIAL PRIMARY KEY,
    month   SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    year    SMALLINT NOT NULL CHECK (year >= 2020),
    amount  NUMERIC(14,2) NOT NULL DEFAULT 0,
    UNIQUE (month, year)
);

-- ── Fiches de paie ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payrolls (
    id               SERIAL PRIMARY KEY,
    chatter_id       INTEGER NOT NULL REFERENCES chatters(id) ON DELETE CASCADE,
    month            SMALLINT NOT NULL,
    year             SMALLINT NOT NULL,
    base_commission  NUMERIC(12,2) NOT NULL DEFAULT 0,
    bonuses          NUMERIC(12,2) NOT NULL DEFAULT 0,
    penalties        NUMERIC(12,2) NOT NULL DEFAULT 0,
    final_amount     NUMERIC(12,2) NOT NULL DEFAULT 0,
    validated        BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (chatter_id, month, year)
);

-- ── Journal d'audit ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id          SERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action      TEXT NOT NULL,
    description TEXT NOT NULL
);

-- ── Index utiles ─────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_daily_sales_date       ON daily_sales(date);
CREATE INDEX IF NOT EXISTS idx_daily_sales_chatter    ON daily_sales(chatter_id);
CREATE INDEX IF NOT EXISTS idx_manager_sales_date     ON manager_sales(date);
CREATE INDEX IF NOT EXISTS idx_penalties_chatter      ON penalties(chatter_id);
CREATE INDEX IF NOT EXISTS idx_bonuses_chatter        ON bonuses(chatter_id);
CREATE INDEX IF NOT EXISTS idx_payrolls_period        ON payrolls(year, month);
CREATE INDEX IF NOT EXISTS idx_shifts_history_chatter ON shifts_history(chatter_id);

-- ── Modèles ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS models (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'inactive')),
    notes      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Associations chatters ↔ modèles (N-N) ────────────────────────
CREATE TABLE IF NOT EXISTS chatter_models (
    id          SERIAL PRIMARY KEY,
    chatter_id  INTEGER NOT NULL REFERENCES chatters(id) ON DELETE CASCADE,
    model_id    INTEGER NOT NULL REFERENCES models(id)   ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chatter_id, model_id)
);

CREATE INDEX IF NOT EXISTS idx_chatter_models_chatter ON chatter_models(chatter_id);
CREATE INDEX IF NOT EXISTS idx_chatter_models_model   ON chatter_models(model_id);

-- ── Objectifs personnels des chatters ───────────────────
CREATE TABLE IF NOT EXISTS chatter_objectives (
    id          SERIAL PRIMARY KEY,
    chatter_id  INTEGER NOT NULL REFERENCES chatters(id) ON DELETE CASCADE,
    month       SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    year        SMALLINT NOT NULL CHECK (year >= 2020),
    amount      NUMERIC(12,2) NOT NULL DEFAULT 0,
    UNIQUE (chatter_id, month, year)
);

CREATE INDEX IF NOT EXISTS idx_chatter_obj ON chatter_objectives(chatter_id);

-- ── Recruteurs : colonne recruiter_id sur chatters ──────
-- Un chatter peut être affilié à un seul recruteur (ou aucun)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='chatters' AND column_name='recruiter_id'
    ) THEN
        ALTER TABLE chatters ADD COLUMN recruiter_id INTEGER
            REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_chatters_recruiter ON chatters(recruiter_id);

-- ── Ajout du rôle recruiter dans la contrainte CHECK ────
-- On recrée la contrainte pour inclure 'recruiter'
DO $$
BEGIN
    -- Supprime l'ancienne contrainte si elle n'inclut pas recruiter
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname='users_role_check' AND conrelid='users'::regclass
    ) THEN
        ALTER TABLE users DROP CONSTRAINT users_role_check;
    END IF;
    -- Recrée avec les 3 rôles
    ALTER TABLE users ADD CONSTRAINT users_role_check
        CHECK (role IN ('manager','chatter','recruiter'));
EXCEPTION WHEN others THEN NULL;
END $$;
