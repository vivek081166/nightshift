# How to read the notifier queue panels

Last updated: 2025-01-20  
Owner: Yuki (notifier)

This guide walks through the queue-monitoring panels on the "Sorrel / notifier" dashboard in the metrics tool. It is written for engineers on the Sorrel primary rotation, secondary engineers, and platform engineers shadowing the shift.

notifier is decoupled asynchronously from the rest of the product: web, api, and payments do not wait for email receipts or SMS alerts to send before finishing their own work. Instead, other services place a message payload into notifier's queue, and our worker nodes pop items, resolve templates, and deliver them to our outside communication vendors. 

Because messages accumulate whenever production activity spikes or downstream delivery slows, looking at a single number like raw backlog size can easily mislead you. A large queue is often completely healthy; a small queue can sometimes hide stuck workers. Use the steps and rules below to read the graphs accurately before deciding on an on-call move.

---

## 1. The Core Rule: Flow Over Inventory

The single most common mistake during overnight shifts is reacting purely to the raw queue depth.

> **Depth alone means nothing; compare 'added per minute' with 'delivered per minute'.**

Queue depth is simply inventory. If thousands of items enter the queue at once, depth climbs abruptly. As long as the rate of delivery matches or exceeds the rate of entry, the queue is operating as designed.

```
+-----------------------------------------------------------------------+
|  Board: "Sorrel / notifier" -> Panel 1: Throughput & Queue Depth      |
|                                                                       |
|  [Queue Depth]               -------/ \------                         |
|                                    /   \                              |
|  [Added per min]    _/\___________/     \__________________________   |
|  [Delivered per min]    _/\___________/\___________________________   |
+-----------------------------------------------------------------------+
```

When evaluating Panel 1:
1. **Compare the slopes:** If **Queue depth** is rising, look immediately at **Messages added per minute** and **Messages delivered per minute**.
2. **Healthy drain:** If **Messages added per minute** surged (for example, due to an automated batch) but **Messages delivered per minute** is high, the backlog will clear naturally once the influx stops. No intervention is required.
3. **True stall:** If **Queue depth** is flat or rising, **Messages added per minute** is non-zero, but **Messages delivered per minute** drops to near zero or stays flat at zero, workers are not draining messages.

---

## 2. Key Panels and What They Show

The "Sorrel / notifier" board contains several dedicated graphs. Focus on these panels in order when investigating delivery anomalies:

| Panel Name | Metric Tracked | Normal State | Warning State |
|---|---|---|---|
| **Queue Depth** | Total pending messages on the primary queue | Fluctuates between 0 and 300 during the day; climbs during the night batch | > 1,000 for more than 20 minutes outside batch hours |
| **Throughput (In vs Out)** | Overlay: `messages_added_per_minute` vs `messages_delivered_per_minute` | Influx matches delivery over rolling 15-minute windows | Delivery stays at 0 while added is > 0 |
| **Oldest Message Age** | Age in minutes of the item at the head of the queue | Under 5 minutes | Increasing linearly; > 30 minutes |
| **Delivery Outcomes** | Status per channel: vendor acceptance, bounces, failures | > 99% accepted across email and SMS | Elevated 4xx/5xx vendor response codes |
| **Vendor Response Codes** | Explicit HTTP response codes from twilio and sendgrid | 200/202 responses | 429 (quota), 500/503 (vendor outage) |
| **Duplicate Detection** | Messages sent with an ID already observed in the past 24 hours | 0 | Spike (> 100 in 10 minutes) |

---

## 3. Detecting Worker Stalls

A genuine failure in notifier's processing pipeline shows up when the backlog ceases to move forward.

> **Oldest message age above 30 minutes while delivered per minute is zero means the workers are stuck.**

When worker nodes hang, crash without rebooting cleanly, or hit a blocking dependency that prevents picking up new jobs, messages sit stationary. The top message remains un-popped, meaning the age of the oldest message increases minute by minute in lockstep with wall-clock time.

### Triage checklist for stuck workers:
1. **Confirm the symptom on the board:**
   - **Messages delivered per minute** is strictly `0`.
   - **Oldest message age** exceeds 30 minutes and is trending steadily upward.
   - **Messages added per minute** shows items are still being queued by other services.
2. **Check recent deploys:** Check the deploy history in the deploy tool for project "sorrel", service "notifier". Note the age of the last deploy.
   - If notifier was deployed within the last 30 minutes, this fits the pattern of a bad release (for example, a syntax regression or broken queue connection logic in the worker loop). In this case, your first move is **roll back** to the previous deploy.
3. **Read logs:** If there has been no recent deploy, your first move is **read logs**.
   - Query the log search tool: `service=notifier level=ERROR` over the start of the window.
   - Look for worker loop errors: `service=notifier msg="worker stuck"` or `service=notifier msg="worker idle"`.
   - Check if the worker processes crashed due to memory or execution timeouts across the three worker nodes in each active region (`ap-northeast-1`, `us-east-1`, `eu-west-1`).

