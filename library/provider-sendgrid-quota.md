# sendgrid: quota and streams

Last updated: 2025-10-06  
Owner: Tom (notifier)  

This note documents how Sorrel uses sendgrid for outbound email delivery, how daily quotas work across distinct email streams, and how on-call engineers should handle quota exhaustion or vendor-side delivery errors.

---

## 1. Context and architecture

Sorrel relies on sendgrid as the primary email vendor for the `notifier` service. Other services (`web`, `api`, `payments`) do not speak directly to outside messaging vendors. Instead, they produce events onto `notifier`'s internal queue. Worker nodes running across our active regions (`ap-northeast`, `us-east`, `eu-west`) poll this queue, render the appropriate localized templates, and call the vendor's outbound mail API.

```
+-------------------------------------------------------------+
|  Sorrel Services (web, api, payments)                      |
+-------------------------------------------------------------+
                              |
                              v (enqueue message job)
+-------------------------------------------------------------+
|  notifier queue (managed queue in aws)                     |
+-------------------------------------------------------------+
                              |
                              v (poll jobs)
+-------------------------------------------------------------+
|  notifier workers (3 nodes per active region)              |
|  - Renders email templates                                  |
|  - Selects stream (transactional vs. marketing)            |
+-------------------------------------------------------------+
                              |
                              v (HTTPS / vendor API)
+-------------------------------------------------------------+
|  sendgrid API (status.sendgrid.com)                         |
+-------------------------------------------------------------+
```

Because outbound email delivery is asynchronous, vendor degradation or vendor quota limits never cause upstream synchronous 5xx errors on `api` or `web`. However, failures directly impact customer experience by delaying appointment confirmations, cancellation notices, and receipts.

---

## 2. Stream separation (transactional vs. marketing)

Since 2025-09-30, transactional email (confirmations, receipts) and marketing email use separate streams with separate quotas.

Prior to this separation, sudden marketing campaigns or mass promotional announcements risked starving critical transactional messages. Under the current configuration, traffic is isolated into two distinct pipelines at the worker layer:

| Stream | Intended traffic | Impact if quota exhausted | Isolation policy |
|---|---|---|---|
| **Transactional** | Appointment booking confirmations, rescheduling notices, receipts, cancellation notices, notices to businesses. | Customers do not receive immediate confirmation of bookings or cancellations. Queued until quota reset. | Hard isolation. Transactional quota cannot be borrowed by marketing campaigns. |
| **Marketing** | Product updates, seasonal business promotions, newsletters. | Marketing outreach delayed. No impact on customer booking flows. | Completely separate sub-user and API pool. Failures or throttling here never bleed into transactional delivery. |

Workers assign the stream based on the source payload metadata before making outbound calls. If a stream encounters a rate limit or vendor rejection, the worker handles that stream independently without pausing jobs destined for the other stream.

---

## 3. Daily quota mechanics

Our commercial tier with sendgrid enforces a daily volume threshold across each stream.

- **Reset window:** The sendgrid daily quota resets at 09:00 JST (00:00 UTC).
- **Behavior on quota exhaustion:** When the quota is reached, notifier keeps emails on the queue and sends them after the reset.
- **Worker behavior:** When the vendor rejects an outbound request due to quota limits (typically returning HTTP 429 with vendor-specific quota payload bodies), worker nodes do not drop the message or treat it as permanently bounced. Instead, workers mark the job for deferred retry. Messages accumulate in the `notifier` queue and drain once the quota resets at 09:00 JST.

### 3.1 Policy on quota adjustments

Raising the quota is a purchasing decision for Tom, not an on-call action.

On-call engineers do not have administrative access, contractual authorization, or purchasing permission to increase sending allocations in the sendgrid portal. If an alert fires because a quota ceiling has been hit:
1. Do not attempt to modify vendor plan tiers or search for administrative credential workarounds.
2. Verify whether the exhaustion is in the marketing stream or the transactional stream.
3. If the transactional stream has stalled and is impacting live booking confirmations, evaluate severity based on customer impact and queue growth, then escalate to Tom (or backup via the paging tool) if business intervention or contractual tier elevation is required.

