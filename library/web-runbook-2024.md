# web runbook (2024 edition)

Last updated: 2024-02-19  
Owner: Aiko (web)

This is the standalone 2024 runbook for `web`, maintained by Aiko for the on-call rotation before its contents were consolidated into the main engineering handbook. It covers operational architecture, health verification, dashboards, troubleshooting procedures, escalation boundaries, and rollback execution for the frontend layer of Sorrel.

---

## 1. Service overview

`web` serves everything a user interacts with inside a web browser:
- The public booking flows for businesses (salons, clinics, dog groomers, tutors).
- The customer self-service account portal.
- The business management dashboard (calendar management, operating schedules, service setup).
- The internal admin console used by support staff (account lookups, manual confirmation resends, supervised account deletions).

The service renders pages on the server (SSR), serves compiled static assets (JavaScript bundles, CSS stylesheets, client-side images, web fonts) through our CDN distribution, and relies on `api` via internal HTTP calls for all business logic and dynamic data storage. 

`web` holds no durable customer records or business data of its own. It persists user sessions in a shared caching cluster. If `web` nodes are cycled or restarted, session continuity is preserved as long as the shared cache remains reachable.

### 1.1 Architecture and capacity (February 2024)

In our current deployment topology, `web` runs four nodes behind the load balancer in each active region (`ap-northeast-1` in Tokyo, `us-east-1`, and `eu-west-1`). 

- **Node pool:** Four nodes per region, autoscaling dynamically between four and eight nodes based on request concurrency and CPU thresholds. (Note: the baseline node footprint is four nodes per region in this revision).
- **Static assets:** Static bundles are generated during pipeline builds, synchronized directly to object storage, and distributed globally through Cloudflare.
- **Rolling deploys:** A deploy uploads the newly compiled asset set to object storage first, validates availability, and then replaces existing application instances two nodes at a time behind the load balancer.
- **Regional routing:** Public traffic enters via Cloudflare edge points of presence, traverses our edge firewall rules, and terminates on regional load balancers before hitting the local `web` node pool.

---

## 2. Dashboards and telemetry

When investigating degraded user experience on the frontend, check metrics in the monitoring suite under folder "Sorrel / Services".

### 2.1 The primary board: "Sorrel / web"

The operational board contains the following telemetry panels:

| Panel | Metric source | What to look for |
|---|---|---|
| Request Rate by Status | Load balancer & origin access logs | Sharp spikes in 5xx (origin failures) or sustained jumps in 4xx. |
| Page Load Latency | Server render timer & edge delivery | p50 and p95 page render durations. Baseline p95 should sit well below 2.0s. |
| Error Rate by Route | Server application instrumentation | Top 10 routes producing HTTP 500–504 responses. |
| Node System Health | Host metrics agent | CPU utilization, memory consumption (RSS), and process restarts per node. |
| CDN Edge Performance | Edge provider integration | Cache hit ratio, origin request volume, edge 4xx/5xx error rates. |
| Node Disk Utilization | System disk counters | Local render cache growth and log volume across node root volumes. |

*Note on browser instrumentation:* As of February 2024, the "Sorrel / web" metrics board does not include an embedded browser-reported error panel. Unhandled client-side JavaScript exceptions, broken script bundles, and failed stylesheet fetches must be inspected directly in the separate front-end error tracking tool, or cross-referenced through asset fetch logs on the edge distribution.

### 2.2 Correlated dependency boards

Because `web` renders data provided by upstream components, keep these boards in view:
- **Sorrel / api:** Managed by Ravi. Check this board whenever `web` server-side rendering times climb or origin 5xx errors increase across data-backed routes.
- **Cloudflare Edge Dashboard:** Managed by Aiko. Check cache purge state, origin fetch latencies, and regional network anomalies.

---

## 3. Symptom guide and diagnosis

Follow the five standard on-call actions when assessing incidents:
- **roll back:** Revert the most recent deploy if it went out recently and matches the onset of failure.
- **read logs:** Query log streams when the underlying cause is undetermined.
- **check provider:** Review external vendor status when the failure points outside our perimeter.
- **page owner:** Wake the service owner if irreversible damage has occurred or high-level decisions are required.
- **no action:** Record observations and step down when impact is absent.

