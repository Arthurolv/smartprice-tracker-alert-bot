CREATE TABLE IF NOT EXISTS products (
    app_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    currency TEXT NOT NULL CHECK (currency = 'BRL'),
    url TEXT NOT NULL,
    target_cents INTEGER NOT NULL CHECK (target_cents >= 0)
);

CREATE TABLE IF NOT EXISTS price_history (
    app_id INTEGER NOT NULL REFERENCES products(app_id),
    day TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    PRIMARY KEY (app_id, day)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS sent_alerts (
    app_id INTEGER NOT NULL REFERENCES products(app_id),
    target_cents INTEGER NOT NULL CHECK (target_cents >= 0),
    episode_start TEXT NOT NULL,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (app_id, target_cents, episode_start)
) WITHOUT ROWID;