---

## 4. Dashboards and observability

When investigating `notifier` alerts related to email delivery, refer to the metrics tool under the **Sorrel / notifier** dashboard folder.

### 4.1 Relevant dashboard panels

| Panel name | What it measures | Normal range | Indication during quota exhaustion |
|---|---|---|---|
| **Queue depth** | Total unprocessed message jobs waiting in the queue. | 0 – 300 (spikes up to 1,500 during nightly reminder batches between 02:00 and 04:00 JST). | Steadily climbs or stays flat above normal baseline without draining. |
| **Messages added vs. delivered** | Enqueue rate vs. successful vendor acceptance rate per minute. | Tracks roughly 1:1 during working hours. | "Added per minute" remains normal; "delivered per minute" drops to zero or near-zero for the affected channel. |
| **Delivery outcomes per channel** | Stacked chart: accepted, delivered, bounced, failed (split by email and SMS). | Dominantly accepted / delivered. | Sharp spike in vendor rejections / failures on the `email` series. |
| **Vendor response codes** | HTTP status codes returned by sendgrid's API. | 2xx responses > 99.5 %. | Cluster of 429 Too Many Requests or specific vendor quota error strings. |
| **Vendor quota usage** | Percentage of daily quota consumed for transactional and marketing streams. | Rises gradually over 24 hours, resetting at 09:00 JST. | Hits 100 % before 09:00 JST. |

### 4.2 Log search patterns

All logs are stored in the log search tool under index `sorrel-prod-*`. To isolate vendor quota issues, narrow the time window to the start of the symptom and run targeted queries against `service=notifier`.

- **Find quota rejections:**
  ```text
  service=notifier msg="quota"
  ```
  Look for vendor payload fields indicating stream type (`stream=transactional` vs. `stream=marketing`) and remaining credits.

- **Check general vendor rejections:**
  ```text
  service=notifier msg="vendor error" channel=email
  ```
  This surfaces raw vendor status codes and error messages returned by sendgrid endpoints.

- **Track worker status during backlogs:**
  ```text
  service=notifier msg="worker idle"
  service=notifier msg="worker stuck"
  ```
  Use these to verify that worker threads are healthy and waiting on rate-limit backoffs rather than deadlocked.

---

## 5. Troubleshooting and operational procedure

When an alert fires involving `notifier` email delivery, follow the structured operational actions outlined in the handbook:

### 5.1 Step 1: Assess severity and symptoms

Read the alert line carefully. Look for:
- Duration of the symptom.
- Current queue depth and whether delivered-per-minute is zero or simply lagging.
- Channel affected (email vs. SMS).

Common alert triggers involving email:
- `notifier-email-fail`: Fires when email failure rate exceeds 20 % for 5 minutes.
- `notifier-queue-depth`: Fires when queue depth exceeds 1,000 for 20 minutes.
- `notifier-queue-stalled`: Fires when delivered per minute is at zero for 15 minutes with messages waiting.

*Reminder on normal traffic:* Queue depth naturally rises between 02:00 and 04:00 JST as the scheduler batches the next day's reminders for `ap-northeast-1`. If messages delivered per minute remains steady and healthy during this window, queue growth is expected and will clear by 06:00 JST.

### 5.2 Step 2: Determine the first move

Apply the five actions strictly based on facts:

```
                  +-----------------------------------+
                  |      Alert fires on notifier      |
                  +-----------------------------------+
                                    |
            Is the alert pointing directly at a vendor?
            (e.g., vendor status, vendor 5xx, quota)
                     /                             \
                   YES                              NO
                   /                                 \
     +--------------------------+          Did a deploy just go out
     | check provider           |          within the last 30 mins?
     | - status.sendgrid.com    |                 /            \
     +--------------------------+               YES             NO
                                                /                \
                                    +---------------+   +-------------------+
                                    | roll back     |   | read logs         |
                                    | (deploy tool) |   | (check worker     |
                                    +---------------+   |  output, errors)  |
                                                        +-------------------+
```

