import sqlite3
from contextlib import contextmanager
from pathlib import Path


class RuleError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status
        super().__init__(message)


def connect(path):
    db = sqlite3.connect(path, timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    return db


def migrate(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript((Path(__file__).parent.parent / 'migrations/001_initial.sql').read_text())


@contextmanager
def transaction(db):
    db.execute('BEGIN IMMEDIATE')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def now(db):
    # Read time AFTER acquiring the writer lock: queued requests cannot use stale time.
    return db.execute("SELECT unixepoch('now')").fetchone()[0]


def audit(db, actor, action, entity, entity_id, detail):
    db.execute('INSERT INTO audit(actor_id,action,entity,entity_id,detail,created_at) VALUES(?,?,?,?,?,?)',
               (actor, action, entity, entity_id, detail, now(db)))


def active_user(db, user_id):
    user = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not user or user['suspended']:
        raise RuleError('This account is unavailable.', 403)
    return user


def top_bid(db, auction_id):
    return db.execute('SELECT * FROM bids WHERE auction_id=? ORDER BY amount DESC,id LIMIT 1', (auction_id,)).fetchone()


def settle_locked(db, auction, timestamp):
    if auction['state'] == 'open' and timestamp >= auction['closes_at']:
        bid = top_bid(db, auction['id'])
        winner = bid['user_id'] if bid else None
        db.execute("UPDATE auctions SET state='closed',winner_id=?,closed_at=? WHERE id=?", (winner, auction['closes_at'], auction['id']))
        audit(db, None, 'auction_closed', 'auction', auction['id'], f'Winner user ID: {winner}; scheduled close {auction["closes_at"]}')
        return True
    return False


def close_due(db):
    with transaction(db):
        timestamp = now(db)
        for auction in db.execute("SELECT * FROM auctions WHERE state='open' AND closes_at<=?", (timestamp,)).fetchall():
            settle_locked(db, auction, timestamp)


def place_bid(db, user_id, auction_id, amount, request_key):
    if type(amount) is not int or not 0 < amount <= 1_000_000_000_000:
        raise RuleError('Enter a whole MNT amount within the supported limit.', 400)
    if not isinstance(request_key, str) or not 16 <= len(request_key) <= 100:
        raise RuleError('A valid request key is required.', 400)
    failure = None
    result = None
    with transaction(db):
        user = active_user(db, user_id)
        existing = db.execute('SELECT * FROM bids WHERE user_id=? AND request_key=?', (user_id, request_key)).fetchone()
        if existing:
            if existing['auction_id'] != auction_id or existing['amount'] != amount:
                raise RuleError('This request key was already used for a different bid.')
            return dict(existing), True
        a = db.execute('SELECT * FROM auctions WHERE id=?', (auction_id,)).fetchone()
        if not a:
            raise RuleError('Auction not found.', 404)
        timestamp = now(db)
        if settle_locked(db, a, timestamp):
            failure = RuleError('Bidding has closed. Refresh to see the result.')
        elif a['state'] != 'open':
            failure = RuleError('This auction is not open for bids.')
        else:
            shop = db.execute('SELECT * FROM shops WHERE id=?', (a['shop_id'],)).fetchone()
            if shop['status'] != 'approved':
                raise RuleError('The seller is suspended.', 403)
            if user['shop_id'] == a['shop_id'] or user['role'] != 'buyer':
                raise RuleError('Only independent buyer accounts may bid. Seller and operator accounts cannot bid.', 403)
            current = top_bid(db, auction_id)
            minimum = current['amount'] + a['increment'] if current else a['start_price']
            if amount < minimum:
                raise RuleError(f'The price changed or this bid is too low. Minimum now: {minimum:,} MNT.')
            cursor = db.execute('INSERT INTO bids(auction_id,user_id,amount,created_at,request_key) VALUES(?,?,?,?,?)',
                                (auction_id, user_id, amount, timestamp, request_key))
            deadline = a['closes_at']
            if a['soft_close'] and deadline - timestamp <= a['soft_close']:
                deadline = timestamp + a['soft_close']
                db.execute('UPDATE auctions SET closes_at=? WHERE id=?', (deadline, auction_id))
            audit(db, user_id, 'bid_accepted', 'auction', auction_id, f'Bid {cursor.lastrowid}; amount {amount}; close {deadline}')
            result = dict(db.execute('SELECT * FROM bids WHERE id=?', (cursor.lastrowid,)).fetchone())
    if failure:
        raise failure
    return result, False


def seller_access(db, user_id, auction_id):
    user = active_user(db, user_id)
    a = db.execute('SELECT * FROM auctions WHERE id=?', (auction_id,)).fetchone()
    if not a or user['role'] != 'seller' or user['shop_id'] != a['shop_id']:
        raise RuleError('Listing not available to this seller.', 403)
    shop = db.execute('SELECT status FROM shops WHERE id=?', (a['shop_id'],)).fetchone()
    if shop['status'] != 'approved':
        raise RuleError('This shop is suspended.', 403)
    return a


def rate_limit(db, bucket, limit, window):
    with transaction(db):
        timestamp = now(db)
        db.execute('DELETE FROM rate_limits WHERE resets_at<=?', (timestamp,))
        db.execute('INSERT INTO rate_limits VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1', (bucket, timestamp + window))
        return db.execute('SELECT count FROM rate_limits WHERE bucket=?', (bucket,)).fetchone()[0] <= limit
