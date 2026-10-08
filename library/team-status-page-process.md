# Status page process

Date: 2025-08-25  
Owner: Kenji Sato (platform lead)

This page defines how the platform and SRE teams manage Sorrel's public status page at `status.sorrel.app`. It details who has publication access, the mechanics of drafting and updating incident notices, the timeline constraints for public communications, and how resolved notices are archived.

---

## 1. Scope and Responsibilities

Our public status page lives at `status.sorrel.app` and is operated through the status tool. It is the single source of truth for external customers, business owners, and integration partners regarding the operational health of Sorrel's four core services: `web`, `api`, `payments`, and `notifier`.

Because external communications carry contractual, brand, and support implications, strict separation of responsibilities applies during incidents:

- **Incident Commander (IC):** The incident commander is the only person permitted to edit and publish updates to `status.sorrel.app`. The IC maintains editorial control over tone, precision, and alignment with support operations.
- **On-Call Engineer:** The primary on-call engineer handles technical triage, executes the first move, and drafts the status page wording inside the incident thread (`#inc-live`) using the approved templates from Section 8.3 of the handbook. The on-call engineer never posts directly to the public status page.
- **Service Owners:** Service owners (Aiko for `web`, Ravi for `api`, Mei for `payments`, and Tom for `notifier`) advise the commander on system state, recovery timelines, and technical accuracy. Owners do not publish status updates unless formally serving as the active incident commander.
- **Support Lead:** Hana (support lead) tracks the public status updates to synchronize macros, customer responses, and incoming ticket volume. Individual customer communications remain under Hana's team. The on-call engineer never contacts customers directly.

---

## 2. Decision Framework: When to Update

We do not post internal glitches, brief transient metric spikes, or behind-the-scenes degradations that do not affect customer workflows. Status page updates are reserved for issues visible to our users.

| Severity | Customer Impact Present? | Publish to status.sorrel.app? | SLA for First Update | Follow-up Cadence |
|---|---|---|---|---|
| **P1** | Yes (e.g., checkout failures, booking engine down, asset render errors, confirmations halted) | **Yes** | **Within 20 minutes** of incident declaration | Every 30 minutes, or upon any state change |
| **P1** | No (e.g., internal audit writer failure without booking loss, secret exposure contained internally) | **No** | N/A | N/A |
| **P2** | Yes (e.g., elevated latency noticeable to users, partial degradation of partner endpoints) | **Discretionary** (IC decides based on customer visibility and volume of support tickets) | Within 30 minutes if approved by IC | Every 30 to 60 minutes |
| **P2** | No (e.g., safety net failure, replica lag within tolerances, audit backlog) | **No** | N/A | N/A |
| **P3** | No customer impact (e.g., disk usage trend, off-peak reminder backlog draining normally) | **No** | N/A | N/A |

### 2.1 The 20-Minute P1 Rule

Under Section 2 of the On-Call Handbook, any P1 where customers can see the problem requires an update to our status page within 20 minutes. 

Because the incident commander rotation is formally paged if a P1 remains open after 15 minutes, there is a narrow window between IC escalation and the 20-minute mark. To ensure we never miss this deadline:
1. The on-call engineer drafts the notice in `#inc-live` immediately upon confirming customer impact.
2. When the IC joins the thread, the draft is already waiting for review.
3. The IC reviews, edits for clarity, and pushes the notice to the status tool before minute 20.

---

## 3. Workflow and Mechanics

The lifecycle of a status notice consists of four stages: drafting, publishing, posting ongoing progress, and resolution.

```
[ Alert fires & P1 declared ]
            │
            ▼
[ On-call drafts message in #inc-live using template ] ── (Within 10-15 mins)
            │
            ▼
[ Incident Commander reviews and edits draft ]
            │
            ▼
[ Incident Commander publishes to status.sorrel.app ] ── (Hard limit: < 20 mins)
            │
            ▼
[ IC updates notice every 30 mins or on state change ]
            │
            ▼
[ Mitigation confirmed by On-call and Owner ]
            │
            ▼
[ IC posts "Resolved" notice; notice remains 7 days ]
```

### 3.1 Step 1: On-Call Drafting

When an incident is declared and customer impact is identified, the primary on-call engineer opens a thread in `#inc-live`. While initiating triage or executing the first move, the on-call engineer selects the applicable handbook template, fills in the bracketed placeholders, and posts the draft into the incident thread with the label `PROPOSED STATUS PAGE DRAFT`.

The on-call engineer must never invent novel language, speculate on underlying architecture, or mention internal tools (such as deployment IDs or log queries) in the draft.

### 3.2 Step 2: Commander Review and Publication