### 3.1 Common operational failure patterns

#### Slower page loads while `api` latency is steady
- **Mechanism:** Server-side template rendering has degraded, a newly introduced client-server component is blocking the event loop, or nodes are experiencing memory paging.
- **Action:** Open `Sorrel / web`, isolate p95 latency by route, and check per-node memory panels. If this began immediately after a fresh release, prepare to roll back. If it started independent of deploys, read logs for memory pressure or template timeouts.

#### Blank pages or broken visual layout reported by users
- **Mechanism:** Missing compiled JavaScript or CSS bundles at the edge, an asset build failure that pushed incomplete bundles to object storage, or a stale CDN cache referencing deleted hashes.
- **Action:** Check the separate browser error tracking console for script execution failures. Check the CDN dashboard to ensure origin object storage fetches are succeeding and no edge cache purge is hung. If the deploy was recent, execute a rollback.

#### Surge in HTTP 4xx responses
- **Mechanism:** A renamed route, missing favicon or static image, or an automated search crawler hitting outdated paths.
- **Action:** Group route errors on the dashboard. If the traffic consists of missing assets or crawlers scanning non-existent URLs and customers are unaffected, take no emergency action during off-hours; log it and file a follow-up cleanup task.

#### HTTP 5xx errors rising across multiple pages
- **Mechanism:** `web` cannot establish connections to `api`, upstream database bottlenecks are timing out SSR requests, or node processes are crashing.
- **Action:** Check `Sorrel / api` immediately. If `api` is throwing errors, the problem sits with the core service, not `web`. If `api` is clean, query `service=web` logs for uncaught exceptions, upstream connection timeouts, or process terminations.

#### Single node restarting repeatedly
- **Mechanism:** Isolated host issue, local disk exhaustion, or an out-of-memory condition caused by render caching.
- **Action:** Verify whether the load balancer has removed the node from rotation. If user traffic is served cleanly by the remaining nodes, isolate the instance by reviewing node-specific logs rather than executing an immediate service rollback.

---

## 4. Log search patterns

All logs are stored in the search tool under index pattern `sorrel-prod-*`. Always constrain queries to the specific incident window to avoid expensive scans.

### 4.1 Diagnostic queries for `web`

To isolate failing endpoints:
```text
service=web status>=500 route=*
```
*Group this query by `route` to distinguish systemic failures from a single broken view.*

To identify server-side render timeouts:
```text
service=web msg="render timeout"
```

To investigate host memory exhaustion:
```text
service=web msg="oom" OR msg="heap limit"
```

To observe deploy pickup per host:
```text
service=web msg="started d-*"
```

To review administrative deletions executed via the internal admin console:
```text
service=web route=/admin/* action=delete
```
*Always record the session ID and target user/business record if unexpected activity is flagged.*

---

## 5. Rollback procedures

Rolling back `web` replaces running instances with containers from the previous deploy and switches CDN asset references back to the previous release build.

### 5.1 Verification before rolling back

Before initiating a rollback:
1. Confirm that the current deploy went out recently (typically within the last 30 minutes). If a deploy occurred hours or days ago, something else changed (traffic shift, partner crawler, edge provider degradation).
2. Confirm the issue originates within `web`. If `api` is returning 5xx or timing out, rolling back `web` will not resolve the incident.
3. Confirm that no irreversible damage has taken place. If customer data was incorrectly modified, page the owner first.

### 5.2 Step-by-step rollback execution

`web` deployments are managed in the central deploy tool.

```
+-------------------------------------------------------------------+
| Deploy Tool: Project "sorrel" -> Service "web"                    |
|                                                                   |
| Current Deploy:  d-1048  (Deployed 12 minutes ago)                |
| Target Deploy:   d-1047  (Previous stable release)                |
|                                                                   |
| [ Roll back to this ]  <-- Click here                             |
+-------------------------------------------------------------------+
```

