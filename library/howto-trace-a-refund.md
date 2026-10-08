# How to trace one refund through the logs

Last updated: 2025-08-18  
Owner: Leo (payments)

This guide documents how to follow a single customer refund through Sorrel's infrastructure using the log search tool. It is intended for on-call engineers investigating customer reports escalated by Hana's team, disputed charges, or alert triage during an active shift.

Tracing a refund requires verifying the sequence of events inside our payments service and correlating them with external confirmations from our card processor, stripe. Because payments handles actual money, strict operational rules apply when inspecting these logs.

---

## 1. Safety and Log Query Hygiene

Before searching payments data, keep our data protection standards in mind:

- **Never search for card numbers; they are never logged.** Sorrel does not store Primary Account Numbers (PANs) or sensitive authentication data anywhere in application databases, memory dumps, or log files. Stripe handles card vaulting directly. Querying for 16-digit sequences, track data, or CVVs in the log search tool triggers internal security audits. Every search containing card-like regexes is logged, indexed, and reviewed by the platform team.
- **Do not paste log lines containing card tokens, customer email addresses, or internal keys into public chat.** When discussing an investigation in `#inc-live` or support escalations, reference only the public booking id, the internal payment reference (`ref`), or provide a direct link to the log search tool with the active time bounds.
- **Narrow the search window.** Searching across wide time windows (such as `now-7d`) against the `sorrel-prod-*` index degrades cluster performance. Always bound your query to the specific 2- to 4-hour window surrounding when the customer requested the cancellation or when the support ticket was filed.

---

## 2. Architecture of a Refund

A business sets its own cancellation policy and refund window in Sorrel. When a booking is cancelled within that window—either directly by the customer on the web interface or via the support team using the internal admin tool—the refund pipeline executes asynchronously across services:

```
[ web / admin ] 
       │
       ▼ (RPC)
[     api     ] ──> writes cancellation to database & audit log
       │
       ▼ (enqueue / dispatch)
[  payments   ] ──> validates business rules & idempotency key
       │
       ▼ (HTTPS API request)
[   stripe    ]
       │
       ▼ (Signed Webhook: charge.refund.updated / settlement)
[  payments   ] ──> updates refund status in database
       │
       ▼ (status update)
[     api     ] ──> marks booking refunded
       │
       ▼ (async event)
[  notifier   ] ──> sends receipt email via sendgrid
```

Refund requests that pass initial validation in `api` are dispatched to `payments`. Most refunds are batched or dispatched individually, while nightly cleanup batches process refunds requested throughout the day at 23:30 JST.

---

## 3. The Three Lifecycle Log Lines

A normal, healthy refund lifecycle in the `payments` service produces exactly three distinct log lines in index `sorrel-prod-*`. All lines are tagged with `service=payments` and contain the unique transaction identifier `ref=<ref>`.

| Lifecycle Stage | Event Message (`msg`) | Emitted By | Meaning |
|---|---|---|---|
| 1. Requested | `"refund requested"` | payments core worker | The refund payload was accepted from `api` or admin tooling, validated against the original charge id, and queued for dispatch. |
| 2. Sent | `"refund sent"` | payments processor client | An outbound API call with a distinct idempotency key was transmitted over HTTPS to stripe. |
| 3. Settled | `"refund settled"` | payments webhook receiver | Stripe confirmed the refund reached terminal status via an incoming, cryptographically signed webhook. |

### Stage 1: `refund requested`
This line is written the moment the `payments` node receives the command from `api`. It captures the target refund amount (in integer cents/yen), the currency, the associated `booking_id`, and the newly allocated refund reference `ref`. 

Typical schema payload:
```json
{
  "timestamp": "2025-08-18T14:10:02.104Z",
  "service": "payments",
  "level": "INFO",
  "node": "payments-prd-apne1-node-03",
  "msg": "refund requested",
  "ref": "ref_98a7df01b4c2",
  "booking_id": "bk_5510294",
  "amount": 4500,
  "currency": "jpy"
}
```

