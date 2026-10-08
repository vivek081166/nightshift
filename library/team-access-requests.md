# Access requests for on-call

Last updated: 2025-04-28  
Owner: Kenji Sato (platform lead)

This guide documents the technical access requirements, group memberships, provisioning workflows, and permission boundaries for engineers joining the primary on-call rotation at Sorrel.

Every engineer scheduled to take primary shifts or shadow an active rotation must complete the setup steps described below before their first shadow shift begins. Operating on-call requires immediate, unhindered visibility into production telemetry, operational logs, alerting systems, and deployment rollbacks across all four Sorrel production services: web, api, payments, and notifier. It also requires strict adherence to our boundary controls regarding customer data and production state.

---

## 1. Core Principles and Permission Boundaries

At Sorrel, the role of the on-call engineer is defined narrowly and deliberately: you are responsible for triage, immediate mitigation (such as executing a rollback to a previous deploy), provider health verification, and escalating unrecoverable conditions to service owners. You are not an arbitrary operator with write access across our persistence layers.

### 1.1 Read Telemetry vs. Data Write Access
- **Log search and dashboard access come with the group `oncall-readers`.** Membership in this group provides broad read access across internal monitoring tools, server metrics, performance dashboards, and the centralized log search cluster.
- **On-call never gets write access to customer data; that is by design.** No engineer receives direct write access, update privileges, or administrative mutation capabilities against production customer tables, booking records, user profiles, or raw transaction databases as part of their on-call role.

This boundary exists to protect both the business and the engineer on call:
1. *Mitigation is prioritized over improvisation:* If customer records are corrupted, transactions have moved incorrectly, or records are improperly altered, on-call engineers are not authorized or permitted to run ad-hoc database updates or manual state repairs. Such conditions require waking the service owner (Aiko for web, Ravi for api, Mei for payments, Tom for notifier).
2. *Data privacy enforcement:* Customer details—names, email addresses, phone numbers, and salon or medical consultation notes—are masked in logs and strictly isolated within primary datastores in our active cloud regions (`ap-northeast-1`, `us-east-1`, and `eu-west-1`). Direct modification rights cannot be requested for triage shifts.
3. *Audit integrity:* In api, the audit log records all modifications to bookings and accounts. Granting on-call write access outside the normal application runtime would compromise compliance and dispute resolution trails.

### 1.2 Summary of Permissions for the Rotation

| System | Role / Group | Level of Access | Approval Required |
|---|---|---|---|
| Metrics tool | `oncall-readers` | Read-only across "Sorrel / Services" | Kenji Sato |
| Log search tool | `oncall-readers` | Query access on index `sorrel-prod-*` | Kenji Sato |
| Paging tool | Schedule "Sorrel primary" | Alert acknowledgment, escalation paging | Platform team (automatic) |
| Deploy tool | Deployment operator | Rollback execution to previous deploy | Standard engineering onboarding |
| Production databases | None | **No write access to customer data** | Strictly prohibited by design |
| Cloud provider | Console read-only | Regional infrastructure status | Platform team |
| Status tool | Incident commander only | Status page updates for `status.sorrel.app` | Escalation / IC rotation |

---

## 2. Request Workflow: `oncall-readers`

Log search and dashboard access come with the group `oncall-readers`. Because this group grants cluster-wide search access across production operational indices, it is governed by our formal platform change tracking.

### 2.1 How to Request
1. Open an internal IT access ticket using the template `Access Request: On-Call Observability`.
2. Set the requested group to `oncall-readers`.
3. Post the ticket link in `#access` in chat.
4. Note your scheduled shadow shift start date in the thread.

### 2.2 Approvals and Turnaround Time
- **Request it in `#access` with a ticket; Kenji approves; it takes one working day.**
- Do not submit the request on the morning of your shadow shift. File the ticket at least one full working day prior to when you are scheduled to begin shadowing.
- During planned absences where Kenji is unavailable, Sara handles operational access ticket review on the platform team's behalf.

---

## 3. Paging Tool Setup

