-- GlassRelay database schema

CREATE TABLE IF NOT EXISTS guild (
    guild_id      INTEGER PRIMARY KEY,
    api_key       TEXT,
    ratio         INTEGER NOT NULL DEFAULT 1000, -- if ratio == 1000; then 1 USD = 1000 credits
    claim_message TEXT,                  -- NULL means the default message
    log_channel   INTEGER NOT NULL DEFAULT 0 -- 0 means no logging
);

CREATE TABLE IF NOT EXISTS product (
    guild_id   INTEGER NOT NULL REFERENCES guild (guild_id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL,
    name       TEXT NOT NULL,
    PRIMARY KEY (guild_id, product_id)
);

CREATE TABLE IF NOT EXISTS payment (
    guild_id    INTEGER NOT NULL REFERENCES guild (guild_id) ON DELETE CASCADE,
    payment_id  INTEGER PRIMARY KEY,     -- GlassRelay's id, unique across all stores
    user_id     INTEGER NOT NULL,        -- 0 means no buyer to show: a guest, or a payment that never completed
    product_id  INTEGER NOT NULL,
    amount      TEXT NOT NULL,           -- exactly as GlassRelay sent it
    credits     INTEGER NOT NULL,        -- for a payment marked by init: its worth at the ratio then, never paid
    paid_at     INTEGER NOT NULL,        -- unix seconds
    credited_at INTEGER NOT NULL,        -- unix seconds
    FOREIGN KEY (guild_id, product_id) REFERENCES product (guild_id, product_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS payment_guild_user ON payment (guild_id, user_id);
