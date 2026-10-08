# notifier runbook (2024 edition)

Last updated: 2024-05-27  
Owner: Tom (notifier)  
Maintainers: Tom, Yuki  

---

## 1. Overview and Architecture

`notifier` handles all outbound communications dispatched by Sorrel. This includes customer booking confirmations, itemized receipts, cancellation notices, schedule modifications, SMS appointment reminders, one-time sign-in verification codes, and operational notifications sent to business owners regarding calendar updates.

The service operates asynchronously. Upstream services (`api`, and indirectly `payments` or `web`) do not wait for external message delivery. Instead, they produce message payloads onto a managed queue hosted in AWS. `notifier` worker instances consume from this queue, render the appropriate templates with locale and business details, and dispatch calls to our external messaging vendors:

- **Email:** Delivered via SendGrid. Used for booking confirmations, business notices, receipts, and cancellation details.
- **SMS:** Delivered via Twilio. Used for critical one-time sign-in passcodes and upcoming appointment reminders.

Because `notifier` sits at the terminal edge of our synchronous architectures, downtime or backlogs in `notifier` do not directly break HTTP request paths on `web` or `api`. However, delivery failures cause immediate customer confusion, support ticket spikes, missed client appointments, and login lockouts when SMS verification codes stall.

### Topology and Infrastructure (2024 Configuration)

```
 [web / api] 
      │
      ▼ (Enqueue payload)
 [AWS Queue]
      │
      ├──────────────────────────────┐
      ▼                              ▼
[Worker Node 1]                [Worker Node 2]  (per active region)
      │                              │
      ├──────────────┬───────────────┤
      ▼              ▼               ▼
 [Template Engine]  [Twilio API]    [SendGrid API]
```

- **Worker pool:** `notifier` runs two worker nodes behind the queue in each active region (`ap-northeast-1`, `us-east-1`, `eu-west-1`). (Note: worker capacity was provisioned at two nodes per region in the Q1 2024 cluster sizing plan).
- **Scheduler daemon:** A cron-driven scheduling process runs within the primary cluster, querying upcoming appointments from `api` storage and placing scheduled reminders onto the queue ahead of appointments.
- **Regions:** Regional instances consume locally queued tasks to maintain low latency and data residency standards where applicable.

---

## 2. Telemetry and Dashboards

The primary dashboard for monitoring this service is located in the metrics tool under **Sorrel / notifier**.

When investigating degraded states, keep this board open and observe the following metrics:

| Metric Panel | Description | Expected Baseline |
|---|---|---|
| **Queue Depth** | Total count of pending messages in the queue | < 200 during normal daylight hours; climbs during scheduled batch runs |
| **Ingress vs. Egress Rate** | Messages added per minute vs. messages delivered per minute | Lines should track closely during steady state |
| **Oldest Message Age** | Age of the message at the front of the queue | Under 60 seconds during normal operations |
| **Delivery Outcomes by Channel** | Breakdown: accepted by vendor, delivered, bounced, failed (SMS vs. email) | Delivery success > 99% |
| **Vendor Response Codes** | HTTP statuses returned by SendGrid and Twilio APIs | 2xx/202 responses; minimal 429 rate limits or 5xx vendor faults |
| **Vendor Quota Tracking** | Daily consumed outbound volume against contracted tier limits | Predictable growth curve matching business activity |

*(Note: There is currently no dedicated dashboard panel for duplicate tracking. In this 2024 deployment, duplicate dispatches must be diagnosed directly via log aggregation queries; see Section 6).*

---

## 3. Operational Characteristics and Scheduled Batches

### 3.1 The Nightly Reminder Batch (ap-northeast)

The scheduler executes the next-day reminder calculation on an established schedule. For our primary market in Tokyo (`ap-northeast`), the nightly reminder batch runs between **01:00 and 03:00 JST**.

