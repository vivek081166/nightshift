# On-call onboarding

Last updated: 2024-01-15  
Owner: Kenji (platform)

This document outlines the path for engineers joining the primary on-call rotation at Sorrel. The goal of this process is not to test memorisation or expect anyone to fix subtle core system bugs at 03:00 JST. Rather, it ensures that when an alert fires, you know how to assess impact calmly, pick an unambiguous first move, communicate clearly in incident channels, and escalate to the correct owner when boundaries require it.

---

## 1. Overview of the onboarding path

Joining the rotation involves four sequential stages:

1. **Access provisioning and local setup:** Obtaining access to production telemetry and operations tools at least one full week prior to starting operational duties.
2. **Shadow shifts (two full rotations):** Observing an experienced primary engineer through two complete weekly shifts (Monday 10:00 JST to Monday 10:00 JST).
3. **The practical pager drill:** Running a planned, simulated P2 incident drill end to end with Sara.
4. **Final handbook review and rotation scheduling:** Completing the remainder of the checklist, completing an end-to-end read of the On-Call Handbook, and entering the schedule.

```
+-----------------------------------+
| 1. Access Setup                   |
|    Telemetry, deploy tool, paging |
+-----------------+-----------------+
                  |
                  v
+-----------------------------------+
| 2. Two Shadow Shifts              |
|    Observe triage, paging, chat   |
+-----------------+-----------------+
                  |
                  v
+-----------------------------------+
| 3. Practical Pager Drill          |
|    Simulated P2 exercise w/ Sara  |
+-----------------+-----------------+
                  |
                  v
+-----------------------------------+
| 4. Handbook Review & Sign-off     |
|    Item 14 read-through complete  |
+-----------------------------------+
```

---

## 2. Onboarding checklist

Work through these items in order. The checklist contains exactly 14 items; every box must be checked before your first solo primary shift is scheduled.

- [ ] **Item 1: Request log search and dashboard access.** Request read permissions for the log search tool (index pattern `sorrel-prod-*`) and the metrics tool (folder "Sorrel / Services") at least a week before your first shadow shift (see the page "Access requests for on-call").
- [ ] **Item 2: Set up the paging tool and verify notifications.** Install the paging application on your mobile device. Configure notification rules to override system focus/do-not-disturb modes for critical alerts.
- [ ] **Item 3: Execute a paging self-test.** Trigger a test page from the paging tool to confirm your device alerts reliably and you can acknowledge it within five minutes.
- [ ] **Item 4: Verify deploy tool read and rollback access.** Confirm you can sign in to the deploy tool for project "sorrel", view past deploy records, and inspect deploy history across services.
- [ ] **Item 5: Join operational communication channels.** Join `#inc-live` in chat, bookmark the incident channel guidelines, and join the internal platform announcements channel.
- [ ] **Item 6: Verify status page management access.** Ensure you have an account set up in our status tool for updating status.sorrel.app, and confirm you know where customer-facing templates live.
- [ ] **Item 7: Review the service architecture and dependencies.** Review the relationship between the four services: `web`, `api`, `payments`, and `notifier`. Review the dependency chain and where outside providers connect.
- [ ] **Item 8: Familiarise yourself with third-party provider dashboards.** Bookmark the external status pages for our five dependencies: stripe, twilio, sendgrid, cloudflare, and aws.
- [ ] **Item 9: Complete first shadow shift.** Shadow an active primary engineer for one full shift (Monday 10:00 JST to the following Monday 10:00 JST). Attend all shift handovers.
- [ ] **Item 10: Complete second shadow shift.** Shadow a second full weekly shift. Observe any triage that occurs, review lines entered into the on-call log, and inspect postmortem drafts.
- [ ] **Item 11: Complete the pager drill with Sara.** Schedule and complete a simulated P2 incident exercise end to end.
- [ ] **Item 12: Review postmortem archives.** Read at least five postmortems in the shared drive folder "Postmortems" from the past six months to understand blameless analysis and timeline construction.
- [ ] **Item 13: Review permissions and escalation boundaries.** Read Section 17 of the handbook to ensure you understand strictly what on-call engineers cannot do (e.g., rotating production credentials, manually altering customer records, changing partner limits).
- [ ] **Item 14: Read the On-Call Handbook end to end.** Read the entire handbook from revision header to glossary without skipping sections.

---

## 3. Tooling and access setup

Get log search and dashboard access at least a week before the first shadow shift (see "Access requests for on-call"). Do not leave permission tickets until the week your shadow shift begins; provisioning involves identity team approvals that cannot be rushed during active incidents.

### 3.1 Telemetry and logs

