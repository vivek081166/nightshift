# twilio: Japan carrier notes

Date: 2025-03-31  
Owner: Tom (notifier)  

## Overview

Sorrel relies on twilio as our outside SMS provider for critical transactional notifications: appointment reminders, calendar updates, and one-time sign-in verification codes. The notifier service is the only Sorrel service that communicates with twilio.

Our largest operating volume originates in the `ap-northeast` region (Tokyo). Japanese telecommunications networks have unique carrier routing and reporting characteristics compared to North American or European aggregators. During high-volume morning booking periods (07:00–09:00 JST) and during evening checkout peaks, on-call engineers frequently observe metric discrepancies in delivery receipt reporting that can easily be mistaken for vendor outages.

This operational note details specific carrier behaviors in Japan—particularly regarding KDDI—to prevent false escalations and misdiagnosed alerts.

---

## Service Architecture and SMS Delivery Pipeline

Understanding the SMS lifecycle helps interpret board metrics accurately when triage is required:

1. **Queueing:** `api` or `web` enqueues an SMS payload onto notifier's background processing queue.
2. **Dispatch:** A `notifier` worker node in `ap-northeast-1` pulls the job, formats the recipient number (E.164 format, `+81`), selects the configured sender number, and issues a REST API call to twilio.
3. **Vendor Acceptance:** twilio validates the request. If accepted, twilio returns an HTTP `201 Created` with a message SID and initial status. notifier marks the message record internally as `dispatched`.
4. **Carrier Handoff:** twilio submits the SMS to the target downstream Japanese mobile carrier network (NTT Docomo, KDDI / au, SoftBank, or Rakuten Mobile).
5. **Handset Termination:** The carrier delivers the message to the customer's mobile device.
6. **Delivery Receipt (DLR):** The carrier asynchronously issues a delivery status notification back to twilio, which twilio forwards to `notifier` via an incoming status webhook. notifier processes the webhook payload and transitions the message status from `pending` to `delivered` (or `failed` / `undelivered`).

```
[ api / web ]
      │ (enqueue message)
      ▼
[ notifier worker ] ──(HTTP POST)──► [ twilio API ]
      │                                    │
      │ (dispatched)                       ▼
      │                             [ Japan Carrier ] (Docomo / KDDI / SoftBank)
      │                                    │
      │                                    ▼
      │                             [ Handset Delivered ]
      │                                    │ (Carrier DLR)
      ▼                                    ▼
[ notifier db ] ◄──(Status Webhook)─ [ twilio Webhook Router ]
(pending -> delivered)
```

---

## KDDI Delivery Receipt Characteristics

The primary operational anomaly observed in Japan involves the KDDI network.

### 1. Delivery Receipt Lag

- Delivery receipts for KDDI numbers in Japan can arrive up to 40 minutes after the SMS was delivered.
- While the customer often receives the SMS on their mobile device within seconds of dispatch, KDDI’s upstream aggregator and signaling network periodically batches or delays the return DLR.
- During this window, `notifier` marks such messages `pending`, not `failed`.
- Messages remain in the `pending` state until the definitive terminal status webhook is received from twilio or until internal retry/cleanup thresholds expire.

### 2. Dashboard Interpretation

On the metrics dashboard (Board **"Sorrel / notifier"**), review the channel panels carefully:

- **Pending Message Count:** A pending count rising on the notifier board for KDDI only is usually receipt lag, not failure.
- **Vendor Response Codes:** If twilio is returning standard success responses (`201`) on message creation and there is no corresponding surge in explicit vendor failure codes (`5xx` or terminal error codes), downstream delivery is taking place.
- **Oldest Message Age:** An elevated message age on delivery tracking metrics that tracks KDDI destinations alone does not indicate that worker nodes are stuck or that the queue is backing up.
- **Handset Confirmation:** Customers are generally receiving their SMS reminders without incident despite the board reflecting an accumulation of unresolved `pending` states.

```
Metric Pattern: KDDI Receipt Lag vs. Vendor Outage

Normal / KDDI Lag:
Twilio HTTP 201 rate:       ████████████████████ (Normal, tracking queue intake)
Twilio API 5xx rate:        (Zero)
Delivery Outcome (Docomo):  [delivered: 99%] [failed: 1%]
Delivery Outcome (KDDI):    [pending: 42%]   [delivered: 57%] [failed: 1%]
Oldest Pending Age (KDDI):  Up to 2400s (40 min)
Diagnosis:                  Carrier receipt delay. Handsets receive SMS. No action required.

True Downstream Outage:
Twilio HTTP 201 rate:       ████████████████████
Twilio API 5xx rate:        (Zero or elevated)
Delivery Outcome (KDDI):    [pending: 2%]    [undelivered/failed: 98%]
Carrier Status Page:        Incident reported on KDDI network.
Diagnosis:                  True carrier failure. Handsets not receiving SMS.
```