### Stage 2: `refund sent`
This log line marks the point of outbound execution. It records that `payments` initiated the network call against Stripe's refund endpoint. 

Search service=payments msg="refund sent" ref=<ref> to see when a refund went to stripe.

This entry contains the execution latency from our side (`duration_ms`) and the remote Stripe response code. If Stripe accepts the request for processing, it returns an HTTP 200 with an object starting with `re_...`.

Typical schema payload:
```json
{
  "timestamp": "2025-08-18T14:10:03.450Z",
  "service": "payments",
  "level": "INFO",
  "node": "payments-prd-apne1-node-03",
  "msg": "refund sent",
  "ref": "ref_98a7df01b4c2",
  "stripe_refund_id": "re_3Ns8X92eZvKYlo2C0aB3x",
  "provider_ms": 346,
  "status": 200
}
```

### Stage 3: `refund settled`
A refund has three log lines: requested, sent, settled; settled comes from the stripe webhook and can arrive hours later.

When Stripe finishes communicating with the customer's card-issuing bank, Stripe emits an asynchronous webhook (`charge.refund.updated` or `refund.updated`) to our public ingress. The `payments` webhook ingestion path validates the webhook signature against our secret, matches the payload to our internal reference, and writes `"refund settled"`. 

Because bank clearance networks, clearing houses, and international card schemes operate on differing update intervals, do not expect `"refund settled"` to appear immediately after `"refund sent"`. A delay of 30 minutes to several hours is completely standard.

Typical schema payload:
```json
{
  "timestamp": "2025-08-18T17:42:18.892Z",
  "service": "payments",
  "level": "INFO",
  "node": "payments-prd-apne1-node-01",
  "msg": "refund settled",
  "ref": "ref_98a7df01b4c2",
  "stripe_refund_id": "re_3Ns8X92eZvKYlo2C0aB3x",
  "event_id": "evt_1Ns8Yk2eZvKYlo2C9kLp1"
}
```

---

## 4. Step-by-Step Triage Procedure

When checking why a customer or salon reports an unconfirmed refund, follow these specific steps in the log search tool.

### Step 1: Locate the reference (`ref`)
If Hana or support only provides a `booking_id` (e.g., `bk_5510294`), you must first resolve the internal payment reference:
1. Set the index to `sorrel-prod-*`.
2. Restrict the time picker to 2 hours before and after the alleged cancellation.
3. Run:
   ```text
   service=payments booking_id="bk_5510294"
   ```
4. Look for the `"refund requested"` line and copy the `ref` value (format: `ref_...`).

### Step 2: Trace the outbound dispatch
Once you have the `ref`, verify whether our nodes actually handed the transaction off to the card provider.
1. Run the targeted query:
   ```text
   service=payments msg="refund sent" ref="<ref>"
   ```
2. Check the timestamp. This tells you precisely when the instruction reached stripe.
3. Check the HTTP response status logged on that line:
   - **HTTP 200**: Stripe acknowledged the instruction. The refund is safely in Stripe's ledger.
   - **HTTP 4xx / 5xx**: The provider rejected the call or experienced a service failure. Check `provider_ms` and provider error messages. Compare with `status.stripe.com` to see if Stripe was experiencing degraded API performance at that timestamp.
   - **No result found**: The refund never left our cluster. Proceed to check for queue deadlocks or database connection issues in `service=payments`.

### Step 3: Check webhook settlement
Verify if the settlement has finalized:
1. Run the query:
   ```text
   service=payments msg="refund settled" ref="<ref>"
   ```
2. If the line exists, the cycle is complete. If the customer claims they have not received the funds, it is a matter of inter-bank processing delays (which typically take 5–10 business days depending on their card issuer), not a technical failure within Sorrel.
3. If no line appears:
   - Check the age of the `"refund sent"` line. If it was sent fewer than 6 hours ago, this is normal behavior.
   - Check the webhook health in the metrics dashboard **Sorrel / payments** ("Webhooks received, retried, failed").
   - Run a fallback query to see if Stripe sent a webhook that encountered processing retries on our side:
     ```text
     service=payments msg="webhook" outcome=retry ref="<ref>"
     ```

