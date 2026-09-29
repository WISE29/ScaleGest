-- ═══════════════════════════════════════════════════════════════
-- Chatter Manager V2 — Migration des données depuis la V1 SQLite
--
-- Utilisation :
--   1. Exporter la V1 SQLite vers CSV ou SQL dump
--   2. Créer la base PostgreSQL V2 avec 001_init.sql
--   3. Exécuter ce script pour importer les données
--
-- Ce script suppose que les données ont été importées dans des
-- tables temporaires préfixées "v1_" :
--   v1_chatters, v1_daily_sales, v1_manager_sales,
--   v1_penalties, v1_bonuses, v1_objectives, v1_payrolls
--
-- Pour créer ces tables temporaires depuis SQLite :
--   sqlite3 dev.db .dump > v1_dump.sql
--   Puis adapter manuellement ou utiliser le script Python
--   migrations/migrate_from_v1.py
-- ═══════════════════════════════════════════════════════════════

-- ── Chatters ─────────────────────────────────────────────────────
-- Les colonnes shift_start / shift_end n'existent pas en V1.
-- Elles seront NULL après migration ; le manager les renseignera.
INSERT INTO chatters (id, name, status, date_joined, notes, shift_start, shift_end)
SELECT
    id,
    name,
    status,
    date_joined::DATE,
    notes,
    NULL,   -- shift_start à définir manuellement
    NULL    -- shift_end   à définir manuellement
FROM v1_chatters
ON CONFLICT (id) DO NOTHING;

-- Réinitialise la séquence après import manuel des IDs
SELECT setval('chatters_id_seq', (SELECT MAX(id) FROM chatters));

-- ── Ventes quotidiennes chatters ─────────────────────────────────
INSERT INTO daily_sales (chatter_id, date, amount)
SELECT chatter_id, date::DATE, amount
FROM v1_daily_sales
ON CONFLICT (chatter_id, date) DO UPDATE SET amount = EXCLUDED.amount;

-- ── Ventes quotidiennes manager ──────────────────────────────────
INSERT INTO manager_sales (date, amount)
SELECT date::DATE, amount
FROM v1_manager_sales
ON CONFLICT (date) DO UPDATE SET amount = EXCLUDED.amount;

-- ── Malus ────────────────────────────────────────────────────────
INSERT INTO penalties (chatter_id, date, amount, reason, comment)
SELECT chatter_id, date::DATE, amount, reason, comment
FROM v1_penalties;

-- ── Primes ───────────────────────────────────────────────────────
INSERT INTO bonuses (chatter_id, date, amount, reason, comment)
SELECT chatter_id, date::DATE, amount, reason, comment
FROM v1_bonuses;

-- ── Objectifs ────────────────────────────────────────────────────
INSERT INTO objectives (month, year, amount)
SELECT month, year, amount
FROM v1_objectives
ON CONFLICT (month, year) DO UPDATE SET amount = EXCLUDED.amount;

-- ── Fiches de paie ───────────────────────────────────────────────
-- En V1 "validated" est un INTEGER (0/1) → BOOLEAN en V2
INSERT INTO payrolls (chatter_id, month, year, base_commission, bonuses, penalties, final_amount, validated)
SELECT
    chatter_id,
    month,
    year,
    base_commission,
    bonuses,
    penalties,
    final_amount,
    CASE WHEN validated = 1 THEN TRUE ELSE FALSE END
FROM v1_payrolls
ON CONFLICT (chatter_id, month, year) DO NOTHING;