---

## Evaluating twilio Status and Carrier Status

When investigating SMS delivery anomalies or when an alert rule fires (e.g., `notifier-sms-fail`), follow standard runbook procedure: check the external dependency before altering internal configuration.

### 1. Status Page Inspection

- twilio’s status page is located at `status.twilio.com`.
- Do not rely solely on the high-level summary at the top of the page. twilio's status page lists Japanese carriers separately; check the carrier line, not only the overall status.
- Expand the **Programmable Messaging** section and look specifically under regional aggregations for Japan:
  - NTT Docomo
  - KDDI
  - SoftBank
  - Rakuten Mobile
- A major status page banner may report "Operational" globally even when a specific Japanese carrier route is degraded or suffering an unscheduled maintenance outage.

### 2. Interpreting Status Indicators

| Status Indication | Meaning for On-Call | Operational Move |
|---|---|---|
| **Global Green / KDDI Carrier Line Green** | All systems normal. If KDDI `pending` counts climb, it is standard receipt lag. | **no action** (log and monitor). |
| **Global Green / KDDI Carrier Line Degraded** | Downstream aggregator is experiencing carrier signaling queues or delayed status reports. | **check provider** (note status page timeline in `#inc-live`). Do not page owner. |
| **KDDI Carrier Line Major Outage / Failure** | Messages terminating to KDDI handsets are failing. twilio will reject or mark `undelivered`. | **check provider**. Verify impact in `#inc-live`. Support lead (Hana) handles customer messaging. |
| **Twilio API 5xx Surge (All Destinations)** | Core twilio edge platform failure. Worker dispatches failing across all carriers. | **check provider**. Verify `status.twilio.com`. Confirm retry backoff is functioning. |

---

## Administrative Ownership and Boundaries

Strict access boundaries apply to all telephony infrastructure at Sorrel. The on-call engineer, secondary on-call, and platform engineers must respect the permissions table set forth in the handbook.

- **Sender Numbers and Limits:** Sender numbers and sending limits are changed by Tom only.
- Under no circumstances should an on-call engineer attempt to provision new Japanese shortcodes, alter alphanumeric sender IDs, change twilio long-code pools, or adjust sending concurrency/throughput throttles.
- If messaging volumes approach daily or per-second account limits during high-traffic booking days, notify Tom during regular hours. Raising sending limits or purchasing additional sender numbers is a commercial and administrative decision reserved for the service owner.

### On-Call Engineers: Permitted vs. Prohibited Moves

```
┌────────────────────────────────────────────────────────────────────────┐
│ ON-CALL ENGINEER                                                       │
├───────────────────────────────────┬────────────────────────────────────┤
│ PERMITTED ACTIONS                 │ PROHIBITED ACTIONS                 │
├───────────────────────────────────┼────────────────────────────────────┤
│ • Read dashboard metrics          │ • Changing sender numbers          │
│ • Inspect logs in sorrel-prod-*   │ • Purchasing new numbers           │
│ • Check status.twilio.com         │ • Modifying twilio sending limits  │
│ • Verify queue worker throughput  │ • Altering webhook URLs / secrets  │
│ • Roll back notifier deploys      │ • Contacting twilio account reps   │
│ • Document findings in #inc-live  │ • Promising customer SMS refunds   │
└───────────────────────────────────┴────────────────────────────────────┘
```

---

## Triage Workflow for SMS Delivery Alerts

When alerted on SMS degradation (for example, if `notifier-sms-fail` triggers because terminal failure rates exceed 20% over 5 minutes), execute the triage steps in the exact sequence specified by team doctrine.

### Step 1: Examine the Alert Context and Metrics

1. Open the board **"Sorrel / notifier"**.
2. Locate the panel **Delivery outcomes per channel (email, SMS)** and **Vendor response codes per channel**.
3. Determine whether the alert reflects actual terminal failures (`failed`, `undelivered`) or an accumulation of unconfirmed messages.
4. Check the carrier distribution:
   - If the issue affects all carriers across Japan, US, and Europe: suspect twilio API availability or our outbound networking in `ap-northeast-1`.
   - If the issue isolates strictly to KDDI recipients: check whether it is a true failure spike or elevated `pending` state accumulation.