The incident commander reads the proposed draft in `#inc-live`. The commander checks:
- Does it accurately name the affected feature (`bookings`, `payments`, `confirmations`, or `sign-in`) without over-promising?
- Does it avoid speculative root causes?
- Is it free of promises regarding financial compensation, goodwill credits, or precise restoration times?

The commander opens the status tool, pastes the text, selects the affected component (`web`, `api`, `payments`, or `notifier`), sets the component state (`Degraded Performance`, `Partial Outage`, or `Major Outage`), and clicks publish.

Once published, the commander pastes the public URL and the published text back into the `#inc-live` thread so the engineering team and Hana are aware of what customers see.

### 3.3 Step 3: Ongoing Updates

While the incident is active, the IC is responsible for keeping the status page fresh:
- Updates must be published at least every 30 minutes during an active P1.
- If the technical team identifies the root cause (for example, confirming a third-party payment provider degradation or bad front-end bundle), the IC transitions the notice from the "Investigating" template to the "Identified" template.
- If the on-call engineer or owner performs a mitigating action (such as rolling back `web` to its previous deploy, or waiting out an upstream network issue), the IC updates the text to state that a fix is being verified.

### 3.4 Step 4: Resolution and Retention

An incident is only declared resolved on the status page when:
1. Dashboards for the affected service confirm error rates, latencies, or queue processing have returned to normal operating baselines.
2. The service owner (Aiko, Ravi, Mei, or Tom) and the on-call engineer agree that no secondary failure modes are present.
3. Hana confirms that incoming customer complaint volume for the symptom has subsided.

Once verified, the IC publishes the resolution notice using the standard resolved template. 

**Retention Rule:** Resolved notices stay visible on `status.sorrel.app` for exactly **7 days**. Do not delete, hide, or archive an incident entry prior to the 7-day mark. Small business owners relying on Sorrel plan their weekly calendars and financial reconciliations across several business days; keeping notices public for 7 days allows businesses to correlate customer complaints, appointment discrepancies, or missed notifications with past platform events without having to open unnecessary support tickets. After 7 days, the status tool automatically archives the entry into the historical uptime record.

---

## 4. Standard Templates

In accordance with Section 8.3 of the On-Call Handbook, status notices must adhere to the three standardized templates. Consistency prevents customer confusion and avoids creating liabilities.

### 4.1 Template 1: Investigating

Used when an incident is detected, customer harm is confirmed, but the root cause has not yet been isolated or mitigated.

> **Status:** Investigating  
> **Text:** "We are investigating reports of problems with [bookings / payments / confirmations / sign-in]. We will update this page within 30 minutes."

*Drafting instructions:* Select one or more of the specific bracketed features. Do not alter the commitment to update within 30 minutes.

### 4.2 Template 2: Identified

Used when the technical team has identified the cause (e.g., an issue with an upstream provider or an isolated deployment defect) and is actively working on or rolling out a fix.

> **Status:** Identified  
> **Text:** "We have identified the cause of the problems with [feature] and are working on a fix. Some customers may still see [symptom]."

*Drafting instructions:* Replace `[feature]` with the affected customer-facing system (e.g., "appointment booking", "card checkouts", "SMS reminder delivery"). Replace `[symptom]` with what the customer experiences (e.g., "slow page load times", "failed payments at checkout", "delayed email confirmations").

### 4.3 Template 3: Resolved

Used when metrics have returned to baseline and stability is confirmed by the incident commander.

> **Status:** Resolved  
> **Text:** "The problems with [feature] between [start] and [end] JST have been resolved. We are sorry for the trouble."

*Drafting instructions:* Fill in `[feature]` matching previous updates. `[start]` and `[end]` must be explicitly formatted in Japan Standard Time (JST), including the 24-hour time (e.g., "14:15 and 14:48 JST" or "2025-08-24 23:40 and 2025-08-25 00:25 JST").

---

## 5. Component Mapping and Provider Handling

When opening an incident in the status tool, the IC must mark specific service components. The table below maps customer-visible symptoms, affected Sorrel services, corresponding components in the status tool, and external provider dependencies.

| Customer Symptom | Core Service | Status Page Component | Upstream Provider Dependencies | Guidance Notes |
|---|---|---|---|---|
| Public calendar blank, business dashboard failing, render errors | `web` | Web Application / Booking Dashboard | Cloudflare (CDN / WAF), AWS | Check if edge is returning errors or origin is down. If static assets fail after deploy, roll back `web`. |
| Booking creation failing, search unavailable, partner sync broken | `api` | Core API & Scheduling Engine | AWS (ap-northeast-1, us-east-1, eu-west-1) | Ravi owns core booking logic. If cross-tenant response checks fail, page Ravi immediately (P1). |
| Credit card checkout timing out, deposit payments failing | `payments` | Checkout & Payments | Stripe | Check status.stripe.com. If Stripe is degraded, note checkout degradation; do not touch provider credentials. |
| Confirmation emails not delivered, receipts missing | `notifier` | Email Notifications | SendGrid | Tom owns vendor account. Check status.sendgrid.com. Notifier queues messages; never rollback for backlog alone if draining. |
| SMS verification codes missing, appointment reminders delayed | `notifier` | SMS Notifications | Twilio | Tom owns vendor account. Check status.twilio.com. Note web sign-in has email fallback. |

