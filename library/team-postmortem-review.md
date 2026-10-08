# Postmortem review meeting

Last updated: 2026-03-16  
Owner: Kenji Sato (platform)

This page describes how the engineering team reviews incident postmortems at Sorrel. The goal of the review meeting is to examine past incidents, understand the systemic conditions that allowed them to occur, and commit to concrete preventative work.

---

## 1. Meeting schedule and attendance

The postmortem review meets every Thursday at 16:00 JST and is run by the platform team. 

The meeting operates on a strict time allocation:
- Each postmortem gets 30 minutes; the service owner attends.
- Meetings are capped at two postmortems (60 minutes total). If more than two reviews are queued in a single week, Kenji prioritises them based on severity and customer impact, carrying remaining drafts to the following Thursday.

### Attendance expectations

| Role | Person / Group | Attendance | Responsibility |
|---|---|---|---|
| Meeting Chair | Kenji Sato (platform lead) | Required | Keeps time, enforces blameless framing, ensures action items are complete. |
| Operational Reviewer | Sara (platform engineer) | Required | Reviews infrastructure, cloud provider dependencies, and telemetry changes. |
| Affected Service Owner | Aiko (`web`), Ravi (`api`), Mei (`payments`), or Tom (`notifier`) | Required | Attends for their service's postmortem; presents the timeline and owns follow-up work. |
| Service Engineers | Priya (`web`), Daniel (`api`), Leo (`payments`), or Yuki (`notifier`) | Optional | Context providers for technical deep-dives on service logic. |
| Support Lead | Hana (support lead) | Recommended | Provides context on customer support tickets, business feedback, and user perception. |
| Incident Commander | Engineer who led the `#inc-live` coordination | Recommended | Clarifies communication timelines and external status page postings. |

---

## 2. Thresholds: When a postmortem is required

Per section 9.2 of the On-Call Handbook, postmortems must be written and submitted for review under the following conditions:

1. **All P1 incidents**:
   - Customers could not book, pay, sign in, or receive confirmations at scale.
   - Money moved wrongly (duplicate charges, erroneous refunds, payout calculation failures).
   - Customer data was exposed or records were deleted without authorisation.
   - An entire region or service experienced an outage.
2. **Specific P2 incidents**:
   - The degraded state persisted for more than one continuous hour.
   - The same underlying failure condition repeated twice within a rolling seven-day window.

Draft documents must be placed in the shared drive under `Postmortems` within 5 working days of the incident's resolution. 

---

## 3. Preparation and structure

The author of the postmortem is typically the on-call engineer who responded, supported by the service owner. Before the document enters the Thursday review, it must follow the standard five-section format.

### Required sections

1. **Summary**: A concise description of what failed, the duration from initial trigger to mitigation, the customer-facing impact, and the severity assigned.
2. **Impact**: Exact figures broken down by category:
   - *Customers*: Number of failed bookings, degraded sessions, or missed reminders.
   - *Money*: Total volume of affected checkouts, delayed settlements, or incorrect transaction entries.
   - *Data*: Exposure scope, audit log omissions, or records affected.
3. **Timeline (JST)**: A chronological sequence reconstructed from the `#inc-live` incident thread, deploy histories, provider status updates, and service logs. Every timestamp must be recorded in Japan Standard Time (JST).
4. **What went well / What went badly / Where we got lucky**:
   - What operational tooling or playbooks functioned as intended.
   - What tooling, documentation, or architecture hindered mitigation.
   - Incidental factors that prevented greater severity (e.g., quiet traffic windows, early detection via unrelated metrics).
5. **Action items**: Corrective work directly targeted at the technical and procedural failure modes discovered during analysis.

---

## 4. The blameless review philosophy

Sorrel approaches every operational incident from the premise of blameless postmortems. Postmortems are blameless: the question is what made the mistake easy and hard to notice.

### Framing principles

- **System design over human failure**: We assume every engineer acted in good faith with the information available to them at the time. Saying an engineer "missed a check" or "entered the wrong value" is a failure of system design, not personal diligence. Why was that input unvalidated? Why was there no guardrail?
- **Visibility and detection**: If bad code, bad configuration, or an external dependency degraded our service, why did alerts not trigger sooner? Was the alerting rule misconfigured? Did the alert line fail to expose the root symptom?
- **Language standards**: Avoid accusatory terms. Focus on causal chains rather than individual decisions:

| Instead of asking... | We ask... |
|---|---|
| "Why did the deployer miss the broken schema?" | "What made the schema change appear safe in local verification, and why did the migration step lack automated compatibility verification?" |
| "Why did on-call take 15 minutes to run the first move?" | "What was missing from the alert line that forced the engineer to search dashboards rather than knowing the first action immediately?" |
| "Who approved the configuration merge?" | "What made the dangerous configuration value easy to submit without flagging review guardrails?" |

---

## 5. Standard agenda (30 minutes per incident)

Kenji chairs the meeting and enforces the clock:

```
[00:00 - 05:00]  Context and Timeline Verification
[05:00 - 15:00]  Technical and Tooling Deep Dive
[15:00 - 25:00]  Action Item Definition and Assignment
[25:00 - 30:00]  Final Sign-off and Owner / Date Commitments
```

### 00:00 - 05:00: Context and timeline verification
The service owner walks through the high-level summary and the timeline. 
- Are the timestamps reconciled between `#inc-live`, the log search tool (`sorrel-prod-*`), and deploy metadata?
- Was the initial severity classification correct under section 2 of the handbook?
- If status page updates were required (for public-facing P1s), did the incident commander update `status.sorrel.app` within the 20-minute window?