### Step 2: Correlate Deployments

- Check deploy history in the deploy tool for service `notifier`.
- Note the age of the last deploy.
- If a new `notifier` release was deployed within the last 30 minutes, and log output indicates template rendering exceptions, payload syntax errors, or corrupted phone number formatting across all dispatches, a rollback may be warranted.
- If no recent deploy has occurred, do not touch application code or nodes.

### Step 3: Check Provider Health

- Navigate to `status.twilio.com`.
- Inspect the specific Japanese carrier status lines (NTT Docomo, KDDI, SoftBank).
- If the carrier line or messaging pipeline displays an active incident, paste the vendor update URL, incident timestamp, and details into `#inc-live`.
- Per our on-call rules, when the alert points to a third-party outage, the action is **check provider**. Rolling back application code does not restore carrier routing.

### Step 4: Examine Service Logs

Search the log indexing tool for `service=notifier`:

```
service=notifier msg="vendor error" channel=sms
```

Look for specific twilio error payloads:
- `21211`: Invalid phone number format (application or customer input issue).
- `21610`: Recipient unsubscribed/blacklisted.
- `30003` / `30005`: Handset unreachable or unknown destination.
- `30008`: Unknown carrier delivery failure (carrier-side drops).
- `Resource temporarily unavailable` or `5xx`: twilio edge gateway issues.

To monitor KDDI-specific webhook traffic:

```
service=notifier channel=sms carrier=kddi
```

Confirm whether status webhooks are arriving late with `status=delivered` or if messages are transitioning to hard delivery failures.

### Step 5: Incident Logging and Handover

Record your observation in the on-call log following standard team format:

`<date> <time JST> | notifier | <severity> | <first move> | <one sentence summary>`

*Example log entries:*
- `2025-03-31 08:15 JST | notifier | P3 | check provider | KDDI pending status count elevated on notifier board; checked status.twilio.com carrier line which confirms normal operations and standard receipt lag.`
- `2025-03-31 14:22 JST | notifier | P2 | check provider | notifier-sms-fail fired; checked status.twilio.com and identified active partial degradation on KDDI route.`

---

## Edge Cases and Failure Scenarios

### Customer Sign-In via SMS Fallback

When a true carrier outage prevents SMS delivery to Japanese handsets:
- Verification codes and one-time sign-in SMS messages will not reach the user.
- Customers attempting to log in will experience authentication blocks if they rely solely on SMS.
- The `web` authentication flow provides an email fallback mechanism. If customer inquiries escalate through support, confirm that `notifier` email dispatch via SendGrid is operational.
- Do not attempt to bypass SMS authentication at the database level. Direct all inquiries regarding authentication policies to Aiko (`web`) or Ravi (`api`).

### Nightly Batch Reminder Interaction

- Between 02:00 and 04:00 JST, notifier's scheduler generates and enqueues reminder messages for the upcoming business day across `ap-northeast`.
- Queue depth naturally rises on the **"Sorrel / notifier"** board during this period and resolves by 06:00 JST.
- If KDDI delivery receipts lag by 30 to 40 minutes during the early morning batch run, the absolute count of `pending` messages will appear unusually high due to the sheer volume dispatched in that two-hour window.
- Compare **Messages added per minute** against **Messages delivered per minute**. If workers are steadily clearing jobs from the queue and twilio returns `201 Created` for outbound dispatches, the elevated `pending` tally is benign.

---

## Escalation Reference

If an incident requires escalation beyond on-call triage:

| Scenario | Escalation Target | Method |
|---|---|---|
| Persistent carrier failure causing wide-scale customer login failures (P1 criteria met) | Tom (notifier owner), secondary: Incident Commander rotation | Page via paging tool schedule "notifier owner" |
| Need to adjust sender numbers, messaging throughput, or twilio account limits | Tom | Ticket or direct handover during business hours |
| Inquiries regarding customer communication, status page wording, or goodwill credits | Hana (support lead) | Incident thread in `#inc-live` |
| Platform infrastructure, host networking, or outbound NAT issues in `ap-northeast-1` | Sara / Kenji Sato (platform) | Incident thread in `#inc-live` |

*Note: For any P1 incident open longer than 15 minutes, page the incident commander rotation. Do not attempt direct modification of external vendor accounts.*
