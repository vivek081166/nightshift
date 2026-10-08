# stripe: API version upgrade notes (2026)

Date: 2026-08-03  
Owner: Leo (payments)

This note documents the stripe API version upgrade completed for the payments service during July 2026. It records the operational background, verification phases, runtime compatibility windows, and credential isolation boundaries relevant to SRE and on-call engineers.

---

## 1. Context and Scope

payments is the sole Sorrel service interfacing directly with stripe. It handles charge creation during checkout, issuing customer refunds, processing asynchronous settlement webhooks, and distributing weekly automated payouts to businesses.

Every payment request, refund operation, and inbound webhook payload carries expectations anchored to stripe API versioning schemas. Because stripe version pinning dictates parameter naming, nested response dictionaries, and webhook serialization, upgrading the target version requires strict validation against both our database schema and downstream notification guarantees for api.

The migration to the new stripe API version was executed in production on 2026-07-14 following a two-week validation cycle in stripe's test mode environment.

### 1.1 Affected Components

| Service Subsystem | Stripe Interaction | Impact of Upgrade |
|---|---|---|
| Checkout Controller | Charges (`/v1/charges`, `/v1/payment_intents`) | Updated error parameter mappings and idempotency headers |
| Refund Processor | Refunds (`/v1/refunds`) | Strict refund reason enum handling |
| Inbound Webhook Listener | Signed event ingestion (`/webhook/stripe`) | Normalization of mutated event structures |
| Weekly Payout Worker | Payouts (`/v1/transfers`, `/v1/payouts`) | Updated metadata structure for banking rails |

---

## 2. Testing and Production Rollout Timeline

To prevent regression across regional deployments (ap-northeast, us-east, eu-west), changes were validated incrementally across staging, shadow ingestion, and production worker pools.

```
+-----------------------------------------------------------------------------------+
| 2026-06-30 to 2026-07-13: Validation in stripe test mode                          |
| - Synthetic booking deposits & full payments tested across Japanese & global cards |
| - Staging test fixtures verified against webhook parser dual-read layer            |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 2026-07-14: Production cutover (08:30 JST)                                        |
| - payments deployed with updated client library bindings                          |
| - Webhook ingestion verified against live signing secrets in ap-northeast-1       |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| Present through 2026-12-31: Dual-shape webhook support window                     |
| - Tolerates legacy field structures during provider draining and retry cycles     |
+-----------------------------------------------------------------------------------+
```

### 2.1 Test Mode Qualification (2026-06-30 to 2026-07-13)

payments moved to a newer stripe API version on 2026-07-14 after testing in stripe's test mode for two weeks.

During the test window, synthetic booking deposits and full balance charges were run against stripe test fixtures simulating domestic credit cards in ap-northeast as well as international cards in us-east and eu-west. Testing focused specifically on:

- Idempotency key stability across repeated checkout submissions.
- Safe serialization of currency rounding for deposits at salons and clinics.
- Response header parsing under simulated slow network conditions (verifying timeout limits before hitting downstream timeouts).
- Webhook signature validation and payload ingestion under varied retry delays.

Leo led the test mode implementation with review from Mei. Verification completed on 2026-07-13 with zero dropped events in staging.

### 2.2 Production Cutover (2026-07-14)

Production traffic was cut over on Tuesday, 2026-07-14 during the scheduled low-volume change window. 

Prior to cutover, database migration compatibility was checked to ensure backward compatibility for one release. In a past deploy, payments was rolled back cleanly when an operational defect occurred, and maintaining schema compatibility ensures that deploy safety invariants remain intact.

Following the rollout:
- Provider response latency held steady on the "Sorrel / payments" dashboard.
- p95 checkout latency and p95 provider response time tracked within baseline thresholds (<1.2 s provider side; checkout overall <1.8 s).
- Outbound charge attempts across Tokyo (ap-northeast-1), us-east-1, and eu-west-1 executed with expected 2xx responses from status.stripe.com endpoints.

---

## 3. Webhook Compatibility and Field Schema Dual-Shape

The upgrade changed several JSON attributes emitted by stripe webhook workers. Most notably, one webhook event type changed its field names; the webhook handler accepts both shapes until 2026-12-31.

Because webhook events can arrive late, out of order, or repeated, payments preserves ingestion resilience by maintaining a schema adapter pattern.

