-- B-Commie v2 — initial PostgreSQL schema.
-- Apply with: psql "$POSTGRES_DSN" -f migrations/0001_init.sql
-- (or via the `bcommie-migrate` helper described in README.md)

BEGIN;

CREATE TABLE IF NOT EXISTS reminders (
    id          BIGINT PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    guild_id    BIGINT,
    channel_id  BIGINT,
    message     TEXT NOT NULL,
    remind_at   TIMESTAMPTZ NOT NULL,
    reminded    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reminders_user_reminded ON reminders (user_id, reminded);
CREATE INDEX IF NOT EXISTS idx_reminders_due
    ON reminders (remind_at)
    WHERE reminded = FALSE;  -- native partial index: DuckDB could not do this

CREATE TABLE IF NOT EXISTS giveaways (
    id             BIGINT PRIMARY KEY,
    guild_id       BIGINT NOT NULL,
    channel_id     BIGINT NOT NULL,
    message_id     BIGINT,
    prize          TEXT NOT NULL,
    winners_count  INTEGER NOT NULL DEFAULT 1,
    ends_at        TIMESTAMPTZ NOT NULL,
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_giveaways_guild_active ON giveaways (guild_id, active);
CREATE INDEX IF NOT EXISTS idx_giveaways_due ON giveaways (ends_at) WHERE active = TRUE;

CREATE TABLE IF NOT EXISTS user_timezones (
    id          BIGINT PRIMARY KEY,  -- Discord user ID
    timezone    VARCHAR(64) NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;

-- Recommended (run manually by a DBA, not by the application):
--   CREATE ROLE bcommie_app LOGIN PASSWORD '...';
--   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bcommie_app;
--   -- The application connects as bcommie_app, never as a superuser (least privilege).