1. Navigate to the deploy tool, locate the project "sorrel", and select the service "web".
2. In the deployment history list, locate the previous stable deploy (e.g., `d-1047` if current is `d-1048`).
3. Click the button labeled **"Roll back to this"**.
4. The deploy tool will orchestrate the rollback:
   - It re-points edge CDN asset routing back to the manifest of the target deploy.
   - It updates application instances behind the regional load balancers two nodes at a time.
   - The total execution cycle takes approximately four minutes.
5. Watch the "Sorrel / web" dashboard panels:
   - Confirm that the error rate and p95 page load latency drop back to baseline levels prior to the bad deploy.
   - Verify that all regional nodes pick up the target build using the log search tool (`service=web msg="started d-*"`).
6. Post an update in the `#inc-live` incident thread containing both deploy IDs (the aborted deploy and the active target deploy).
7. If the rollback completes cleanly and resolves the degradation, notify Aiko during regular working hours. If the rollback completes but errors persist, page Aiko immediately.

---

## 6. External provider interactions

`web` relies on two primary infrastructure vendors:

### 6.1 Cloudflare (CDN & Edge Security)
- **Role:** Handles TLS termination, static asset delivery, caching of public salon pages, and WAF protection.
- **Provider status:** Check `www.cloudflarestatus.com`.
- **Diagnostic criteria:** If edge latencies spike or assets return 5xx while origin node health is stable, review the provider status page and Cloudflare dashboard.
- **Operational caution:** Never alter production edge firewall configurations or WAF rules during an ongoing alert without explicit confirmation from Aiko. Cache purges should complete within 60 seconds; if purges stall, suspect an upstream provider delay.

### 6.2 AWS (Compute, Networking, Object Storage)
- **Role:** Hosts the virtual machines running the four `web` nodes per region, regional Application Load Balancers, and S3 asset buckets.
- **Provider status:** Check `health.aws.amazon.com` and the AWS Personal Health Dashboard.
- **Diagnostic criteria:** If failures are strictly localized to one region (such as `ap-northeast-1` failing while `us-east-1` and `eu-west-1` remain healthy), cross-reference AWS networking and routing status before making application-level changes. Traffic evacuation from an entire cloud region requires approval from the incident commander and service owners.

---

## 7. Escalation, owner boundaries, and admin tools

### 7.1 Admin tool operations

The admin console embedded within `web` allows our customer support staff (led by Hana) to assist business owners with their schedules, resend confirmation emails, and handle customer data requests.

- **Account deletion protocol:** Account deletions require a secondary approval in the admin tool. 
- **Irreversible actions:** The on-call engineer must never attempt manual data deletions or data restoration scripts. Restoring purged accounts requires pulling database backups, an operation performed strictly by service owners.
- **Suspicious bulk activity:** If an alert flags abnormal account modifications or deletions from a single admin session (e.g., alert rule `web-admin-bulk`), do not attempt to mitigate by restarting nodes. Immediately page Aiko.

### 7.2 When to page Aiko

Page Aiko via the paging tool (schedule escalation for `web`) under the following conditions:
- An incident has resulted in data exposure or unauthorized data access through the web interface.
- Deletions or administrative anomalies have occurred that cannot be undone.
- A rollback was performed via the deploy tool, but error rates remain elevated after completion.
- A P1 incident impacting `web` has been ongoing for 30 minutes without clear mitigation.
- Decisions are required regarding CDN edge firewall adjustments or contract-level configurations.

When paging, include the exact alert line, current severity, and the specific actions already performed in the paging payload. If Aiko does not acknowledge within 10 minutes, the paging tool will route the escalation directly to the active incident commander rotation.

---

## 8. Incident hygiene and logging

For every alert raised against `web`:

1. **Acknowledge:** Acknowledge within 5 minutes for P1, 15 minutes for P2, or 1 hour for P3.
2. **Channel:** Open or update the incident thread in `#inc-live`. Post the alert line, severity, and your initial action.
3. **Log entry:** At the conclusion of the event, append a line to the on-call log matching the standard format:
   ```text
   <date> <time JST> | web | <severity> | <first move> | <summary of observation and rationale>
   ```
4. **Postmortem:** If the incident is classified as P1, or is a P2 lasting over an hour, a blameless postmortem draft must be submitted to the shared drive within 5 working days for Thursday platform review. Coordinate findings with Aiko, Kenji Sato, and the platform team.