- **check provider:** If the alert explicitly cites vendor errors, quota limits, or third-party timeouts, look at `status.sendgrid.com` first. Determine if the provider is experiencing degraded performance, backlog processing delays, or an outage.
- **read logs:** If the cause is unconfirmed, inspect `service=notifier` logs to check whether workers are encountering template rendering bugs, network connectivity failures within `aws`, or quota rejections.
- **roll back:** Only undo the most recent deploy via the deploy tool if a deploy occurred within the last half hour and corresponds directly with the onset of failures. (Note: A rollback stops new sends from bad code; it cannot recall emails already delivered to sendgrid).
- **page owner:** If a situation occurs that cannot be undone, or if an administrative decision outside on-call authority must be made (such as an emergency commercial contract override), page Tom via the paging tool.
- **no action:** If the alert fired on a harmless queue fluctuation (such as the early-morning reminder scheduler) while delivery throughput is active and unblocked, log the entry and move on.

### 5.3 Step 3: Quota exhaustion triage workflow

If dashboard metrics or logs confirm that `msg="quota"` is being returned:

1. **Identify the affected stream:**
   - Review the **Vendor quota usage** panel on the `notifier` board.
   - If the **Marketing stream** is at 100 %: Customer transactional emails (confirmations, receipts) are entirely unaffected due to stream separation. Marketing jobs will hold on the queue and resume draining at 09:00 JST. This is a non-customer-impacting degradation for core product usage. Document the state in `#inc-live` or log it as a P3 trend for working hours.
   - If the **Transactional stream** is at 100 %: Customers booking appointments will experience delayed confirmations. Evaluate time until reset (09:00 JST).
2. **Confirm queue persistence:**
   - Verify that workers are safely deferring jobs and not dropping messages. `notifier` is built to retain messages on the queue until the quota opens.
3. **Escalation boundary:**
   - Do not attempt to upgrade or change settings on the sendgrid account. Raising the quota is a purchasing decision for Tom.
   - If transactional delivery will be delayed for a prolonged period during peak daytime hours, page Tom using the paging tool with the alert line, current severity, and current queue depth.
4. **Log the event:**
   - Record the entry in the on-call log following the standard format:
     `<date> <time JST> | notifier | <severity> | <first move> | <summary>`

---

## 6. Provider interaction and failure reference

Summary of operational expectations when working with sendgrid:

| Attribute | Specification / Rule | Reference |
|---|---|---|
| **Service Dependency** | `notifier` is the only service that talks to sendgrid. No other service interacts with it directly. | Handbook Section 6.3 |
| **Public Status Page** | `status.sendgrid.com` | Handbook Section 6.3 |
| **Daily Quota Reset** | 09:00 JST (00:00 UTC) every day. | Section 3 |
| **Stream Architecture** | Separate transactional and marketing streams since 2025-09-30. | Section 2 |
| **Retry Behavior** | Rejected emails remain on `notifier` queue; workers resume sending after quota reset or vendor recovery. | Handbook Section 6.3 & Section 3 |
| **Quota Modifications** | Tom decides quota and plan changes. On-call never modifies vendor account plans. | Handbook Section 6.3 & Section 3 |
| **Worker Rollback** | Deploy tool -> project "sorrel" -> service "notifier". Workers drain in-flight messages before switching (~3 minutes). | Handbook Section 5.4 |
| **Service Owner** | Tom (notifier owner). Backup: incident commander rotation. | Handbook Section 4.1 |

---

## 7. Change log

- **2025-10-06:** Updated documentation to reflect stream separation (transactional vs. marketing) introduced on 2025-09-30. Clarified quota reset timing (09:00 JST), worker retention behavior, and on-call escalation boundaries regarding plan purchasing limits. — *Tom / Kenji Sato*
- **2025-08-14:** Initial provider reference note published covering baseline `notifier` worker interactions and queue failure states. — *Tom*