During the **01:00–03:00 JST** window:
- Ingress rate will surge as thousands of upcoming appointments are identified, formatted, and pushed onto the queue.
- **Queue Depth will climb substantially** (often passing 1,000–2,500 pending messages).
- **This is expected behavior.** Do not panic or assume workers have failed simply because the queue size spikes.
- **Check Egress:** Ensure the "messages delivered per minute" line remains steady or elevated. If messages are continuously draining and the oldest message age is resolving predictably across the window, the system is performing normally. By 04:30 JST, the queue should return to its sub-200 baseline.

### 3.2 Daylight Hours (07:00–23:00 JST)

- **07:00–09:00 JST:** Morning commute spike. High volume of transactional sign-in SMS codes and new morning bookings.
- **12:00–13:00 JST:** Lunchtime booking burst.
- **18:00–23:00 JST:** Evening peak. Heavy volume of new checkout confirmations and payment receipts. Oldest message age should stay under 60 seconds throughout these windows.

---

## 4. Triage and the Five Actions

When on-call receives an alert for `notifier`, follow the five standard actions in the Sorrel On-Call Handbook. Do not guess; base your first move on the explicit facts presented in the alert line and dashboards.

```
                  ┌──────────────────────────────┐
                  │      notifier Alert Fires    │
                  └──────────────┬───────────────┘
                                 │
                 Check Alert Details & Dashboards
                                 │
     ┌───────────────────┬───────┴──────────┬───────────────────┐
     ▼                   ▼                  ▼                   ▼
Deploy < 30m?      Vendor Error /      Stalled Queue       Data / Quota
Recent failure?    Quota mentioned?   Unknown Cause?       Irreversible?
     │                   │                  │                   │
[roll back]      [check provider]      [read logs]        [page owner]
(Undo via        (Inspect Twilio /     (Examine worker    (Tom for limits,
deploy tool)     SendGrid status)       stack traces)     keys, accounts)
```

### 4.1 `roll back`
- **When to execute:** Use when an alert fires within ~30 minutes of a recent `notifier` deploy, where workers begin crashing, template rendering failures spike across all messages, or processing stalls immediately after the new release.
- **Execution:** Go to the deploy tool, select project "sorrel", service "notifier", identify the previous known-good deploy ID (`d-xxxx`), and trigger "Roll back to this". 
- **Behavior:** The two worker nodes per region will finish their in-flight message execution before picking up the rolled-back code revision (takes approximately three minutes).
- **Constraint:** Rolling back stops new message failures from the bad deploy. It cannot recall an email or SMS that has already been handed off to an external vendor API.

### 4.2 `read logs`
- **When to execute:** When the root cause is unclear. For example: queue depth is flat or rising, message delivery has slowed down, but no vendor incident is apparent and no deploy occurred recently.
- **Execution:** Query the log search tool for `service=notifier` targeting the start of the deviation window. Look for unhandled exceptions, worker exit loops, template syntax bugs, or internal connection pool timeouts.

### 4.3 `check provider`
- **When to execute:** When the alert symptoms or metrics explicitly indicate upstream supplier degradation (e.g., SendGrid returning 5xx gateway errors or Twilio returning carrier delivery drops).
- **Execution:**
  - Twilio: Check `status.twilio.com`
  - SendGrid: Check `status.sendgrid.com`
  - AWS (Underlying SQS/Compute): Check `health.aws.amazon.com`
- Check whether the external vendor has flagged degraded performance, rate limiting, or regional carrier outages (specifically Japanese mobile carriers for Tokyo traffic).

### 4.4 `page owner`
- **When to execute:** When an irreversible condition or policy decision is encountered that cannot be settled by on-call engineers alone:
  - Account-level daily sending quotas hit on SendGrid or Twilio requiring contractual tier increases.
  - Hard credential compromise or live API key exposure.
  - Large-scale delivery of sensitive customer data to incorrect destinations.
  - An unresolved P1 incident that has persisted past 30 minutes where initial remediation failed.
- **Owner:** Tom (notifier owner). Backup: Incident Commander rotation.

### 4.5 `no action`
- **When to execute:** When an alert fires on a harmless transient spike or expected pattern where no customer harm is taking place.
- **Example:** Queue depth crossing a threshold between 01:00 and 03:00 JST during the automated nightly reminder batch, while delivered-per-minute metrics demonstrate that workers are steadily and rapidly draining the queue. Write one line in the on-call log and let it drain.