### 5.1 Third-Party Provider Outages

When an incident is caused by an outside dependency (`stripe`, `twilio`, `sendgrid`, `cloudflare`, or `aws`), we communicate our degraded state clearly to customers without blaming or attacking the vendor. 

- Use the standard templates: name the affected feature rather than the internal vendor name. For example, state "problems with payments", not "Stripe is having an outage".
- The incident commander must subscribe the incident channel to the provider's status page (e.g., status.stripe.com, status.twilio.com).
- If the provider is degraded, Sorrel cannot accelerate their resolution. The IC must ensure the status page is updated every 30 minutes to confirm we are monitoring the upstream recovery.

---

## 6. Real Incident Walkthrough: P1 Checkout Degradation

To demonstrate how the handoff between on-call and the incident commander works in practice under the 20-minute rule, consider the following timeline from a past production event.

### 6.1 Timeline Example

- **14:02 JST:** Checkout failure rate rises above 2 % in region `ap-northeast-1`. Alert `payments-checkout` fires. The primary on-call engineer acknowledges the page at 14:04 JST.
- **14:06 JST:** On-call confirms real checkouts are failing. Latency on our payments nodes is normal, but charge attempts to Stripe are timing out. The on-call engineer checks `status.stripe.com` and sees degraded API performance reported by the provider.
- **14:08 JST:** On-call engineer opens incident thread in `#inc-live`:
  > **On-Call:** "P1 declared. `payments-checkout` firing, charge attempts timing out at provider. Customer checkout affected. Opening status page draft below."
- **14:10 JST:** On-call posts the draft in `#inc-live`:
  > **PROPOSED STATUS PAGE DRAFT:**  
  > Feature: payments  
  > Text: *We are investigating reports of problems with payments. We will update this page within 30 minutes.*
- **14:15 JST:** Incident duration reaches 13 minutes. Because customer impact is high and external recovery is pending, the on-call engineer pages the incident commander rotation.
- **14:17 JST:** The incident commander acknowledges and joins `#inc-live`. The IC reviews the draft posted at 14:10 JST.
- **14:19 JST (Minute 17 of incident):** The IC logs into the status tool, sets the "Checkout & Payments" component to `Degraded Performance`, and publishes the notice. This completes the publication safely within the **20-minute limit**.
- **14:20 JST:** Hana updates customer support macros to reflect the published notice, advising agents that checkout retries are running and customers should avoid repeatedly re-submitting cards.
- **14:45 JST:** The IC posts an updated "Identified" notice:
  > *We have identified the cause of the problems with payments and are working on a fix. Some customers may still see failed payments at checkout.*
- **15:10 JST:** Upstream provider resolves their network degraded state. Charge success returns to 99.8 % on the `Sorrel / payments` dashboard. Mei verifies that no duplicate charges occurred and webhook retries have completed.
- **15:25 JST:** The IC publishes the resolved message:
  > *The problems with payments between 14:00 and 15:20 JST have been resolved. We are sorry for the trouble.*
- **Retention:** The notice remains visible under past incidents on `status.sorrel.app` until 15:25 JST 7 days later, after which it moves to the automated archive.

---

## 7. Common Pitfalls and Anti-Patterns

During incident reviews, the platform team frequently audits status page execution. The following common anti-patterns must be avoided:

1. **On-Call publishing directly:** The on-call engineer is focused on stopping damage, examining dashboards, reading logs, and coordinating with service owners. Taking on external communication distracts from technical triage. Draft only; let the IC publish.
2. **Missing the 20-minute window:** Waiting until root cause is definitively proven before posting the first status update violates our P1 SLA. If customers cannot book or pay, publish the "Investigating" notice within 20 minutes even if the underlying reason is still unknown.
3. **Speculative technical detail:** Never publish text such as "Database connection pool exhausted on api node 4" or "Rollback of deploy d-5120 failed". Customers need to know what business workflow is broken, not our internal infrastructure details.
4. **Deleting resolved notices early:** Removing a resolved notice after a few hours obscures visibility for businesses auditing their day's bookings. Always allow notices to stay on the page for the full 7 days.
5. **Promising compensation:** Never write "Refunds will be granted for missed appointments" or "Credits will be applied" on the status page. Commercial remedies are handled strictly through Hana and the service owners.

For questions or feedback regarding this process, reach out to Kenji Sato or post in the platform discussion channel.
