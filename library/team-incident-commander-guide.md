# Incident commander guide

Last updated: 2026-01-12  
Owner: Kenji Sato (platform)

This guide defines how the incident commander (IC) role functions at Sorrel. It sits alongside the On-Call Handbook (revision 2026-10-07a) and documents the operational boundaries, communication cadence, handoff mechanics, and post-incident responsibilities for anyone holding the IC pager.

---

## 1. Scope and purpose

Sorrel runs four core services: `web`, `api`, `payments`, and `notifier`. On-call engineers act first to arrest damage, contain failure domains, and determine immediate operational moves according to our five actions (roll back, read logs, check provider, page owner, no action). 

When an incident escalates into a prolonged P1, technical troubleshooting and coordination cannot effectively be done by the same brain. The incident commander steps in to run the response structure so that the primary on-call engineer and service owners can focus entirely on technical mitigation.

### Core mandate

The commander keeps the timeline, updates the status page, decides who talks to whom, and calls the incident over; the commander does not debug.

If you find yourself reading logs in `sorrel-prod-*`, checking connection pool metrics, or inspecting stack traces while wearing the IC hat, you are vacating your post. Step back immediately and direct those inquiries to the primary engineer or the service owner.

---

## 2. Escalation and paging

The incident commander rotation is paged for any P1 still open after 15 minutes.

Our paging tool maintains the "Incident Commander" schedule as a separate escalation tier alongside the "Sorrel primary" on-call rotation. The paging mechanism triggers under two conditions:

1. **Automatic duration threshold:** An incident thread opened in `#inc-live` tagged with severity P1 that remains unmitigated at T+15 minutes automatically pages the secondary IC tier.
2. **Owner escalation fallback:** If an owner page (to Aiko for `web`, Ravi for `api`, Mei for `payments`, or Tom for `notifier`) goes unacknowledged after 10 minutes, the paging tool escalates directly to the incident commander rotation as their backup.

### Acknowledging the page

When your pager fires:
- Acknowledge within 5 minutes in the paging tool.
- Join the active incident thread in `#inc-live`.
- Review the alert line pasted at the top of the thread, the severity assessment, and the initial actions taken by the primary engineer.
- Formally announce yourself in the thread (see Section 4 for handoff syntax).

---

## 3. Commander responsibilities during an incident

### 3.1 Keep the timeline

Every P1 requires an exact, audit-ready operational record. The commander ensures all critical events, metric transitions, and structural decisions are logged in the `#inc-live` thread with explicit timestamps in Japan Standard Time (JST).

Key events that must be recorded in the thread:
- Alert firing time, initial acknowledgment, and first move taken.
- Handoff of the IC role.
- Owner engagement times (e.g., when Ravi, Mei, Aiko, or Tom acknowledge).
- Status page state changes.
- Execution of rollbacks, deployment state changes, or upstream provider incident confirmations.
- Inflection points in customer impact (e.g., error rate falling below 1 %, checkout latency returning to baseline).

Do not allow impressions or vague status updates. Enforce precise metrics: write "error rate fell from 6 % to 0.3 % after rollback" rather than "looks better".

### 3.2 Update our status page

Our status page lives at `status.sorrel.app` and is edited through the internal status tool. Per handbook policy, only the incident commander updates it. Neither the primary on-call engineer nor individual service owners modify public customer-facing incident state.

- **Threshold:** The status page must be updated within 20 minutes of incident start if customer impact is visible.
- **Copy:** Use standard handbook templates. Do not improvise marketing language or speculative timelines.

| Phase | Template format |
|---|---|
| Investigating | "We are investigating reports of problems with [bookings / payments / confirmations / sign-in]. We will update this page within 30 minutes." |
| Identified | "We have identified the cause of the problems with [feature] and are working on a fix. Some customers may still see [symptom]." |
| Resolved | "The problems with [feature] between [start] and [end] JST have been resolved. We are sorry for the trouble." |

Ensure external statements never promise concessions, compensation, or refunds. If payments or billing disputes are involved, customer communications are coordinated exclusively through Hana (support lead) and Mei.

### 3.3 Decide who talks to whom

During a high-severity outage, operational channels degrade rapidly if external parties or internal stakeholders interrupt working engineers. The IC acts as the operational airlock.

- **Support team communication:** Direct all inbound inquiries from support to Hana. Provide Hana with structured updates every 15 to 30 minutes so support staff can handle incoming customer contacts consistently.
- **External providers:** When an outside dependency (stripe, twilio, sendgrid, cloudflare, or aws) experiences an outage, verify their status page (e.g., `status.stripe.com`, `status.twilio.com`, `status.sendgrid.com`, `www.cloudflarestatus.com`, or `health.aws.amazon.com`). Assign one engineer to monitor the provider status page and route findings into `#inc-live`.
- **Engineering allocation:** Prevent duplicative work. If both the primary on-call engineer and a service engineer (e.g., Sara, Daniel, Yuki, Priya, or Leo) are in thread, assign distinct surfaces: one to observe dashboard metrics and log queries, the other to coordinate with the service owner on remediation.
- **Cross-region decisions:** If an infrastructure failure affects an entire AWS region (such as our primary ap-northeast-1 deployment in Tokyo, or us-east-1 / eu-west-1), moving traffic out of a region is never a unilateral on-call decision. The IC convenes the platform lead (Kenji Sato) and the relevant service owners before directing any traffic shifts.

### 3.4 Call the incident over

An incident is not closed when code is merged or a rollback finishes; it is closed when production telemetry confirms that the platform has stabilized and customer impact has ceased.