```
                    Inbound stripe Webhook
                               |
                               v
               [ Signature Verification (HMAC) ]
                               |
                               v
               [ Event Type Router: payments ]
                               |
               +---------------+---------------+
               |                               |
        (Standard Events)             (Mutated Event Type)
               |                               |
               |                               v
               |                    [ Adapter Decodes Payload ]
               |                    | - Legacy field names?   |
               |                    | - New field names?      |
               |                    +-------------+-----------+
               |                                  |
               +---------------+------------------+
                               |
                               v
                 [ Canonical Internal Event Model ]
                               |
                               v
                 [ Update Booking Payment State ]
                               |
                               v
                     [ Acknowledge 200 OK ]
```

### 3.1 Field Mapping Details

In the mutated event, the provider transitioned nested resource identification and dispute/charge settlement linkage:

- Legacy payload structures passed top-level identifiers and nested billing reference nodes under `source_data` and `charge_reference`.
- The new schema flattens metadata attributes, moving transaction tracking into `payment_intent_reference` and renaming `settlement_details` sub-objects.

The payments ingestion layer normalizes both payloads into an internal immutable model:

```json
// Example: Normalized payload handling logic in payments worker
{
  "reference_id": payload.payment_intent_reference || payload.charge_reference || null,
  "settlement_status": payload.settlement_state || payload.settlement_details?.status || "pending",
  "occurred_at": payload.created_utc || payload.created
}
```

### 3.2 Dual-Shape Operational Deadlines

- **Active Window:** 2026-07-14 through 2026-12-31.
- **Deprecation Date:** 2027-01-01 00:00:00 JST.
- **Monitoring Strategy:** The adapter logs an internal metric whenever legacy fields are parsed (`payments.stripe.webhook.legacy_shape_consumed`). A daily count is surfaced on the payments telemetry dashboard.
- **Retirement Task:** Leo and Mei will remove the fallback parser branch in early January 2027 once historical retries and queued settlement replays from stripe have fully cleared.

---

## 4. Key Management and Credential Isolation

Payments operations rely strictly on separation between sandbox environments and production funds. At Sorrel, API key handling follows rigid security boundaries.

Live keys are only in the secrets manager; test keys are in the staging config and never work against live accounts. Any key seen outside the secrets manager is treated as exposed and goes to Mei.

### 4.1 Boundary Matrix

| Environment | Key Type | Storage Location | Permitted Access | Real Money Movement |
|---|---|---|---|---|
| Production | Live Secret (`sk_live_*`) | Secrets Manager only | payments production nodes via runtime injection | Yes (Charges, Refunds, Payouts) |
| Production | Live Webhook Secret (`whsec_*`) | Secrets Manager only | payments production nodes via runtime injection | No (Validation only) |
| Staging / QA | Test Secret (`sk_test_*`) | Staging Config repository | payments staging instances, local development mocks | No (Simulated cards only) |
| Staging / QA | Test Webhook Secret (`whsec_test_*`) | Staging Config repository | payments staging instances | No (Simulated payloads only) |

### 4.2 Security Rules for On-Call and SRE

1. **Test Key Blast Radius:** Test keys configured in staging repositories cannot authenticate against live accounts or manipulate production bookings. They cannot interact with the cardholder network or settle real merchant funds.
2. **Zero Plaintext Secrets:** Live API keys and webhook signing secrets are injected into payments memory strictly at container initialization. They must never appear in:
   - Git commits or branch configs.
   - Deploy environment overrides.
   - Continuous integration scripts or pipeline output.
   - Application logs (`service=payments`).
   - Incident channels or tickets.
3. **Log Sanitization:** Application-level filters redact sensitive headers (`Authorization: Bearer ...`) and cardholder details. Live credential fragments match an automated scanning rule across the `sorrel-prod-*` index.

---

## 5. Failure Modes and On-Call Diagnostics

When handling payments alerts, engineers must follow the handbook’s five actions (roll back, read logs, check provider, page owner, no action) based on the alert line.

### 5.1 Diagnosis Flowchart for Payments Alerts

```
Alert fires: payments-checkout, payments-latency, or payments-provider-timeout
                                  |
                                  v
             Does the alert explicitly point at stripe?
           (provider timeout, vendor 5xx, status page degraded)
                                  |
                 +----------------+----------------+
                 | YES                             | NO
                 v                                 v
        [ check provider ]                Did payments deploy
    - Check status.stripe.com             within last 30 minutes?
    - Check latency split on board                 |
    - Confirm if theirs or ours           +--------+--------+
                                          | YES             | NO
                                          v                 v
                                   [ roll back ]      [ read logs ]
                                 - Undo deploy      - Query sorrel-prod-*
                                 - Restore clean    - Search errors & timeouts
                                   state            - Check failure codes
```

