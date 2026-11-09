PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);
CREATE TABLE IF NOT EXISTS shops (
 id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 address TEXT NOT NULL, contact TEXT NOT NULL, terms TEXT NOT NULL,
 instructions TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'approved',
 identity_note TEXT NOT NULL DEFAULT 'Seller identity review pending'
);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
 alias TEXT UNIQUE NOT NULL, role TEXT NOT NULL CHECK(role IN ('buyer','seller','operator')),
 shop_id INTEGER REFERENCES shops(id), suspended INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS auctions (
 id INTEGER PRIMARY KEY, shop_id INTEGER NOT NULL REFERENCES shops(id),
 title TEXT NOT NULL, description TEXT NOT NULL, condition TEXT NOT NULL,
 evidence TEXT NOT NULL, image TEXT NOT NULL DEFAULT 'pendant',
 start_price INTEGER NOT NULL CHECK(start_price>0), increment INTEGER NOT NULL CHECK(increment>0),
 closes_at INTEGER NOT NULL, soft_close INTEGER NOT NULL DEFAULT 120 CHECK(soft_close BETWEEN 0 AND 600),
 payment_hours INTEGER NOT NULL DEFAULT 48 CHECK(payment_hours BETWEEN 1 AND 168),
 fees TEXT NOT NULL DEFAULT 'No buyer platform fee. Pickup is free; delivery must be agreed with seller.',
 seller_terms TEXT NOT NULL, payment_instructions TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','open','closed','cancelled','suspended')),
 winner_id INTEGER REFERENCES users(id), closed_at INTEGER,
 payment TEXT NOT NULL DEFAULT 'awaiting' CHECK(payment IN ('awaiting','paid','unpaid_review')),
 fulfillment TEXT NOT NULL DEFAULT 'pending' CHECK(fulfillment IN ('pending','collected','delivered')),
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bids (
 id INTEGER PRIMARY KEY, auction_id INTEGER NOT NULL REFERENCES auctions(id),
 user_id INTEGER NOT NULL REFERENCES users(id), amount INTEGER NOT NULL CHECK(amount>0),
 created_at INTEGER NOT NULL, request_key TEXT NOT NULL,
 UNIQUE(user_id, request_key)
);
CREATE INDEX IF NOT EXISTS bids_auction ON bids(auction_id,amount DESC,id);
CREATE TRIGGER IF NOT EXISTS immutable_bid_update BEFORE UPDATE ON bids BEGIN SELECT RAISE(ABORT,'Accepted bids are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_bid_delete BEFORE DELETE ON bids BEGIN SELECT RAISE(ABORT,'Accepted bids are immutable'); END;
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), action TEXT NOT NULL,
 entity TEXT NOT NULL, entity_id INTEGER, detail TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_audit_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'Audit is append only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_audit_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'Audit is append only'); END;
CREATE TABLE IF NOT EXISTS reports (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 auction_id INTEGER NOT NULL REFERENCES auctions(id), reason TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open', resolution TEXT, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS inquiries (
 id INTEGER PRIMARY KEY, email TEXT NOT NULL, message TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (
 bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, resets_at INTEGER NOT NULL
);
