# stripe: notes for on-call

Date: 2024-07-08  
Author: Mei (payments owner)  
Target audience: Platform team, SRE, and primary/secondary on-call rotation  

---

## 1. Context and Purpose

Sorrel operates four core services: `web`, `api`, `payments`, and `notifier`. Of these four, `payments` is the single service that communicates with Stripe. 

We process customer card transactions whenever appointments require upfront deposits or full prepayment. In addition to customer checkouts, `payments` issues refunds when appointments are cancelled inside a merchant's designated cancellation window, and handles the Sunday weekly payout run that disburses funds to businesses across our three active cloud regions: `ap-northeast` (Tokyo), `us-east`, and `eu-west`.

Because `payments` handles real money, operational mistakes can lead to irreversible state changes, incorrect ledger entries, or customer financial harm. This note covers the architectural boundary between Sorrel and Stripe, what failure modes look like from our dashboards, how webhooks behave over time, and what actions on-call engineers are strictly permitted—and forbidden—to take when Stripe is degraded or failing.

---

## 2. Core Operational Rules for On-Call

When on-call engineers respond to alerts involving checkout failures, refund anomalies, or webhook backlogs, keep the following hard constraints in mind:

1. **Check status.stripe.com first.**  
   `status.stripe.com` is the status page; subscribe the incident thread to it during a payments incident. When external calls fail or time out while our own application nodes are healthy, verify Stripe's upstream platform health before touching anything internally.
2. **Never change anything in the stripe dashboard during an incident.**  
   Payment settings are Mei's decision. On-call engineers have read-only visibility into operational metrics and logs. You are never permitted to rotate live API keys, alter account webhook destinations, modify payment method configurations, adjust fraud rules, or toggle capture behavior during an outage. If a credential compromise or configuration defect requires modifying our Stripe account, page Mei immediately.
3. **Disputes arrive as webhooks and are handled by Mei's team in working hours, never by on-call.**  
   A dispute webhook signifies that an end cardholder disputed a charge through their card issuer. This is normal business operations, not an operational reliability emergency. It requires review by finance and business support, never technical intervention by on-call engineers in the middle of the night.
4. **Distinguish internal latency from provider latency.**  
   The `Sorrel / payments` metrics board plots checkout latency (ours) and provider response time (theirs) side by side on the latency panel. Do not assume an elevated p95 checkout latency is an application regression until you look at the provider breakdown.
5. **No rollbacks when money has already moved.**  
   If an alert or log investigation reveals that charges, refunds, or payouts were duplicated or issued incorrectly, money has already moved. A rollback cannot pull currency back out of banking rails or card networks. The first move under the handbook is always `page owner` (Mei).

---

## 3. Webhook Delivery and Retry Architecture

Sorrel relies on Stripe's inbound webhooks for asynchronous lifecycle updates. When a customer initiates checkout on `web`, `payments` submits a charge authorization request to Stripe. Once settled, failed, or disputed, Stripe sends a cryptographically signed webhook payload back to our regional endpoints.

### 3.1 Webhook Delivery Mechanics

```
+---------------+                    +---------------------+                    +-----------------+
|               |  POST /webhooks    |  payments service   |  Mark Paid / State |                 |
| Stripe Engine | -----------------> | (4 nodes per region)| -----------------> |  api service    |
|               |   Signed Payload   |  Verifies signature |                    |                 |
+---------------+                    +---------------------+                    +-----------------+
        |                                       |
        | If 5xx / timeout                      | Writes event to
        v                                       v payments DB
 [Retry Schedule:                             [Idempotent Handler]
  Up to 3 days,
  exponential backoff]
```

Key operational characteristics of this pipeline include:

* **Stripe retries a webhook it could not deliver for up to 3 days, with growing gaps between attempts.**  
  If our ingestion endpoint returns an HTTP 5xx status, times out, or drops the connection during node maintenance or a localized database lock, Stripe queues the event and retries with an exponential backoff schedule spanning up to 72 hours.
* **Transient spikes in retries are normal.**  
  During heavy traffic windows (such as Friday evenings between 18:00 and 23:00 JST), or immediately following a regional network hiccup, Stripe may retry deliveries that took slightly longer than their timeout threshold. Seeing an uptick in retries on the `Sorrel / payments` dashboard is not an immediate catastrophe. The system is explicitly built to ingest webhooks that arrive late, out of order, or more than once.
* **Idempotency is mandatory.**  
  `payments` maintains its own dedicated database (separate from `api`). It records incoming event identifiers and evaluates idempotency keys before executing ledger actions. If Stripe delivers the exact same webhook payload three times over twelve hours, our code will acknowledge the receipt and drop the duplicate execution cleanly.

### 3.2 Handling Disputes

When a cardholder files a chargeback, Stripe dispatches a `charge.dispute.created` (or updated/closed) webhook. 

