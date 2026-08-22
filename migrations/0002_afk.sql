-- B-Commie v2 — adds afk_status (missing from 0001_init.sql).
BEGIN;

CREATE TABLE IF NOT EXISTS afk_status (
    id      BIGINT PRIMARY KEY,  -- Discord user ID
    reason  TEXT NOT NULL,
    since   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;