### 05:00 - 15:00: Technical and tooling deep dive
The group discusses the failure mode. Discussion focuses on our standard operational paths:
- **Alert quality**: Did the alert line follow the required structure (service, symptom, duration, error rate or latency, customer reports, deploy age)? If the alert was late, or if it fired when no customer was harmed, should the rule in section 14 be adjusted?
- **First move evaluation**: Was the first action taken aligned with the five defined moves (roll back, read logs, check provider, page owner, no action)? 
  - If a rollback occurred, did it restore stability within the expected window?
  - If an outside provider was involved (stripe, twilio, sendgrid, cloudflare, aws), did the responder check the provider's status page or API errors before touching internal systems?
  - If data exposure or financial discrepancies occurred, was the service owner paged immediately without delay?
- **Failure classification**: Which known failure mode from section 7 of the handbook does this map to? Was it a bad deploy, an external dependency failure, a connection pool saturation, or an unhandled edge case?

### 15:00 - 25:00: Action item definition
The review transitions into engineering solutions. Action items must address:
- Reducing the probability of the defect happening again.
- Making the defect detectable earlier in the deployment or operational lifecycle.
- Speeding up mitigation for the on-call engineer during future shifts.

### 25:00 - 30:00: Sign-off and commitments
Kenji leads the final review of the generated action items. Action items need an owner and a date before the meeting ends.

---

## 6. Action item requirements

Vague or aspirational action items are rejected during the meeting. An action item cannot simply be "improve monitoring" or "add tests." It must describe a specific deliverable, name a single individual as owner, and include an agreed target completion date.

### Action item criteria

1. **Single owner**: Every item is assigned to one engineer (e.g., Daniel, Yuki, Leo, Priya, Sara), not a team or shared alias.
2. **Deterministic due date**: Specific calendar date agreed upon by the owner and the service owner.
3. **Traceability**: The item must link directly to an observation made in the "What went badly" or timeline analysis.

### Standard action item table template

Every postmortem document must conclude with this table populated before Kenji accepts the postmortem as closed:

| ID | Category | Description | Owner | Target Date | Status |
|---|---|---|---|---|---|
| AI-01 | Prevent | Add strict input validation schema to checkout submission endpoint in `payments`. | Leo | 2026-03-30 | Open |
| AI-02 | Detect | Tune alert rule `api-pool` threshold to fire at 85 % saturation over 5 minutes. | Daniel | 2026-03-24 | Open |
| AI-03 | Mitigate | Add log search query for regional DNS timeouts to runbook section 15.3. | Sara | 2026-03-27 | Open |
| AI-04 | Audit | Reconcile missing audit log entries caused by database write worker failure. | Ravi | 2026-04-03 | Open |

---

## 7. Reviewing typical failure modes

To maintain consistency, the review team checks incidents against the architectural and operational patterns defined in the service runbooks.

### Web failures (`web`)
- **Review focus**: Static asset delivery, Cloudflare CDN configuration, node memory usage, and server-side render performance.
- **Key questions for Aiko**:
  - If assets failed, was it a missing CDN purge or an upload failure to object storage during the deploy?
  - Did node restarts trigger `web-node-restart` alerts, and were they caused by memory leaks on specific render paths?
  - If admin bulk actions took place, was the dual-approval workflow bypassed or properly recorded in the logs?

### API failures (`api`)
- **Review focus**: Database connection pools, slow queries, cross-tenant isolation, partner limits, and regional routing.
- **Key questions for Ravi**:
  - If the database connection pool saturated (`api-pool`), what query or job held connections open?
  - If requests in one region failed (ap-northeast, us-east, or eu-west), did the team confirm AWS regional health before investigating application code?
  - If a partner integration caused degradation, was their contracted limit enforced, or did unthrottled traffic exhaust service capacity?
  - If an audit log gap occurred (`api-audit-gap`), what caused the audit writer to drop events while request traffic continued?

### Payments failures (`payments`)
- **Review focus**: Stripe connectivity, webhook processing, refund duplication, and checkout validation.
- **Key questions for Mei**:
  - On checkout failure alerts, did responders check the latency panel to separate Sorrel latency from Stripe's response times?
  - If duplicate charges or refunds occurred, was Mei paged immediately as a P1 per the escalation policy?
  - Were webhook retries handled idempotently without corrupting the payment state in api?
  - Did any live payment provider keys leak into `sorrel-prod-*` log streams or error traces?

### Notifier failures (`notifier`)
- **Review focus**: Queue depth vs. delivery throughput, SendGrid and Twilio API responses, template rendering, and duplicate messages.
- **Key questions for Tom**:
  - Did an alert for high queue depth fire during the expected overnight batch window (02:00–04:00 JST for ap-northeast reminders) when deliveries were still proceeding normally?
  - If messages stalled, were queue workers hung or did the outside vendor enforce an unhandled rate limit?
  - If duplicate notifications reached customers, what caused message IDs to be reused within the 24-hour window?

---

## 8. Closing and archive process

A postmortem review is considered complete only when:
1. The postmortem document has been reviewed in the Thursday session.
2. The blameless timeline has been validated against production logs and `#inc-live` records.
3. All action items have an assigned individual owner and an explicit delivery date.
4. The service owner (Aiko, Ravi, Mei, or Tom) gives final approval on the text.
5. Kenji moves the document from the `Drafts` workspace to the official `Postmortems` archive in the shared drive.

Platform tracks outstanding action items across all postmortems. Kenji reviews the status of open items weekly, and any overdue action item is raised directly with the owning service lead before new engineering deploys are prioritised.