---

## 4. The Nightly Reminder Batch (JST)

A recurring point of confusion for engineers on the night shift is the early-morning queue spike.

> **During the nightly reminder batch, depth commonly reaches 1,000 to 1,500 and drains by 06:00 JST.**

notifier runs a scheduler that generates next-day booking reminders for our primary market in Japan. Here is how that pattern behaves:

* **02:00–04:00 JST:** The scheduler runs across `ap-northeast` bookings. It scans api for appointments scheduled for the upcoming day and enqueues confirmation and reminder payloads in bulk.
* **Peak accumulation:** Depth rapidly builds, commonly peaking between 1,000 and 1,500 messages on the primary queue. 
* **Worker drain:** The worker nodes process these items sequentially, rendering templates and handing them to vendors. Because this is a scheduled influx, **Messages delivered per minute** will remain elevated and active while the queue works down.
* **06:00 JST:** The backlog typically drains completely back to baseline before the Japanese morning peak starts at 07:00 JST.

```
00:00 JST       02:00 JST               04:00 JST             06:00 JST
  |               |                       |                     |
--+---------------+-----------------------+---------------------+------>
  [Baseline: ~50]  [Scheduler fires]       [Peak: 1,000 - 1,500] [Drained]
                   Added/min surges        Delivered/min high    Queue returns to <200
```

### Shift handling during the night batch:
If an alert rule evaluates notifier depth overnight:
- Verify that **Messages delivered per minute** is high and steady.
- Verify that **Oldest message age** remains controlled (messages are flowing through, even if deep in the stack).
- If delivery is healthy and the queue is draining steadily toward the 06:00 JST target, this represents standard product behaviour: choose **no action**, record the entry in the on-call log, and move on.

---

## 5. Separating Internal Issues from Outside Providers

When **Messages delivered per minute** drops, do not assume our worker nodes are broken without looking at the vendor outcome panels. notifier depends directly on two outside providers:
- **sendgrid** for transactional email (receipts, schedule confirmations, notifications to businesses).
- **twilio** for SMS (appointment reminders, one-time sign-in passcodes).

Check the **Delivery Outcomes per channel** and **Vendor response codes** panels:

### Scenario A: Vendor errors or rate limits
- **Symptom:** **Messages delivered per minute** drops, but **Oldest message age** does not climb because messages are failing or retrying rapidly, or vendor response panels show 4xx/5xx spikes.
- **Provider status:**
  - For SMS: Check `status.twilio.com`.
  - For Email: Check `status.sendgrid.com`.
- **First move:** If the alert points directly at vendor API rejections or vendor status incidents, choose **check provider**.
- **Important constraint:** If sendgrid or twilio returns quota errors (`service=notifier msg="quota"`), notifier leaves items in the retry loop. Raising provider account tier quotas or sending allocations involves commercial purchasing decisions owned strictly by Tom. On-call engineers do not modify provider account tiers or sending configurations.

### Scenario B: Worker crashes vs vendor rejections
- Open log search: `service=notifier msg="vendor error" channel=sms|email`.
- If the logs show clear remote gateway errors (e.g., HTTP 502/503/504 from the vendor API), the issue is outside our infrastructure.
- If the logs show internal render failures (e.g., `TemplateRenderError` or database lookups timing out), the issue lies within notifier or api.

---

## 6. Duplicate Detection Panel

The dashboard includes a panel tracking **Duplicate detection: messages sent with an ID already seen in the last 24 hours**.

- **What it tracks:** Every outgoing message carries a deterministic UUID tied to the booking and the event trigger. If notifier tries to push a payload with an identifier that was already processed within the rolling 24-hour cache window, the counter increments.
- **Why it matters:** Duplicate SMS reminders and email receipts frustrate customers and prompt support tickets to Hana's team.
- **What to look for:** A sudden spike (> 100 duplicates over a 10-minute window) indicates either an upstream service (such as api) repeatedly enqueuing duplicate jobs, or worker nodes failing to acknowledge queue receipts after successful vendor dispatch.
- **First checks:**
  1. Open logs: `service=notifier msg="duplicate id"`. Identify the producing service generating the duplicate submissions.
  2. Compare against recent deploys of notifier or api.

---

## 7. Escalation and Ownership

When handling queue-related incidents, use the standard escalation pathways:

- **Service Owner:** Tom (notifier owner).
- **Engineers:** Yuki (notifier engineer).
- **Secondary / Backup:** The incident commander rotation.

### When to page Tom:
- Customer harm that cannot be undone has occurred (e.g., thousands of duplicated messages blast customer phones, or critical sign-in channels are permanently discarded).
- A sending limit or commercial account threshold requires an immediate administrative decision.
- An incident commander determines that an unresolved P1 queue issue has run past 30 minutes without relief from the initial triage move.

For routine backlog clearings where delivery metrics remain healthy, avoid unnecessary pages. Document the behavior, verify the queue trend, and log the line in the on-call register.