Before declaring an incident resolved:
1. Verify error budgets, latencies, and transaction rates across the relevant dashboards ("Sorrel / web", "Sorrel / api", "Sorrel / payments", or "Sorrel / notifier").
2. Ensure backlogs are draining cleanly (e.g., queue workers actively consuming in `notifier` rather than stalled).
3. Post the resolution statement to `status.sorrel.app`.
4. State explicitly in `#inc-live` that the P1 is stood down, recording the final resolution time in JST.

---

## 4. Handoffs and role transfers

The IC role must have an unambiguous owner at every single second of an incident. Ambiguity over who holds the coordination role leads to unmanaged threads and delayed public updates.

### Handoff convention

Hand the commander role over out loud in the thread: "Kenji is IC from 03:10".

When transferring command:
1. The outgoing IC posts a concise summary of current state:
   - Current customer impact and open symptoms.
   - Active hypotheses and who is working on them.
   - Status page state and next scheduled update time.
   - Pending provider or owner escalations.
2. The incoming IC confirms acceptance.
3. The incoming IC posts the exact ownership line to `#inc-live` using the standard format:
   `[Name] is IC from [HH:MM] JST`

### Example handoff thread

```text
03:08 JST [Sara]: Current state: api 5xx rate down to 0.4 % following the rollback of d-4986. 
Database pool utilization stabilized at 42 %. Status page updated to 'Identified' at 02:55 JST. 
Ravi is reviewing slow query logs on ap-northeast primary replica.

03:10 JST [Kenji Sato]: Acknowledged, taking over incident command.

03:10 JST [Kenji Sato]: Kenji is IC from 03:10. Next status page check scheduled for 03:25 JST.
```

---

## 5. Post-incident responsibilities

The commander’s responsibilities extend through the immediate aftermath of an incident. Closing the incident thread does not conclude the operational loop.

### 5.1 Postmortem initiation

After the incident the commander opens the postmortem document and names its author.

- **Location:** Shared drive, under folder `Postmortems`.
- **Naming convention:** `YYYY-MM-DD-P1-<short-description>.md`.
- **Author assignment:** The IC designates the author based on the primary failure domain:
  - If the incident was rooted in booking logic, database contention, or partner quotas: assign to Ravi or Daniel (`api`).
  - If rooted in front-end routing, edge caching, or asset compilation: assign to Aiko or Priya (`web`).
  - If rooted in transaction failures, webhooks, or billing state: assign to Mei or Leo (`payments`).
  - If rooted in worker stall, template processing, or messaging quotas: assign to Tom or Yuki (`notifier`).
  - If rooted in cross-cutting infrastructure, regional networking, or platform orchestration: assign to Sara or Kenji Sato (`platform`).
- **Notification:** Link the initialized postmortem document at the bottom of the incident thread in `#inc-live`, explicitly mentioning the assigned author.

### 5.2 Postmortem timeline standards

The postmortem author must deliver the completed draft within 5 working days. The commander ensures the raw chat history, JST timestamps, and operational data from `#inc-live` are pasted into the draft template immediately while logs and memory are fresh.

Required postmortem structure:
- **Summary:** Concise narrative of what failed and how it was contained.
- **Impact:** Exact figures on affected bookings, failed checkouts, unserved confirmations, and SLO budget consumed.
- **Timeline:** Comprehensive event log in JST, noting alert trigger, IC assumption, mitigation steps, and recovery.
- **What went well / What went badly / Where we got lucky:** Blameless operational evaluation.
- **Action items:** Explicit tasks with clear single owners and committed target dates.

The platform team runs the blameless postmortem review meeting every Thursday, where the service owner and IC review findings and sign off on follow-up work.

---

## 6. Incident Commander Checklist

Keep this checklist open during any active command shift.

### Immediate setup (T+15 to T+20 minutes)
- [ ] Acknowledge page in paging tool.
- [ ] Open the `#inc-live` incident thread.
- [ ] Announce assumption of command: `[Name] is IC from [HH:MM] JST`.
- [ ] Verify primary engineer has executed an appropriate first move (roll back, read logs, check provider, page owner, no action).
- [ ] If impact is customer-visible, open status tool and publish "Investigating" notice to `status.sorrel.app`.
- [ ] Confirm whether service owner (Aiko, Ravi, Mei, Tom) has been paged or needs to be paged.

### Active phase (T+20 minutes to resolution)
- [ ] Maintain the operational timeline in thread every 15 minutes.
- [ ] Ensure on-call engineers are executing technical actions, not answering external inquiries.
- [ ] Coordinate with Hana if support ticket volumes spike or customer communications require alignment.
- [ ] Check provider status pages if upstream dependencies are implicated (`status.stripe.com`, `status.twilio.com`, `status.sendgrid.com`, `www.cloudflarestatus.com`, `health.aws.amazon.com`).
- [ ] Refresh status page every 30 minutes or upon state change ("Identified").
- [ ] If handing over command, announce handover out loud: `[Name] is IC from [HH:MM]`.

### Wrap-up phase (Post-recovery)
- [ ] Confirm telemetry has normalized across service dashboards for at least 15 minutes.
- [ ] Update `status.sorrel.app` to "Resolved" with precise start and end times in JST.
- [ ] Announce incident closure in `#inc-live`.
- [ ] Create new document in `Postmortems` folder.
- [ ] Name the postmortem author in `#inc-live` and provide the document link.
- [ ] Ensure primary engineer logs the incident line in the on-call log.
