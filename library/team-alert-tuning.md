# Alert tuning process

Date: 2024-06-03  
Owner: Kenji (platform)

This document describes how we review, modify, and retire production alerting rules across Sorrel's four services: web, api, payments, and notifier. 

Alert fatigue directly compromises incident response. When engineers are paged for non-actionable signals or noisy thresholds, real failures get missed or acknowledged slowly. Our goal is simple: an alert that pages on-call must represent an active customer problem or an irreversible condition requiring human intervention. Everything else belongs on a dashboard or in a ticket.

---

### 1. The Alert Tuning Lifecycle

Alert tuning is a continuous maintenance loop fed by on-call handovers, weekly incident reviews, and our on-call log.

```
+-------------------------------------------------------------+
|                     On-Call Rotation                        |
|  - Responds to paging alerts                                |
|  - Enforces single first move                               |
|  - Records entry in on-call log                             |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                     Weekly Handover                         |
|  - On-call engineer identifies noisy or late alerts         |
|  - Files ticket labelled 'alert-tuning'                     |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|             Monthly Alert Review (First Wednesday)          |
|  - Platform lead + Service owners review open tickets       |
|  - Inspect log metrics and count "no action" occurrences    |
|  - Decide: tune threshold, downgrade, or remove             |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                  Service Team Execution                     |
|  - Service engineering team writes rule PR                  |
|  - Normal review and deploy during standard daytime hours   |
+-------------------------------------------------------------+
```

---

### 2. Identifying Candidates for Tuning

Alerts should not be adjusted ad hoc in the middle of an incident. Instead, candidates for tuning are identified through the daily and weekly on-call log entries.

Per section 9.1 of the on-call handbook, every alert that fires requires a log entry:
`<date> <time JST> | <service> | <severity> | <first move> | <one sentence: what you saw and why you chose that move>`

From these entries, three distinct patterns require tuning:

1. **Repeated "no action" entries:** The alert fired, but nothing failed for customers and no internal risk was active. The on-call engineer correctly wrote it down and moved on.
2. **Late-firing alerts:** Customers reported an outage or degraded performance to support before the alert fired. The threshold is either too loose or measuring the wrong symptom.
3. **Flapping or noisy thresholds:** An alert fires and resolves repeatedly within minutes due to routine traffic variations (such as scheduled crawler activity or regular batch processing) without any real degradation.

Any engineer on rotation who identifies an alert matching these patterns must file a ticket.

---

### 3. Ticketing and the `alert-tuning` Label

Any alert that should be tuned gets a ticket with the label `alert-tuning`.

Do not bury alert feedback in chat threads, postmortem action items, or unformatted handover notes. If an alert requires attention from an engineering team, open a ticket in the platform project tracker immediately.

#### Ticket Requirements
Every ticket created with the `alert-tuning` label must include:
- **Rule identifier:** The exact rule name as defined in monitoring (for example, `web-4xx` or `notifier-queue-depth`).
- **Service:** web, api, payments, or notifier.
- **Service Owner:** Aiko (web), Ravi (api), Mei (payments), or Tom (notifier).
- **Symptom observed:** Why the current rule is unsatisfactory (noisy, unhelpful threshold, missing real impact, late warning).
- **Log evidence:** Direct references to lines in the on-call log or incident threads where the alert fired. Include timestamps in JST.
- **Proposed direction:** Whether the rule needs a tighter window, an altered percentage threshold, an exclusion for safe periodic patterns, demotion to a dashboard panel, or complete removal.

Tickets lacking log evidence or clear rule names will be sent back to the reporter before the monthly review meeting.

---

### 4. Monthly Alert Review

Tickets are reviewed on the first Wednesday of each month in the alert review.

The meeting is scheduled for 14:00 JST on the first Wednesday of every month. It is chaired by Kenji Sato (platform lead) and attended by the service owners—Aiko, Ravi, Mei, and Tom—along with platform team engineers (Sara) and interested service engineers (such as Daniel, Yuki, Priya, or Leo).