Inspect the production log search index (`sorrel-prod-*`). Verify that you can run structured queries using service tags:

```
service=web
service=api
service=payments
service=notifier
```

Ensure you can filter by log levels (`level=ERROR`) and sort chronologically ascending to isolate the first error of an incident window rather than the loudest one. Note that customer details such as names, phone numbers, and physical addresses are masked in logs, while booking ids and customer ids remain visible for tracing.

### 3.2 Metrics and dashboards

Confirm you can open each service board under the "Sorrel / Services" directory in the metrics tool:

| Service | Primary Board Name | Key Panels to Verify |
|---|---|---|
| `web` | Sorrel / web | Status breakdown (2xx/3xx/4xx/5xx), p95 load time, CDN edge errors, node memory/restarts |
| `api` | Sorrel / api | Latency percentiles, database pool usage, replica lag, SLO error budget burn, audit log writes |
| `payments` | Sorrel / payments | Checkout success/failure, internal checkout latency vs provider response latency, refunds panel |
| `notifier` | Sorrel / notifier | Queue depth, messages added vs delivered per minute, delivery outcomes by channel, duplicate panel |

---

## 4. The shadowing process

New engineers shadow two full shifts before taking a primary shift. A shadow shift lasts a full operational cycle: starting Monday at 10:00 JST and running until the handover on the following Monday at 10:00 JST.

### 4.1 What to do during a shadow shift

As a shadow, you do not carry the primary pager, but you follow everything the primary does:

- **Follow all pages:** When the primary is paged, follow the alert line in the paging tool. Check whether you would have assessed the severity as P1, P2, or P3 based on customer impact.
- **Observe `#inc-live`:** Watch how threads are opened, how alert lines are pasted, and how updates are posted every 15 minutes for P1s or 30 minutes for P2s.
- **Follow first moves:** When an alert fires, compare your assessment of the five actions (roll back, read logs, check provider, page owner, no action) with the move the primary engineer selects.
- **Participate in shift handover:** Attend the weekly handover at 10:00 JST on Monday. Ensure you see how open issues, ongoing provider degradations, and pending tickets are transferred between engineers. Handover is only complete when the incoming engineer writes "taken" in the active incident thread.

---

## 5. The practical pager drill with Sara

After shadowing, they do a pager drill with Sara: a fake P2 page at an agreed time, acknowledged and handled end to end.

This drill tests operational mechanics in real time without putting customer booking flows or transaction pipelines at risk. It is scheduled during normal working hours.

### 5.1 Drill mechanics

1. **Scheduling:** Contact Sara to arrange a one-hour window. Ensure you are at your laptop, connected to production monitoring, and have your paging application open.
2. **The trigger:** Sara triggers a simulated alert that delivers a synthetic P2 alert line to your paging schedule.
3. **Acknowledgment:** Acknowledge the page within 15 minutes (the P2 SLA).
4. **Incident thread setup:**
   - Open a dedicated mock incident thread in `#inc-live`.
   - Post the full alert line at the top.
   - State the severity (P2) and the customer impact clearly.
   - State your chosen first move before performing secondary investigations.
5. **Investigation workflow:**
   - Investigate the synthetic symptom across the relevant service dashboard in the metrics tool.
   - Run the appropriate query in the log search tool to locate the initial failure timestamp.
   - Identify whether the simulated issue stems from a recent service deploy, an outside dependency degradation, or internal resource exhaustion.
6. **Simulated communications:**
   - Write regular incident updates in the thread at the required cadence (every 30 minutes for a P2).
   - If an escalation boundary is reached during the scenario (for instance, data requiring restoration from backups or partner rate limit changes), practice identifying the correct service owner to contact:
     - `web`: Aiko
     - `api`: Ravi
     - `payments`: Mei
     - `notifier`: Tom
7. **Resolution and logging:**
   - Close the thread once the simulated root trigger is mitigated.
   - Format an entry for the on-call log according to the strict syntax:
     `<date> <time JST> | <service> | <severity> | <first move> | <one sentence summary>`
   - Review the exercise with Sara to discuss timing, telemetry navigation, and logging accuracy.

---

## 6. Core principles and operational boundaries

During onboarding, pay close attention to operational limits. As an on-call engineer, your job is to halt active harm and stabilise the platform, not to perform ad-hoc production architectural work in the middle of the night.

### 6.1 The five actions

Every alert gets one first move recorded in the on-call log. Always determine which action applies based on what the alert line states:

