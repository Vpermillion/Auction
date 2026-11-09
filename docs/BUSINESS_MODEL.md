# Auction House pilot business hypothesis

**Customer.** Established shops and professional sellers in Mongolia with their own inventory, premises, audience and ability to resolve customer issues. Jewelry/accessories are an example segment, not evidence of demand. Altan Studio and Nomad Objects are imaginary demo shops.

**Value.** A branded shop page, explicit auction terms, durable bids, winner records, manual fulfillment tracking and exports. The seller brings the audience and remains the buyer's item counterparty. The first milestone is one useful auction for one real seller, followed by willingness to pay again.

**Revenue options.** Agree one simple per-event fee or a subscription in writing before a pilot. The amount is undecided; MNT 100,000/month was illustrative, not the price. A 3% commission is not a requirement. Manual invoices and onboarding are enough. Do not add a payment gateway or commission accounting until the model earns that complexity.

**Division of work.** Seller: inventory, ownership/authenticity statements, condition descriptions, evidence, relevant certificates, buyer communications, direct payment, pickup/delivery and remedies. Platform: software, bid acceptance/closing, access control, privacy, records, operator review and technical support. This separation does not remove the platform's own legal duties. Seller identity review must never imply that every item is authenticated.

**Operating workload.** Founder recruits and reviews the seller, agrees rules and price, trains the seller, helps prepare listings, monitors the event close, reviews reports, reconciles seller-reported outcomes and conducts a post-event interview. Seller handles item questions and fulfillment. Track founder support minutes per event, number of reports, manual corrections, unpaid outcomes and seller time spent. Do not assume a small team is sufficient until these measurements exist.

**Costs.** This implementation has no paid service dependency: Flask, Waitress and SQLite run on one machine. Actual ongoing costs will include suitable hosting, persistent disk, backups, domain/TLS, incident monitoring, legal/translation work, founder support time and any future provider fees. These costs are unquoted and unvalidated. Calculate contribution per event as fee minus cash operating costs and the measured cost of support time. Do not assume free hosting is durable storage.

**Assumptions to test.** Sellers can attract bidders without paid platform acquisition; timed auctions suit their stock; buyers understand the rules; seller claims are sufficient for the chosen items or can be supported by appropriate evidence; manual direct payment is manageable; sellers will pay enough to cover support. Controls do not establish buyer identity or reliably detect related-account/shill bidding. No partnerships, revenue, customer demand or legal approval are claimed.

## Paid-pilot validation

1. Interview 3–5 candidate shops about current sales, audience reach, item questions, payment failures and willingness to run an event. Record evidence and objections, not just compliments.
2. Choose one seller with a suitable small collection and a reachable existing audience. Agree the event scope, seller duties, support window, refund/cancellation process and an actual pilot fee. Resolve the launch checklist before accepting real money or real buyer data.
3. Dry-run the whole event with synthetic accounts: concurrent bids, deadline extension, reports, winner instructions, manual payment records and export. Rehearse seller/operator recovery and backup restore.
4. In an approved paid event, measure invited visitors, registrations, unique bidders, accepted bids, sold/unsold lots, unpaid winners, completed handovers, report volume, seller effort and founder support time. Describe results with actual denominators; avoid invented targets presented as industry facts.
5. Interview seller and buyers. Ask the seller to pay for a second event or subscription at an agreed price. Repeat paid use, manageable support and positive contribution are stronger signals than demo praise or a single signup. If the seller declines, document why and change the offer or stop.

**Decision gate.** Before the first real event, choose explicit thresholds with the seller for useful participation, acceptable support load and repeat willingness to pay. No thresholds, prices or market size are assumed proven in this repository.