#### Agenda and Process
1. **Log Metric Aggregation:** The platform team generates a summary of all alert fires across `sorrel-prod-*` for the previous calendar month, categorized by service and first move (`roll back`, `read logs`, `check provider`, `page owner`, `no action`).
2. **Review of `alert-tuning` Tickets:** Each open ticket is evaluated against the monthly data.
3. **Decision Classification:** For each ticket, the group agrees on an action:
   - **Retain:** The alert is operating correctly; recent firings were genuine edge cases.
   - **Tune:** Adjust threshold values, duration windows, or scope filters (such as regional exclusions or specific HTTP route ignores).
   - **Downgrade to Dashboard:** Demote the rule from a paging alert to an unpaged visual metric on the service dashboard.
   - **Remove:** Delete the rule entirely.

---

### 5. The Ten "No Action" Rule

An alert that led only to 'no action' ten times in a month is downgraded to a dashboard or removed.

This rule is strictly applied during the monthly review. When an alert rule records ten or more firings within a single calendar month where the verified first move in the on-call log was `no action`, that rule loses its paging status. 

#### Rationales for Action
- **Downgrade to a dashboard:** Used when the underlying metric still provides diagnostic value during an active investigation, but does not justify interrupting an on-call engineer. The metric remains visible on the service board in the "Sorrel / Services" folder (for example, on "Sorrel / web" or "Sorrel / api"), but its paging trigger is removed.
- **Remove:** Used when the alert monitors an artificial condition or an architectural assumption that is no longer valid. If the metric regularly spikes without causing customer errors, latency issues, or downstream queue backlogs, the check is deleted entirely from our monitoring definitions.

#### Exceptions
Rules marked as "always" in section 14 of the handbook (such as `api-cross-tenant`, `payments-refund-duplicate`, or `payments-secret-scan`) are safety nets designed to prevent or catch irreversible harm (money moved wrongly, data exposed, secrets leaked). These rules do not fire under normal operations. If one of these rules fires erroneously, it points to a broken scanner pattern or response filter bug that must be resolved by engineering immediately, rather than silenced.

---

### 6. Implementation and Deploy Safeguards

Alert changes are made by the service owner's team, never during a night shift.

Modifying alert definitions is an engineering change to production configuration. It carries operational risk: an improperly scoped filter can silence critical failure notifications, while a syntax error can disable alerting pipelines entirely.

#### Implementation Rules
1. **Ownership:**
   - Changes to `web-*` rules are implemented by Aiko's team (Aiko, Priya).
   - Changes to `api-*` rules are implemented by Ravi's team (Ravi, Daniel).
   - Changes to `payments-*` rules are implemented by Mei's team (payments engineering, Leo).
   - Changes to `notifier-*` rules are implemented by Tom's team (Tom, Yuki).
   - Cross-cutting monitoring infrastructure, base alert templates, and notification pipelines are maintained by Kenji Sato and Sara.
2. **Review:** All pull requests altering alert definitions require review and approval from the relevant service owner or the platform lead before merging.
3. **Timing and Night Shifts:**
   - No alert rule modifications may be deployed between 22:00 and 07:00 JST.
   - If an alert is firing repeatedly through the night and waking on-call for benign reasons, the on-call engineer must acknowledge, document the behavior in the on-call log as `no action`, and file an `alert-tuning` ticket for daytime triage. 
   - An on-call engineer is never permitted to silence, edit, or delete an alerting rule during a night shift to stop pages.

---

### 7. Historical Decisions and Case Studies

To clarify how these principles apply in practice, below are examples of rule evaluations conducted during previous alert reviews.

#### Case 1: `web-4xx` Route Noise (April 2024 Review)
- **Problem:** `web-4xx` fired twelve times during April, primarily between 02:00 and 05:00 JST. All twelve on-call log entries recorded `no action`.
- **Findings:** A search-engine crawler was indexing outdated URLs from an archived business directory, causing bursts of 404 responses. Real users experienced zero page load degradation or booking failures. Origin latency and API error rates remained baseline.
- **Outcome:** Ten "no action" rule triggered. Aiko and Priya updated the route filters for `web-4xx` to exclude static marketing routes and legacy redirects, and adjusted the rule condition so night firings require confirmed customer reports via support tooling before generating a page.