### 5.2 Common Failure Shapes and Actions

#### Case A: Provider Latency or Degraded Availability
- **Symptom:** Checkouts slow down or fail. On "Sorrel / payments", p95 checkout latency is elevated, but p95 provider response time matches the surge. The alert references provider timeouts.
- **First Move:** `check provider`
- **Actions:**
  1. Open status.stripe.com and inspect charge API latency.
  2. If an incident is posted or provider response times are spiking globally, paste the status page link and current timestamp into the `#inc-live` incident thread.
  3. Subscribe the incident channel to status.stripe.com updates.
  4. Do not alter local payment code, timeouts, or webhook configurations. Do not switch payment settings during a provider incident; that decision is reserved exclusively for Mei.

#### Case B: Ingestion / Validation Spike Following Internal Deploy
- **Symptom:** Validation errors or checkout failure rates spike immediately (e.g., within 10 minutes) following a release of payments, while status.stripe.com reports normal operations.
- **First Move:** `roll back`
- **Actions:**
  1. Determine the deploy age from the alert line. If recent (<30 mins) and directly driving the failure rate, execute a rollback to the previous release.
  2. Verify that checkout success recovers on the "Sorrel / payments" board.
  3. Note both the failing and active release identifiers in `#inc-live`.

#### Case C: Webhook Retries and Out-of-Order Deliveries
- **Symptom:** `payments-webhook-retry` alert fires indicating more than 10 % of webhooks are being retried within the hour.
- **First Move:** `no action` (or `read logs` if unclassified)
- **Actions:**
  1. Check the webhook telemetry panel on the payments board.
  2. Webhook retries are normal behaviour during busy operational windows (e.g., Friday evenings between 18:00 and 23:00 JST). stripe guarantees delivery by retrying until an HTTP 200 acknowledgment is received.
  3. If checkouts are clearing cleanly, bookings are transitioning properly, and no customer complaints are logged, record the observation in the on-call log as a P3 and monitor. If delivery completely halts, read logs (`service=payments msg="webhook" outcome=retry`).

#### Case D: Discrepancy in Settlement, Duplicate Charges, or Refunds
- **Symptom:** Duplicate refund references submitted or charges counted more than once.
- **First Move:** `page owner`
- **Actions:**
  1. Money has already moved wrongly. Irreversible financial actions cannot be fixed by on-call alone.
  2. Page Mei immediately via the paging tool.
  3. Support Mei in establishing timeline data from `service=payments msg="refund sent"` searches without attempting manual reversals.

#### Case E: Live Key Exposure
- **Symptom:** The log scanner trips or an engineer encounters a live provider key (`sk_live_*`) in log aggregation, an error trace, chat, or a ticket.
- **First Move:** `page owner`
- **Actions:**
  1. Live keys seen outside the secrets manager must be assumed compromised.
  2. Rotating a live production stripe key breaks active transaction flows and requires owner coordination. Never rotate a production credential yourself.
  3. Page Mei instantly. Do not paste the key, commit link, or log line into public chat; provide only the log search URL or reference ID.

---

## 6. Verification and Reference Checklist

For ongoing reference during shifts, verify dashboard metrics and health indicators via standard tooling:

### 6.1 Telemetry Indicators

- **Dashboard:** "Sorrel / Services" -> "Sorrel / payments"
- **Key Panels:**
  - *Checkout submissions, successes and failures per minute, by region*
  - *Charge attempts, outcomes, and time to provider response*
  - *p95 checkout latency (ours) and p95 provider response time (theirs)*
  - *Refunds issued per hour, count and total amount*
  - *Webhooks received, retried, failed, by event type*
  - *Webhook legacy vs. new shape decoding rate*

### 6.2 Useful Log Search Strings

Execute searches against the `sorrel-prod-*` index for the specific incident timeframe:

```text
# Check overall payment processing failures by region and error code
service=payments outcome=failed region=*

# Isolate slow calls to stripe API endpoints
service=payments provider_ms>5000

# Inspect webhook delivery failures and retries
service=payments msg="webhook" outcome=retry

# Trace specific refund status safely without querying card numbers
service=payments msg="refund sent" ref=<ref>

# Monitor dual-shape legacy fallback consumption
service=payments msg="webhook" adapter=legacy_shape
```

### 6.3 Escalation Contacts

- **Service Owner (payments):** Mei
- **Component Engineer:** Leo
- **Secondary Escalation:** Incident Commander rotation (via paging tool)
- **External Provider Status:** status.stripe.com

---
*Document maintained by payments engineering. Revisions require sign-off from Leo or Mei.*