* These payloads hit our standard webhook listener and write audit rows to the `payments` database.
* **On-call engineers must never wake the payments team or attempt to respond to disputes.**  
* Disputes arrive as webhooks and are handled by Mei's team in working hours, never by on-call. 
* Do not attempt to refund the associated booking, do not attempt to contact the merchant or customer, and do not tweak dispute handling settings in the Stripe dashboard.

---

## 4. Dashboards and Metrics Reference

When investigating checkout anomalies, keep the board `Sorrel / payments` open in the metrics tool alongside the corresponding region in `Sorrel / api`.

| Dashboard Panel | What It Measures | What "Normal" Looks Like | Warning Signs |
|---|---|---|---|
| **Checkout Submissions & Outcomes** | Requests per minute split by region and status (success vs. failure). | Tracks customer booking curve (peaks 18:00–23:00 JST). Failures < 0.5 %. | Sharp drop in successes with failure rate > 2 % sustained over 3 minutes. |
| **Latency: Ours vs. Provider** | p95 checkout latency (Sorrel origin) plotted against p95 provider response time (Stripe). | Sorrel processing < 150 ms; provider response < 800 ms. | Provider curve climbs to 5,000 ms+ while Sorrel processing line remains low and flat. |
| **Charge Attempts & Timeouts** | Total calls to Stripe API and % timing out. | Timeouts < 0.1 %; responses return within 1 second. | Timeout rate climbs above 5 % sustained over 5 minutes. |
| **Refund Volume & Amounts** | Hourly count and cumulative value of refunds issued. | Spikes slightly after 23:30 JST (daily batch refund sweep). | Sudden surge in refund count or repeated identical totals at unusual hours. |
| **Webhooks Ingestion & Retries** | Received, retried, and failed events categorized by event type. | Low steady stream of retries (< 2 %); clean acknowledgments. | Sustained 5xx responses on `/webhooks`; retry rates exceeding 10 % over an hour. |
| **Validation Errors** | Pre-flight validation failures on checkout forms by input field. | Rare, steady baseline from customer typos (card number format, expiry). | Spike exceeding 1 % of all submissions, often tied to a front-end deploy on `web`. |

---

## 5. Typical Failure Shapes and Operational Responses

In accordance with the Sorrel On-Call Handbook, you have three immediate responsibilities when an alert fires: determine the severity, choose your single first move from the five actions (`roll back`, `read logs`, `check provider`, `page owner`, `no action`), and record your initial findings in the `#inc-live` incident thread.

### 5.1 Scenario A: Upstream Outage or Degradation at Stripe

* **Observed Metrics:**  
  * The `payments-provider-timeout` rule fires.
  * More than 5 % of provider calls are timing out over a 5-minute window.
  * The latency panel shows p95 provider response time spiking sharply (e.g., > 6,000 ms), while Sorrel internal execution latency remains flat.
  * Checkout failure rate rises uniformly across all three active regions (`ap-northeast`, `us-east`, `eu-west`).
* **First Move:** `check provider`
* **Execution:**
  1. Open `status.stripe.com`. Note the exact time of their earliest reported degradation and compare it to the onset on our graphs.
  2. In the `#inc-live` incident thread, paste the alert line, state the severity, and confirm that our calls are failing due to upstream provider degradation.
  3. Subscribe the incident channel to `status.stripe.com` updates.
  4. Post an update in `#inc-live`: *"Stripe is reporting degraded performance for Charges and API. Sorrel checkout failures correlate directly with provider timeout spikes. Subscribed thread to status.stripe.com. Holding off on code changes."*
  5. If the problem persists for more than 15 minutes, the incident commander rotation will coordinate public status updates on `status.sorrel.app` using our standard templates.
  6. **Do not attempt to touch settings in the Stripe dashboard.** Wait for upstream recovery. Once Stripe stabilizes, watch the latency panel return below baseline and verify that checkout success resumes.

### 5.2 Scenario B: Elevated Webhook Retries After Recovery

* **Observed Metrics:**  
  * Following an upstream incident or a brief network blip, the `payments-webhook-retry` rule fires.
  * More than 10 % of webhooks are being retried within the hour.
  * Checkout success rate on the live site is already green and customers are booking normally.
* **First Move:** `no action` (or `read logs` if retry causes are unknown)
* **Execution:**
  1. Recall that Stripe retries a webhook it could not deliver for up to 3 days, with growing gaps between attempts.
  2. Check the `Sorrel / payments` webhook delivery panel: verify that the absolute rate of delivered events is climbing and that incoming webhooks are being successfully acknowledged (HTTP 200).
  3. Confirm that no end customers are blocked from booking appointments or completing payment flows.
  4. Classify this as a P3 event. Record the line in the on-call log noting that Stripe is draining its 3-day retry backlog following the prior disruption, and monitor the queue until it flattens.