#### Case 2: `notifier-queue-depth` Nightly Reminder Batch (May 2024 Review)
- **Problem:** `notifier-queue-depth` fired eight times during early morning hours in May.
- **Findings:** Between 02:00 and 04:00 JST, notifier's scheduler builds and enqueues reminder SMS and email messages for ap-northeast businesses. Queue depth routinely passed 1,000 items while worker delivery throughput remained steady at over 300 messages per minute. Oldest message age stayed under five minutes.
- **Outcome:** The alert was generating noise because it only looked at raw backlog volume rather than worker health. Tom and Yuki retained `notifier-queue-stalled` for zero throughput situations, and tuned `notifier-queue-depth` to evaluate oldest message age alongside depth before triggering a page.

#### Case 3: `api-partner-reject` Contract Boundaries (May 2024 Review)
- **Problem:** `api-partner-reject` fired five times for a single external integration partner syncing schedules.
- **Findings:** The partner consistently exceeded their contracted rate limit, receiving expected 429 Too Many Requests responses. The on-call engineers recorded `no action` because Sorrel's API was operating correctly and protecting core database pools. However, the alert paged at 03:30 JST.
- **Outcome:** Ravi and Daniel adjusted the rule to require sustained partner rejection across multiple partner IDs, and routed single-partner threshold violations directly to a partner operations ticket rather than the primary on-call rotation.

---

### 8. Review Schedule and Responsibilities Matrix

The table below outlines the responsibilities for tracking, evaluating, and applying alert changes across Sorrel:

| Role | Person / Group | Responsibilities |
|---|---|---|
| Platform Lead | Kenji Sato | Maintains alerting framework, schedules and chairs monthly review, tracks global alert counts. |
| Platform Engineer | Sara | Maintains dashboard synchronization, metrics pipeline health, and log metric query tools. |
| web Owner | Aiko (backup: Priya) | Owns rules for `web-*`. Implements threshold and filter PRs for web and edge monitoring. |
| api Owner | Ravi (backup: Daniel) | Owns rules for `api-*`. Implements threshold PRs for database pools, endpoints, and partner limits. |
| payments Owner | Mei (backup: Leo) | Owns rules for `payments-*`. Implements PRs for checkout, latency, and webhook monitoring. |
| notifier Owner | Tom (backup: Yuki) | Owns rules for `notifier-*`. Implements PRs for delivery queues, worker loops, and vendor limits. |
| Support Lead | Hana | Flags discrepancies where customer issues reached support before alerts fired. |
| On-Call Engineers | Active Rotation | Records accurate on-call log entries, identifies noisy rules, files tickets with `alert-tuning`. |

---

### 9. Checklists

#### On-Call Engineer: Filing an `alert-tuning` Ticket
- [ ] Verify that the alert did not represent a genuine customer failure or hidden risk (such as silent audit gap or secret exposure).
- [ ] Confirm the entry is recorded in the on-call log with the correct first move and rationale.
- [ ] Collect the exact rule name from the monitoring alert line.
- [ ] Capture the start and end timestamps in JST.
- [ ] Open a ticket with the label `alert-tuning`.
- [ ] Tag the service owner (Aiko, Ravi, Mei, or Tom) in the ticket description.

#### Service Team: Executing an Alert Change
- [ ] Confirm the change was approved during the monthly alert review or in direct daytime coordination with Kenji Sato.
- [ ] Draft the configuration update in the monitoring repository.
- [ ] Verify that the change only affects the intended service and does not weaken safety-net rules marked "always".
- [ ] Obtain review and approval from the service owner.
- [ ] Deploy the change during standard working hours (between 07:00 and 22:00 JST, avoiding Friday afternoons after 16:00).
- [ ] Post confirmation of the update in `#inc-live` or the engineering announcement channel.
- [ ] Close the associated `alert-tuning` ticket.