- **roll back:** Undo the most recent deploy, when that deploy is recent enough to be the cause. Deploys are small and frequent; bad deploys typically surface within the first half hour when traffic hits the new code. Note that a past rollback was performed on api prior to the release tooling migration.
- **read logs:** Go and read the service's own output, when nobody knows yet what happened. Look for the earliest error in the time window rather than the highest volume error.
- **check provider:** Look at an outside service we depend on, when the alert already points at one. External dependencies include stripe, twilio, sendgrid, cloudflare, and aws.
- **page owner:** Wake the person who owns this service, when something has already happened that you cannot undo—data seen, money moved, accounts deleted—or when somebody has to make a decision you are not allowed to make.
- **no action:** Write it down and move on, when nothing has failed and no customer is affected. Record the event in the on-call log so alerts firing unnecessarily can be tuned during business hours.

### 6.2 Permissions matrix

Be explicitly aware of what you are permitted to do during an incident versus what requires waking an owner or escalating to the incident commander:

| Action / Responsibility | On-call primary | Service owner | Incident commander | Support lead |
|---|---|---|---|---|
| Read metrics and logs | Allowed | Allowed | Allowed | Restricted |
| Roll back web or notifier to previous deploy | Allowed | Allowed | Allowed | Not allowed |
| Open incident thread in `#inc-live` | Allowed | Allowed | Allowed | Not allowed |
| Stop unannounced synthetic load test | Allowed | Allowed | Allowed | Not allowed |
| Update status.sorrel.app | Not allowed | Not allowed | Allowed | Not allowed |
| Rotate production credentials / API keys | Not allowed | Allowed (Mei, etc.) | Not allowed | Not allowed |
| Modify partner contracted request limits | Not allowed | Allowed (Ravi) | Not allowed | Not allowed |
| Delete or restore customer data from backup | Not allowed | Allowed (Aiko, Ravi) | Not allowed | Not allowed |
| Contact customers directly regarding issues | Not allowed | Not allowed | Not allowed | Allowed (Hana) |

### 6.3 Severity guidelines

| Severity | Customer Experience & System State | Response Expectations |
|---|---|---|
| **P1** | Widespread inability to book, checkout, sign in, or receive confirmations. Money moving wrongly (duplicate charges, erroneous refunds). Customer data exposure or cross-tenant leakage. Full service or regional failure. | Acknowledge in 5m. Open thread in `#inc-live` within 10m. Incident commander paged if open >15m. Update status page in 20m if customer-visible. Postmortem within 5 working days. |
| **P2** | Degradation affecting a minority of customers, one specific endpoint, or one region. Noticeable latency while requests complete. Failure of internal safety nets (audit logs stopped, backup delays) while user requests still succeed. | Acknowledge in 15m. Open thread in `#inc-live`. Hand over cleanly at shift change if unresolved. Postmortem if lasting >1h or repeating twice in a week. |
| **P3** | Metric shifted with zero customer impact and zero user-facing errors. Harmless background patterns (e.g., crawler traffic bursts, normal webhook retries). | Acknowledge in 1h (or next working day). Write one line in the on-call log. Open a ticket for the owning team if alert requires tuning. |

---

## 7. Service ownership reference

When escalating or transferring decisions during an incident, contact the designated service owners:

- **web:** Owned by Aiko. Covers server-rendered templates, CDN asset delivery, client script errors, and the internal admin tool. (Admin tooling inquiries may also involve Priya or support escalation with Hana).
- **api:** Owned by Ravi. Covers booking state engines, availability search, database connection pools, regional data layers, partner API thresholds, and audit logging. (Engineering discussions may involve Daniel).
- **payments:** Owned by Mei. Covers credit card processing via stripe, webhook ingestion, charge capture, refunds, and weekly payouts. (Engineering discussions may involve Leo).
- **notifier:** Owned by Tom. Covers message dispatch pipelines, worker pools, template processing, SMS via twilio, and transactional email via sendgrid. (Engineering discussions may involve Yuki).
- **Platform infrastructure:** Led by Kenji Sato, with Sara supporting platform automation, tooling, and alerting setups.

---

## 8. Practical shift tips

- **Check the change calendar:** Before your shift starts on Monday at 10:00 JST, check for planned provider maintenance windows or scheduled game days.
- **Quiet night trends:** Keep in mind that between 02:00 and 04:00 JST, notifier's scheduler queues the next day's reminder batch for ap-northeast-1. Queue depth climbing during this window while delivery rates remain steady is expected behaviour and does not require intervention.
- **Rest policy:** If you spend more than two hours handling an overnight incident, take the following morning off. This is mandatory team policy to prevent fatigue and ensure operational safety.

Once all 14 checklist items are complete—culminating in reading the On-Call Handbook end to end—notify Kenji to confirm your readiness for the live primary rotation.
