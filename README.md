# Auction House — a working SaaS pilot

A phone-friendly, server-backed auction pilot for established shops in Mongolia. **Synthetic demo only; no public deployment or live payment integration.** Built from an empty repository on `codex/auction-pilot` with Flask, server-rendered Jinja and SQLite to minimize cost and operational complexity.

## Run locally (Python 3.11+)

PowerShell, from this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app auction.app:create_app init-db
.\.venv\Scripts\python.exe -m flask --app auction.app:create_app seed-demo
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:5055 --call auction.app:create_app
```

Open [http://127.0.0.1:5055](http://127.0.0.1:5055). Linux/macOS: use `.venv/bin/python` and `.venv/bin/waitress-serve` instead. Stop with Ctrl+C. No Node build or paid account is needed.

The environment variables in `.env.example` must be exported by your shell; there is no automatic dotenv loading. `AUCTION_DB` defaults to ignored `instance/auction.sqlite3`. A random session secret is created once in ignored `instance/session-secret` if `APP_SECRET` is absent; use a secret manager/environment injection for a hosted preview. Keep the same secret across restarts. `COOKIE_SECURE=0` is for loopback HTTP only. No secrets or user database are tracked.

`init-db` is repeatable. `seed-demo` refuses an occupied users table; use a new `AUCTION_DB` path and repeat both commands for a clean demo. Seed deadlines are relative to creation: 6, 24 and 36 hours ahead, plus one completed lot to show winner instructions. This source includes bundled stock photos, credited in `docs/ASSETS.md`; they illustrate synthetic listings and are not item evidence.

## Demonstrate the journey

All demo account passwords are `Pilot-demo-2026!`:

| Role | Email | Try |
| --- | --- | --- |
| Buyer | `buyer@example.test` | Bid, see My bids, see seeded winner instructions |
| Second buyer | `buyer2@example.test` | Outbid the first buyer; compare account outcomes |
| Seller | `seller@example.test` | Manage Altan Studio, create/publish a lot, review winner, record payment/fulfillment, export CSV |
| Other seller | `other-seller@example.test` | Manage Nomad Objects, confirm shop isolation |
| Operator | `operator@example.test` | Onboard seller, review inquiries/reports, suspend and inspect audit |

1. Visit the landing page, then the Altan Studio shop and lot 001. Read condition, seller evidence, frozen policies and closing rules.
2. Sign in as seller. Create a draft with a near-future Ulaanbaatar closing time (at least a minute ahead), save and publish. All material terms lock at publication. Set soft close to 120 seconds to try extensions, or 0 for a quick closing demonstration. Seconds are not entered in the minute-precision date picker.
3. Sign out; sign in as buyer or register a synthetic buyer with a 12+ character password. Bid at the minimum. Open a second session/account to outbid. Prices poll every five seconds; the server rejects stale bids and decides all deadlines.
4. After the final deadline, visit My bids. The winner sees the frozen seller instructions and payment deadline. A seeded completed lot is available immediately on the first buyer account.
5. Sign in as seller. Review the private winner email. Record a seller-confirmed payment and then collection/delivery with notes. CSV exports include every accepted bid for that shop. The records are manual, not verified by a payment provider.
6. Submit a report from a listing as a signed-in buyer. Operator can review it, record a resolution or suspend a listing/shop/account with a reason. Inquiry form submissions are stored for the operator; no email is sent.

The MN/EN switch translates shared labels and key bidding disclosures. Longer English policies, operational text, status/error messages and seller descriptions still require translation. MNT formatting and Asia/Ulaanbaatar (UTC+8) display are implemented; all stored times are Unix UTC seconds.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q auction
node --check static/app.js
```

Tests use isolated temporary databases and real SQLite connections/threads. They cover simultaneous prices, duplicate requests, exact closing boundary, extensions, closing winner/no-winner, immutable bids/audit, CSRF, private aliases, registration, authorization, cross-shop access/export, seller publishing, manual outcome recording, overdue review/relisting, onboarding rollback, reports and suspension. See [verification notes](docs/VERIFICATION.md) for actual results and browser checks.

Optional materialization of unattended due lots (no daemon is needed for safe bid acceptance):

```powershell
.\.venv\Scripts\python.exe -m flask --app auction.app:create_app close-auctions
```

Closing occurs transactionally on relevant requests too. For immediate unattended recording, schedule that command externally. No background email or notification service is installed.

## Operating scope and limitations

One Waitress process with multiple threads and SQLite on persistent local disk is the intended small-pilot setup. `BEGIN IMMEDIATE` serializes writes, including bid and close transactions. This is not a multi-host/high-volume topology; database busy errors ask the browser to retry the same request. Browser uncertainty preserves a pending request in session storage until confirmed. Do not clear storage and blindly place another bid after an unknown network result.

No real item/photo/document uploads, email verification/recovery, MFA, automated seller invoices/subscriptions, background notifications or live provider verification ship. The disabled payment adapter raises errors. `DEMO_MODE=0` only hides shared credentials and blocks seeding; it is **not a production switch**. Existing known demo accounts must be removed/replaced before a restricted hosted preview. The product remains labeled as a preview in either mode.

Before a real-money launch, resolve [launch prerequisites](docs/LAUNCH_CHECKLIST.md): Mongolian legal review, pricing and seller agreements, actual item evidence, privacy/retention, payment arrangements, account hardening, translation, security review, reliable hosting/backups and event support. Controls do not eliminate shill bidding or guarantee authenticity.

- [Business hypothesis and paid-pilot validation](docs/BUSINESS_MODEL.md)
- [Architecture, state rules and official references](docs/ARCHITECTURE.md)
- [Launch prerequisites](docs/LAUNCH_CHECKLIST.md)

No claims of customers, partners, revenue, market validation or legal approval are made.