---

## 5. Duplicate Detection and Escalation

Because financial transactions carry real compliance and financial liabilities, any irregularity in the log stream requires immediate, decisive handling.

### The Critical Rule
If one reference shows two 'sent' lines, money may have moved twice: stop and page Mei.

Under our idempotency design, every unique refund attempt must carry a distinct idempotency key tied directly to the single `ref`. If a node crashes midway through dispatch, or if a network retry policy was misconfigured during a release, a single refund may mistakenly execute twice against Stripe's API.

When executing:
```text
service=payments msg="refund sent" ref="<ref>"
```

Count the matching log entries:
- **0 lines**: Refund not sent. Check worker queues and `service=payments level=ERROR`.
- **1 line**: Normal operation. Outbound transaction was singular and intact.
- **2 or more lines**: **Anomaly detected.** 

### What to do if two "refund sent" lines appear:
1. **Stop your investigation immediately.** Do not attempt to rerun scripts, do not issue cancellation webhooks, and do not execute ad-hoc database updates.
2. **Do not attempt to roll back code** as your first move if the money has already left our accounts. A rollback will not recover funds that have already settled with the customer's bank.
3. **Declare a P1 incident.** Under section 2 of the on-call handbook, any instance where money moves wrongly—including duplicate refunds—is classified as a P1 regardless of whether the customer or business has noticed.
4. **Page Mei directly via the paging tool.** As the service owner for `payments`, Mei is the only person authorized to make decisions regarding ledger adjustments, Stripe credential adjustments, manual reversal disputes, or initiating clawbacks from merchant balances.
5. In your page description and the `#inc-live` incident thread, paste:
   - The alert or discovery line.
   - The exact payment reference (`ref`).
   - The timestamps of both `"refund sent"` log events.
   - The Stripe refund IDs associated with each line (e.g., `re_AAA...` and `re_BBB...`).

---

## 6. Common Log Search Patterns for payments

Below is a consolidated reference of standard log search filters when analyzing refunds on the `sorrel-prod-*` index.

```text
# 1. Trace the entire lifecycle of a single refund reference
service=payments ref="ref_example123"

# 2. Check for dispatch timestamp to stripe
service=payments msg="refund sent" ref="ref_example123"

# 3. Check for provider timeouts during dispatch (>5000ms)
service=payments msg="refund sent" provider_ms>5000

# 4. Filter for webhook reception on a specific refund
service=payments msg="refund settled" ref="ref_example123"

# 5. Check if webhook ingestion is experiencing retries
service=payments msg="webhook" outcome=retry

# 6. Check for validation errors prior to sending
service=payments msg="validation" field=*

# 7. Isolate failures across all refund operations in a given window
service=payments outcome=failed
```

---

## 7. Escalation Boundaries

Operating on-call requires knowing what decisions you can make independently versus what requires service owner involvement:

### What On-Call Can Do
- Run all read queries across `sorrel-prod-*` logs using the log search tool.
- Cross-reference timestamps with `status.stripe.com` to confirm external outages.
- Provide factual timeline details (`requested`, `sent`, `settled`) to Hana's support team so they can communicate with merchants.
- Inspect the **Sorrel / payments** dashboard to see if checkout latency or provider timeouts are elevated globally.

### What On-Call Cannot Do
- Never modify or retry a transaction directly against Stripe's production API.
- Never manually adjust merchant balances or fee subtractions.
- Never issue manual compensating refunds through the Stripe dashboard.
- Never rotate payment credentials or update webhook signing secrets during an incident without Mei.
- Never communicate directly with businesses or consumers regarding lost funds or duplicate payouts. All communications must go through Hana (support lead) or Mei (payments owner).