---

## 5. Symptom and Failure Mode Runbooks

### 5.1 Alert: Queue Depth High / Growing

**Diagnostic Steps:**
1. Open dashboard **Sorrel / notifier**.
2. Examine the time: Is it between 01:00 and 03:00 JST? If yes, check the "messages delivered per minute" panel. If workers are delivering at high volume, this is the ap-northeast nightly reminder run. If the backlog is draining normally, this is a P3 scenario requiring no intervention.
3. If outside batch hours, compare **messages added** vs **messages delivered**.
   - If added is 10x normal: Check upstream `api` activity. Did a marketing blast or massive reschedule occur?
   - If delivered is zero or near-zero: Workers are stalled (proceed to Section 5.2).
4. Review deploy history. Was `notifier` deployed in the last 30 minutes?
   - If yes and delivery flatlined or errored immediately: **roll back** in the deploy tool.

### 5.2 Alert: Queue Stalled / Delivered at Zero

**Diagnostic Steps:**
1. Check the oldest message age. If age is increasing linearly and delivered is zero, messages are blocked.
2. Check worker node health on the dashboard. Are the two worker nodes in the region alive or throwing out-of-memory (OOM) alerts?
3. If not preceded by a recent deploy, the first move is **read logs**:
   ```
   service=notifier level=ERROR
   ```
   Look for:
   - `msg="worker stuck"` or `msg="worker idle"`
   - Database/Queue connectivity timeouts
   - Repeated unhandled template rendering crashes causing worker thread panics
4. If logs show workers crashing repeatedly on a bad payload ("poison pill"), isolate the specific failing message ID or template error. If widespread code corruption exists following a release, roll back.

### 5.3 Alert: SMS Failure Rate Spike

**Diagnostic Steps:**
1. Inspect the "Delivery outcomes per channel" panel. Confirm SMS is failing while Email is healthy.
2. Inspect "Vendor response codes per channel".
   - Are we receiving HTTP 429 (Too Many Requests)? We are exceeding Twilio concurrency or account-level rate limits.
   - Are we receiving HTTP 5xx from the API endpoint? Twilio edge is failing.
3. **check provider:** Visit `status.twilio.com`. Review SMS delivery status, particularly Japan carrier routes.
4. If Twilio confirms a major outage, document findings in `#inc-live`. Note that `notifier` automatically retains unacknowledged or failed tasks and retries delivery for up to one hour. 
5. If the issue is a hard account suspension or depleted Twilio balance/quota, **page owner** (Tom).

### 5.4 Alert: Email Failure Rate Spike

**Diagnostic Steps:**
1. Verify the channel breakdown: Confirm whether failures are confined to SendGrid.
2. Inspect vendor response codes:
   - Look for vendor error strings indicating quota exhaustion:
     `service=notifier msg="quota"`
   - If logs show daily account limits reached, on-call engineers cannot upgrade contract plans. **page owner** (Tom).
3. If responses show API connection timeouts or 502/503 errors: **check provider** at `status.sendgrid.com`.
4. If SendGrid is operational and there was a recent deploy changing email templates, **read logs** for syntax compilation errors:
   ```
   service=notifier msg="vendor error" channel=email
   ```
   If template syntax errors are throwing exceptions post-deploy, **roll back** to the prior version.

---

## 6. Duplicate Detection and Log Hunting

*Important Notice for the 2024 Deployment:* Because `notifier` does not currently feature a dedicated duplicate monitoring dashboard panel, suspected duplicate message dispatches cannot be tracked via a graph. 

Duplicate sends usually surface when customer support leads (such as Hana) report that multiple identical emails or SMS codes were received by users, or when an alert rule triggers on duplicate message identifiers.

### Diagnostic Workflow for Duplicates

When duplicate sends are reported or suspected:

1. **Do not guess or restart workers blindly.**
2. Navigate to the log search tool across the `sorrel-prod-*` index.
3. Run the targeted duplicate detection query:
   ```
   service=notifier msg="duplicate id"
   ```