Paging tool access is set up by the platform team when you join the rotation. You do not need to submit an access ticket in `#access` for the paging tool itself.

### 3.1 Provisioning Procedure
When your onboarding schedule is finalized and confirmed with the platform team:
1. The platform team creates your paging profile and associates it with your company identity.
2. You are placed on the secondary rotation schedule and added to the "Sorrel primary" schedule tree.
3. You will receive an automated profile setup invitation to your company workstation.

### 3.2 Pre-Shift Device Verification
Once the platform team completes the profile setup, complete the following validation steps prior to your shadow shift:
- Install the paging application on your primary mobile phone.
- Configure notification rules to bypass system focus, sleep, and silent profiles.
- Execute a test page from the paging tool client. Confirm that the alert produces an audible, persistent notification.
- Verify that acknowledging a page works directly from both the mobile client and your workstation web interface. Acknowledge time is strictly enforced (5 minutes on a P1, 15 minutes on a P2).
- Confirm visibility into the owner escalation schedules for all four service domains:
  - **web**: Aiko (backup: incident commander rotation)
  - **api**: Ravi (backup: incident commander rotation)
  - **payments**: Mei (backup: incident commander rotation)
  - **notifier**: Tom (backup: incident commander rotation)

If you do not see your profile attached to the "Sorrel primary" schedule at least three working days before your shift, post in `#platform-support` so Sara or Kenji can resolve your roster entry.

---

## 4. Systems Configured via `oncall-readers`

Membership in `oncall-readers` configures your single sign-on profile across two mission-critical monitoring platforms:

### 4.1 Log Search Tool (Index: `sorrel-prod-*`)
The group grants query execution rights over all production log streams tagged with `service=<name>`.

#### Available Datastreams
- `service=web`: HTTP access logs, server-side rendering execution traces, asset loading telemetry, and administrative endpoint traces.
- `service=api`: Endpoint routing, connection pool health, slow query captures, response filters, and audit daemon events.
- `service=payments`: Regional checkout attempts, payment provider responses, webhook ingestion traces, and validation exceptions.
- `service=notifier`: Worker ingestion rates, template rendering pipelines, and vendor status responses.

#### Mandatory Log Hygiene Rules
Even with search access, on-call engineers are subject to strict data handling constraints:
- Customer phone numbers, real names, and contact details are masked by our ingestion filters before indexing. If you encounter an unmasked field in an error trace, notify the service owner immediately.
- Card numbers are never stored, logged, or indexed by Sorrel; payment references are used instead. Never run ad-hoc searches designed to match raw card sequences. Searches for card details are themselves audited and reviewed by Mei's team.
- Never copy raw log search output into public chat channels or unencrypted tickets. When discussing log events in `#inc-live`, link directly to the log search tool query window with an explicit time boundary.

### 4.2 Metrics Dashboards ("Sorrel / Services")
Membership in `oncall-readers` opens read access to all boards in the metrics tool folder "Sorrel / Services". These boards are essential for triage:

- **Sorrel / web**:
  - Request rate segmented by status code (2xx, 3xx, 4xx, 5xx).
  - p50 and p95 page load latencies (server-side vs. real-user browser metrics).
  - Top ten routes by error frequency.
  - Node resource utilization (CPU, memory, restarts per node).
  - Cloudflare CDN edge metrics: cache hit ratio, origin traffic volume, 4xx/5xx at edge.
  - Browser-reported script errors and failed static asset loads.
  - Disk usage per node for log files and local render caches.

- **Sorrel / api**:
  - Request rate split across endpoint groups (`booking`, `search`, `account`, `partner`).
  - Latency percentiles (p50, p95, p99) per endpoint group.
  - Error volume segmented by 4xx and 5xx.
  - Service Level Objective (SLO) panel tracking monthly booking error budget consumption.
  - Primary and read replica database metrics: connection pool usage per node, slow queries, replica lag across `ap-northeast`, `us-east`, and `eu-west`.
  - Search index query times and freshness latencies.
  - Partner traffic metrics showing quota consumption and rejection rates against contractual limits.
  - Audit log event write rates.

