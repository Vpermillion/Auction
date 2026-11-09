# Verification — 9 November 2026 (Asia/Ulaanbaatar)

## Passed locally

- `python -m unittest discover -s tests -v`: **30 tests passed** against temporary SQLite databases, including separate connections and real concurrent threads.
- `python -m compileall -q auction`: passed.
- `node --check static/app.js`: passed on Node 22.17.0.
- `python -m pip check`: no broken dependencies (Flask 3.1.3, Waitress 3.0.2).
- `git diff --cached --check`: no whitespace errors.

The tests cover same-price concurrency; concurrent duplicate requests; payload/key mismatch; replay after closing; exact and past deadline rejection; a bid blocked on a writer lock until its deadline; a bid/closing race; repeated and disabled soft close; highest-bid/no-bid winner selection; whole MNT/minimum checks; role, suspended-account and shop enforcement; append-only bids/audit; CSRF; cross-shop read/edit/cancel/status/relist/export; registration privilege isolation; private public histories; complete seller-draft → publish → buyer bid → close → manual payment → fulfillment; cancellation/relisting history; overdue unpaid review; operator onboarding rollback; reports/review/suspension; rate limits across connections; response headers; language selection; disabled payment provider; rejected uploads; malformed JSON; and seller outcome submission without JavaScript.

## Observed in the in-app browser

The app was served locally with Waitress, bound to `127.0.0.1:5055`. Browser interaction used real rendered forms and server persistence, not synthetic frontend acceptance.

1. Loaded and visually inspected the landing page and signed in as the demo seller.
2. Created “Browser journey · synthetic pendant”, saved its draft, changed the final deadline and disabled soft close for a short test, then published.
3. Signed out and in as the demo buyer. Read the listing and submitted its 100,000 MNT starting bid. The rendered page confirmed acceptance and displayed the public alias in bid history. Browser console had no captured warning/error at that point.
4. After the actual published deadline elapsed, visited My bids. Server closure selected that buyer and displayed winner instructions and the 48-hour payment deadline.
5. Signed in as the seller. Recorded a **synthetic manual** payment confirmation, then collection. The dashboard showed `paid` and `collected`; no money or actual item changed hands.
6. Checked a 390×844 viewport: no horizontal overflow and condition/evidence content remained visible. Switched MN/EN and observed translated shared navigation and demo notices. Reset the viewport afterwards.

Screenshots of the landing, winner account and seller result are included with the handoff outputs, not in the source repository. The preview database includes that extra browser-test lot; a fresh seed creates the four documented initial lots. No real personal data or payment credentials were used.

## Verification limits

This is not penetration testing, formal accessibility certification, a high-volume/load test or proof of shill-bidding detection. A full provider integration cannot be tested because none is configured. Network interruption recovery is implemented through stored idempotency keys and API duplicate tests; browser offline/timeout fault injection was not performed. No real-money event, real seller onboarding, legal review, full Mongolian translation, email delivery or production deployment was attempted. A CI workflow is included; remote CI status must be distinguished from these local results.
