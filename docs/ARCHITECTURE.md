# Design and reliability notes

The source repository was empty. This uses Python 3.11+, Flask/Jinja, Waitress and one SQLite database. Server rendering provides usable forms without JavaScript; a small script adds five-second state polling and idempotent retry. No frontend build, cloud account or paid dependency is required. One host plus durable local disk is the intended pilot topology.

## Database authority

`migrations/001_initial.sql` is repeatable and records schema version 1. There are no prior data migrations. The seed command refuses a nonempty users table and runs atomically. All amounts are integer MNT; there are no floats, wallet balances or provider credits.

Each bid runs `BEGIN IMMEDIATE` on its own connection. SQLite serializes writers; the database clock is read only after obtaining that lock. The transaction checks the active account, idempotency key/payload, shop status, auction status, final deadline and current highest accepted amount, then inserts the bid, updates any extension and appends an audit event before commit. Requests at `timestamp >= closes_at` cannot bid. Database time has one-second resolution. A busy database waits up to 15 seconds; a failure returns a retryable 503. This is appropriate for a small pilot, not a claim of unlimited throughput.

The bid key is unique per user, across auctions. Replaying the same payload returns the original bid even after closing; reusing the key for another payload is rejected. Browser uncertain requests are saved in per-tab session storage. On interruption, the browser blocks a new bid until the original request is retried. Reloading can recover it. Without JS, the form contains a stable key, so resubmitting the original POST is safe; a freshly loaded form has a new key. Clearing browser storage loses automatic retry recovery; inspect My bids before attempting another bid.

Soft close is a rolling interval: a valid bid inside the final N seconds sets close to server time + N, including repeatedly. N=0 disables extension. There is no undocumented extension cap. First accepted bid may equal the start price; later bids must be at least current + increment (not necessarily an exact multiple). Highest accepted bid wins. Tied prices cannot be accepted concurrently.

`close_due` runs on public auction lists/details/API and account/dashboard requests, or via CLI. Closing shares the writer lock with bids and is idempotent. It records the final deadline as `closed_at`, and selects the highest accepted bid. An idle process does not materialize a closing row until a relevant request/CLI call, but late bids are still rejected and settle the due lot before returning a conflict. No winner notification is automatic.

## States and interventions

Draft → open (all terms freeze immediately) → closed. Draft/open can instead become cancelled by seller with a reason, or suspended by operator. Stopped lots never reopen. Shop suspension settles already-due lots and suspends its remaining open/draft lots. Accepted bids and audit rows have update/delete rejection triggers; admin code never rewrites either. Direct database administrators remain able to alter schema/data, so filesystem permissions/backups matter.

Only a documented cancelled, unsold or overdue unpaid-review lot can be copied to a new draft. The new lot has no old bids and a new closing time. Closed awards are retained. No automatic underbidder promotion or penalty exists. Seller can record manual payment then fulfillment; overdue unpaid review cannot overwrite paid status. Other status corrections and appeals need operator review and an agreed operational procedure before live use.

## Security and privacy boundaries

Password hashes use Werkzeug's default scrypt; sessions are signed, HttpOnly, SameSite=Lax and expire after eight hours. Every state-changing route requires a session CSRF token, including anonymous auth/inquiry forms. Content is escaped by Jinja; CSP permits only same-origin assets and denies framing. Request bodies are limited to 32 KB and file uploads are rejected. SQLite stores basic cross-process rate-limit counters using short-lived keyed IP hashes. Proxy headers are not implicitly trusted. Real deployment still requires infrastructure limits, TLS, secure cookies, hardened accounts and review.

All seller mutation/export queries are server-scoped to their shop. Seller and operator accounts cannot bid anywhere. Winning buyer email is shared only with the relevant seller; public history exposes random aliases, amounts and times. Operator sees private accounts/reports. Public aliases are pseudonyms and can be correlated; this is not anonymity. Evidence is text only, with no sensitive identity document storage.

`DEMO_MODE=1` permits seed and shows shared credentials. `DEMO_MODE=0` hides them and refuses seed; it does **not** remove existing demo accounts or make the app live-ready. The site remains preview-labeled. Payment adapter is disabled in every mode. There is no hidden QPay endpoint or fake verified-payment status.

## Official references consulted

- [SQLite transactions](https://www.sqlite.org/lang_transaction.html): `BEGIN IMMEDIATE`, serialized writers and busy handling informed the locking design.
- [Flask security considerations](https://flask.palletsprojects.com/en/stable/web-security/): request limits, output escaping, CSRF, cookie and response-header protections.

Implementation choices and business assumptions are documented above; these references do not establish Mongolian legal compliance.