- **Sorrel / payments**:
  - Checkout attempts, success rates, and failure rates per active region.
  - Charge transaction outcomes and latency to card provider response.
  - Split latency panel comparing internal checkout overhead against provider response times.
  - Refund issuance counts and aggregate volume per hour.
  - Webhook delivery states (received, retried, failed) segmented by event type.
  - Weekly business payout batch job states.
  - Validation failures segmented by input field.

- **Sorrel / notifier**:
  - Queue depth, enqueue rates, and worker delivery rates per minute.
  - Message age for the oldest queued item.
  - Delivery outcomes across channels (email via SendGrid, SMS via Twilio).
  - Upstream vendor response code distributions.
  - Duplicate message detection panel tracking repeated message IDs over 24-hour windows.
  - Daily vendor quota utilization meters.

---

## 5. Deployment Tool Access and Rollbacks

Every engineer on call is provisioned as an operator within the deploy tool for the project "sorrel". 

### 5.1 Permitted Deployment Actions
On-call engineers are strictly permitted to perform one operational deploy action without service owner approval: **rolling back a service to its immediately preceding deploy** when a recent release has caused an active production regression.
- All four services deploy and roll back through the deploy tool (project "sorrel"). Rollbacks swap back to the previous known good deployment ID (`d-*`), replacing nodes and updating edge assets or worker queues over a few minutes.
- The deploy tool retains the last twenty deploys of each service ready for immediate rollback.

### 5.2 Prohibited Deployment Actions
- **No new feature deploys:** On-call engineers are prohibited from pushing new code releases, deploying bug-fix builds, or promoting hotfixes during their shift unless they are the direct author/owner of the change and have explicitly posted notice to the on-call channel during regular business hours.
- **No multi-version rollbacks:** Rolling back more than one release boundary may break database schema backward compatibility. Multi-version rollbacks require the presence and authorization of the owning service lead (Ravi, Mei, Aiko, or Tom).
- **No feature flag toggles:** Modifying feature flags in production is not equivalent to an operational rollback. Feature flags are managed directly by service owners.

---

## 6. Access Verification Checklist

Prior to entering your first scheduled shadow shift, complete the checklist below. Review your access from your remote workstation using your standard off-network VPN/authentication profile:

- [ ] **Log Search Tool**: Can authenticate, access the `sorrel-prod-*` index, and successfully execute a scoped query such as `service=web level=ERROR` over a recent 15-minute window.
- [ ] **Metrics Tool**: Can navigate to the "Sorrel / Services" folder and view live graphs across all four service boards: web, api, payments, notifier.
- [ ] **Deploy Tool**: Can access project "sorrel", view deployment history for web and notifier, inspect deploy IDs (`d-*`), and locate the "Roll back to this" control panel.
- [ ] **Paging Tool**: Mobile application installed, critical alerts allowed through Do Not Disturb, profile attached to the "Sorrel primary" schedule, test page acknowledged successfully.
- [ ] **Incident Communication**: Joined `#inc-live`, `#access`, and the primary engineering operational channels.
- [ ] **Outside Provider Dashboards**: Verified bookmarks for external provider status boards:
  - Stripe: `status.stripe.com`
  - Twilio: `status.twilio.com`
  - SendGrid: `status.sendgrid.com`
  - Cloudflare: `www.cloudflarestatus.com`
  - AWS: `health.aws.amazon.com` (and AWS Personal Health Dashboard)
- [ ] **Status Page**: Confirmed access to view `status.sorrel.app` (incident commanders retain update permissions).

If any check fails, do not wait until the handover window on Monday morning. File a ticket and ping `#access` or notify Kenji and Sara immediately.

---

## 7. Offboarding and Role Transitions

When an engineer leaves the on-call rotation:
1. The platform team removes the user profile from the "Sorrel primary" schedule in the paging tool.
2. If the engineer no longer requires production telemetry access for primary engineering duties, a removal ticket is filed in `#access` to de-provision membership in `oncall-readers`.
3. Paging notification routes and escalation backups are audited to ensure no automated notifications escalate to an inactive member.