4. Analyze the output to identify:
   - The message ID and originating service (usually `api`).
   - The rate of recurrence: Is a single upstream job posting identical booking IDs repeatedly, or are `notifier` workers failing to acknowledge messages off the queue, causing AWS to redeliver the same task repeatedly to both worker nodes?
5. Check worker logs around message ACK completions:
   ```
   service=notifier level=ERROR msg="failed to ack"
   ```
   If worker nodes process a message but crash right before issuing the queue acknowledgement, the message will re-appear on the queue after the visibility timeout, creating an endless loop of duplicate dispatches.
6. If a recent deploy introduced an acknowledgement regression or bad retry loop, **roll back** via the deploy tool. If upstream `api` is generating duplicated tasks, escalate triage to `api` owner (Ravi).

---

## 7. Rollback Procedure

For `notifier`, rollbacks are managed via the deploy tool.

```
 [Deploy Tool: Project "sorrel"]
               │
               ▼
   Select Service: "notifier"
               │
               ▼
 Select Prior Stable Deploy (d-xxxx)
               │
               ▼
   Click "Roll back to this"
               │
   ┌───────────┴───────────┐
   ▼                       ▼
Worker 1 drains        Worker 2 drains
current task           current task
   │                       │
Pulls old build        Pulls old build
   └───────────┬───────────┘
               ▼
   Verify Board & Logs (~3 mins)
```

1. Open the deploy tool and browse to project **sorrel**.
2. Select service **notifier**.
3. Review the deploy history to identify the last known good deploy ID (e.g., `d-3841`).
4. Select that version and click **"Roll back to this"**.
5. The deployment system will gracefully signal the two worker nodes per region. Workers will finish processing their current in-flight message before the process restarts with the prior build artifact. The rollover completes across regions in approximately three minutes.
6. Return to dashboard **Sorrel / notifier**:
   - Check that "messages delivered per minute" stabilizes.
   - Check that error rates decline to normal baselines.
7. Record the event in `#inc-live` providing the failing deploy ID and the target rollback deploy ID. Notify Tom during normal working hours, or page if the rollback fails to clear the issue.

---

## 8. Log Reference Sheet

Run these queries in the log search tool (`sorrel-prod-*`) constrained strictly to the window of the incident:

| Scenario | Search Query | Purpose |
|---|---|---|
| General Errors | `service=notifier level=ERROR` | Locates first stack traces and error occurrences |
| Deploy Verification | `service=notifier msg="started d-*"` | Confirms when worker nodes adopted a release build |
| Vendor API Faults | `service=notifier msg="vendor error" channel=*` | Isolates third-party provider error envelopes |
| Quota Exceeded | `service=notifier msg="quota"` | Identifies contracted rate or volume blocks |
| Worker Health | `service=notifier msg="worker stuck"` | Detects thread locks or timed-out worker tasks |
| Duplicates | `service=notifier msg="duplicate id"` | Traces repeat processing of identical payloads |
| SMS Provider Errors | `service=notifier msg="vendor error" channel=sms` | Extracts raw error status returned by Twilio |
| Email Provider Errors | `service=notifier msg="vendor error" channel=email` | Extracts raw error status returned by SendGrid |

---

## 9. Escalation and Ownership

- **Service Owner:** Tom (`notifier`)
- **Engineering Contributor:** Yuki
- **Secondary Backup:** Incident Commander Rotation
- **Platform Architecture / Queue Lead:** Kenji Sato

### Boundaries of Authority

- **On-Call Engineer:**
  - Can inspect metrics and execute log queries.
  - Can trigger service rollbacks to the prior deploy using the deploy tool.
  - Can monitor vendor status pages and log tickets.
  - Cannot alter commercial sending quotas, swap vendor master credentials, or delete queued records manually.
- **Service Owner (Tom):**
  - Authorizes Twilio and SendGrid plan adjustments and quota increases.
  - Manages provider API keys and webhook secret configurations.
  - Makes binding calls on notification content alterations or mass communication re-runs following an outage.