### 5.3 Scenario C: Duplicate Charges or Abnormal Financial Movements

* **Observed Metrics:**  
  * The `payments-refund-duplicate` rule fires, or support channels flag multiple reports of customers being debited twice for a single booking reference.
  * An unexpected batch of payout transfers fires unexpectedly outside the standard Sunday 23:00 JST window.
* **First Move:** `page owner`
* **Execution:**
  1. This is an immediate P1 incident regardless of whether it affects one customer or one thousand. Money has already moved wrongly.
  2. Page Mei via the paging tool schedule. Do not rely on chat pings.
  3. Include the exact alert line, state severity P1, and summarize the symptom: *"Paging Mei: duplicate card charges confirmed for booking references. Initiating owner escalation as money has already moved."*
  4. While waiting for Mei to acknowledge (within 10 minutes), open `sorrel-prod-*` and run read-only log searches on `service=payments outcome=failed` or trace specific booking IDs.
  5. **Never attempt to issue manual bulk refunds or change Stripe dashboard balance settings yourself.** Decisions regarding customer balance adjustments, merchant goodwill credits, and payment gateway configuration rest exclusively with Mei and finance leads.

### 5.4 Scenario D: Suspected Credential Exposure

* **Observed Metrics:**  
  * The `payments-secret-scan` rule fires indicating a pattern match for a live Stripe API secret key in application log output, an exception trace, or an admin chat export.
* **First Move:** `page owner`
* **Execution:**
  1. Live Stripe API keys are stored in our secure secrets manager and must never appear in `sorrel-prod-*` logs, tickets, or chat channels.
  2. Classify as P1 immediately.
  3. Page Mei. Live credential rotation can instantly break active checkout authorization across all regions if executed incorrectly; on-call engineers are explicitly forbidden from generating or rolling production provider keys in the Stripe dashboard.
  4. Document the log query or reference location internally, avoiding copying the secret string into `#inc-live`.

---

## 6. Log Investigation Runbook for Payments

When debugging `payments` issues, search the index `sorrel-prod-*` in the log search tool. Ensure you constrain the search query time window to the exact minutes surrounding the alert trigger to prevent slow cluster scans.

```
# 1. Inspect top failure reasons across regions
service=payments outcome=failed region=*

# 2. Identify slow upstream calls to Stripe (> 5 seconds)
service=payments provider_ms>5000

# 3. Trace webhook ingestion lifecycle and retries
service=payments msg="webhook" outcome=retry

# 4. Check for payload validation errors on checkout
service=payments msg="validation" field=*

# 5. Trace a specific refund execution without logging card details
service=payments msg="refund sent" ref=<ref>
```

*Data Privacy Warning:* Never paste cardholder names, PANs, or authentication keys into incident threads, chat rooms, or postmortems. Sorrel does not store raw credit card numbers; Stripe stores and processes them. Only refer to booking IDs, payment intent references, and refund IDs in internal communication.

---

## 7. Escalation and Ownership Summary

| Area / Role | Primary Contact | Secondary / Fallback | Responsibilities & Boundaries |
|---|---|---|---|
| **payments Service Owner** | Mei | Incident Commander rotation | Final authority on charges, refunds, payouts, provider configuration, dispute handling policy, and Stripe dashboard settings. |
| **API Integration & Core Engine** | Ravi | Incident Commander rotation | Manages booking states, partner integrations, database connection health, and downstream "pending payment" states. |
| **Web & Admin Portal** | Aiko | Incident Commander rotation | Manages browser checkout forms, client-side validation errors, and support admin deletion/restore flows. |
| **Platform / Infrastructure** | Kenji Sato (Platform Lead) | Sara (Platform Engineer) | Cloud networking, load balancer configuration, cross-region connectivity to Stripe endpoints. |
| **Support Lead** | Hana | Customer Support Team | Customer communication, merchant messaging, gathering report volumes during checkout disruptions. |
| **Primary On-Call Engineer** | Weekly Rotation | Assigned Secondary | First responder: triage severity, execute first move, subscribe threads to provider status, record on-call log entries. |

### Summary Checklist for payments Incidents

- [ ] Has an alert fired? Note the exact time, duration, and whether customer reports exist.
- [ ] Is Stripe itself failing? Check `status.stripe.com` and verify via the provider latency panel.
- [ ] If Stripe is degraded, subscribe the `#inc-live` incident thread to `status.stripe.com`.
- [ ] Keep hands off the Stripe dashboard. Do not toggle payment options, webhooks, or dispute configs.
- [ ] If money moved incorrectly, secrets leaked, or duplicate refunds occurred, page Mei immediately.
- [ ] Treat dispute webhooks as business-as-usual for working hours; leave them for Mei's team.
- [ ] Record the incident outcome and your first move in the on-call log after stabilization.
