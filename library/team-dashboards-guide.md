# Dashboards guide

Last updated: 2024-12-09  
Owner: Sara (platform)

This document covers how we structure and read dashboards in our metrics tool. It is written for platform engineers, service owners, and anyone taking their first shifts on the primary rotation.

Do not describe the per-service boards here; they are in the handbook. Each service runbook in the Sorrel On-Call Handbook already lists the panels for that service's board in the "Sorrel / Services" folder (`Sorrel / web`, `Sorrel / api`, `Sorrel / payments`, and `Sorrel / notifier`). This guide documents the top-level cross-service boards, general dashboard conventions, query practices, and how to use dashboard links during incident triage.

---

## 1. Where dashboards fit in incident response

When an alert pages the on-call engineer, the first job is deciding severity and the first move among our five standard actions (roll back, read logs, check provider, page owner, no action). Dashboards are the primary tool for answering three questions quickly:

1. Did the symptom start abruptly or ramp up slowly?
2. Is the blast radius isolated to one region, one node, or one endpoint group, or is it system-wide?
3. Does the symptom correlate in time with an outside event, such as a recent deploy or a provider failure?

Dashboards show aggregated telemetry. They do not replace logs when you need the exact stack trace, query string, or tenant identifier, but they tell you where in the stack to look before you run log queries.

---

## 2. Global dashboard conventions

### 2.1 Folder structure

All production telemetry boards live in the metrics tool under these top-level folders:

| Folder | Contents | Audience |
|---|---|---|
| `Sorrel / Overview` | High-level health across all four production services. | Everyone, Incident Commanders, status page updates |
| `Sorrel / Services` | Deep-dive operational boards per service (web, api, payments, notifier). | Service owners, on-call debugging |
| `Sorrel / On-call` | Paging volume, acknowledgment times, escalation statistics, shift load. | Platform lead, SRE, engineering managers |
| `Sorrel / Infrastructure` | Node clusters, AWS load balancers, database instances, network throughput. | Platform team |

### 2.2 Time picker behavior

Every board's time picker defaults to the last hour; widen it before comparing with a deploy.

This default keeps dashboard rendering fast when an engineer opens a link in the middle of the night. However, an hour-long view can be misleading:
- A deploy may have gone out 45 minutes ago, but the traffic change or error accumulation began subtly 20 minutes ago.
- Background jobs (such as notifier's nightly reminder scheduling between 02:00 and 04:00 JST, or payments' Sunday payout processing) follow diurnal cycles that only make sense when viewed across a 6-hour or 24-hour window.
- Weekly deployment cycles mean you often need to compare current traffic with the same hour from seven days prior.

When opening any board during an incident, set the time range to at least the last 3 hours, and overlay the vertical deploy markers from the deploy tool before drawing conclusions about root cause.

### 2.3 Unit and percentile standards

- **Timezone:** Dashboards render in UTC by default in the raw query engine, but team views must be set to JST (UTC+9) to match timestamps in `#inc-live`, the on-call log, and handover notes.
- **Latency panels:** We plot p50 (median), p95, and p99. Do not rely on average latency. A stable average frequently hides severe tail latency for a small share of customers.
- **Rate panels:** Request rates and throughput are rendered as operations per second or operations per minute. Error rates are plotted as a percentage of total requests for that specific route or endpoint group.

---

## 3. High-level boards

### 3.1 Sorrel / Overview

The board 'Sorrel / Overview' shows one row per service: request rate, error rate, latency.

This board provides an immediate birds-eye view across web, api, payments, and notifier without requiring the engineer to switch between four browser tabs. It is the board displayed on the wall monitor in the office and the first board opened by an incident commander when assessing broad impact.

#### Layout

```
+---------------------------------------------------------------------------------------------------+
| Sorrel / Overview                                                            Time range: [ Last 1h v ] |
+---------------------------------------------------------------------------------------------------+
| Row 1: web       | Request Rate (req/s)      | Error Rate (% 4xx vs 5xx) | Latency (p50 / p95 ms)     |
| Row 2: api       | Request Rate (req/s)      | Error Rate (% 4xx vs 5xx) | Latency (p50 / p95 / p99)  |
| Row 3: payments  | Checkouts / min           | Failure Rate (%)          | Provider vs App p95 Latency|
| Row 4: notifier  | Ingest vs Egress (msg/m)  | Vendor Rejections (%)     | Queue Depth & Age (s)      |
+---------------------------------------------------------------------------------------------------+
```

#### How to read the rows

1. **web row:**
   - *Request Rate:* Split by 2xx, 3xx, 4xx, 5xx status classes. Look for sudden drops in total requests (indicates CDN or DNS issues) or sudden surges (crawlers, campaigns).
   - *Error Rate:* Separates edge-generated errors from origin errors. Origin 5xx errors pointing upward usually reflect problems upstream in api.
   - *Latency:* Measures browser-reported rendering time against server-side rendering latency.

2. **api row:**
   - *Request Rate:* Total requests across active regions (ap-northeast, us-east, eu-west).
   - *Error Rate:* 4xx versus 5xx. A 4xx spike is often client validation or a partner exceeding their contract; a 5xx spike indicates unhandled exceptions, database pool saturation, or regional outages.
   - *Latency:* Displays p50, p95, and p99. When p99 decouples from p50, look for database locks, search index stalls, or slow third-party calls.

3. **payments row:**
   - *Request Rate:* Checkout submissions per minute. Compare current rate with the standard day curve (e.g., Friday evening peak versus quiet morning hours).
   - *Error Rate:* Checkout failure rate. Separates validation failures (customer error) from charge failures.
   - *Latency:* Crucially displays our checkout processing latency side-by-side with Stripe's API latency. If latency climbs while Stripe's latency is flat, the issue is on our application nodes or database. If both climb together, the dependency is slow.

4. **notifier row:**
   - *Request Rate:* Ingestion rate (messages placed onto the queue by api/payments) vs delivery rate (messages handed to Twilio and SendGrid).
   - *Error Rate:* Vendor-returned delivery rejections or quota rejections.
   - *Queue Depth & Age:* The depth graph shows backlogged jobs. If depth rises but egress matches normal throughput, it is likely the scheduled batch. If egress drops to zero, the workers are stuck.

### 3.2 Sorrel / On-call

The board 'Sorrel / On-call' shows pager load: pages per week, pages per night, time to acknowledge.

This board is reviewed weekly during the platform team handover meeting on Monday mornings and during the Thursday postmortem review led by Kenji Sato. Its purpose is to track on-call sustainability, identify noisy alerts that need tuning, and verify that paging policies are functioning as intended.

#### Core Panels

| Panel Name | Metric Tracked | Target / Threshold | Why We Track It |
|---|---|---|---|
| Pages per week | Total alerts routing to the primary schedule over a rolling 7-day period. | < 15 pages per week | High counts indicate alert fatigue or unstable infrastructure. |
| Pages per night | Alerts firing between 22:00 and 07:00 JST. | < 3 pages per week | Night pages directly impact engineer health and require mandatory morning rest under Section 10.4. |
| Time to acknowledge (TTA) | Time in minutes from alert generation to primary acknowledgment. | P1: < 5 min<br>P2: < 15 min | Validates paging app setup, phone notification overrides, and rotation coverage. |
| P1 escalation rate | Share of incidents requiring secondary or Incident Commander escalation. | < 10 % of P1 incidents | Identifies whether alerts are missing the primary engineer. |
| Action breakdown | Distribution of logged first moves (roll back, read logs, check provider, page owner, no action). | Monitored for trends | Alerts resulting primarily in "no action" get flagged for removal or threshold tuning. |

---

## 4. Reading dashboards during an alert

When paged, follow this systematic flow in the metrics tool:

```
                  +-----------------------------------+
                  |        Alert fires on phone       |
                  +-----------------------------------+
                                    |
                                    v
                  +-----------------------------------+
                  |  Open 'Sorrel / Overview'         |
                  |  Widen time window past 1 hour    |
                  +-----------------------------------+
                                    |
         +--------------------------+--------------------------+
         |                                                     |
         v                                                     v
[ Single service degraded ]                           [ Multiple services degraded ]
         |                                                     |
         v                                                     v
Open the service's own board                          Check dependency chain (Section 16)
in 'Sorrel / Services'                                Check AWS regional health
Compare with deploy history                           Check cloudflare edge status
```

### 4.1 Isolating regional vs global degradation

Sorrel operates across three active AWS regions:
- `ap-northeast-1` (Tokyo - our primary and largest customer volume)
- `us-east-1`
- `eu-west-1`

When api or payments alerts fire, open the regional breakdown panel. If errors or latency spikes are confined entirely to `ap-northeast`, do not assume application code is broken unless a deploy targeted that region alone. Check:
- Cross-region database replication lag.
- Region-level AWS personal health dashboards.
- Cloudflare CDN edge delivery metrics for the Tokyo points of presence.

### 4.2 Separating internal latency from outside provider latency

A frequent source of mistaken rollbacks is confusing downstream provider slowness with application regressions. The payments and notifier dashboards explicitly split these metrics:

- On `Sorrel / payments`, our internal checkout handler duration is plotted in blue, and card provider API response time is plotted in amber. If amber spikes to 6,000 ms and blue tracks it directly, the issue is on the Stripe side. Rolling back payments code will not resolve the incident; the handbook action is to check provider (`status.stripe.com`).
- On `Sorrel / notifier`, worker queue processing delay is separated from SendGrid and Twilio delivery acknowledgment latencies. If vendor response codes show HTTP 429 (rate limited) or 5xx, worker processing stalls naturally.

---

## 5. Correlating dashboard metrics with deploys

Our deployment tool registers markers directly into the metrics engine. Every deployment event for `web`, `api`, `payments`, and `notifier` appears as a thin vertical line labeled with its deploy id (e.g., `d-1042`) or release identifier.

### 5.1 Evaluating deploy age against metric changes

- **Immediate jump:** If an error rate rises from 0.1 % to 4.5 % within 3 minutes of a vertical deploy line, the deploy is the prime suspect. The handbook action is rollback.
- **Gradual drift:** If latency has been climbing steadily over the past 18 hours, an alert firing 10 minutes after a new deploy is often coincidental. The recent deploy might have accelerated memory exhaustion, but it did not cause the underlying leak. Read logs before initiating a rollback.
- **Time picker trap:** Remember that because every board defaults to the last 1 hour, a deploy completed 65 minutes ago will not appear on the screen unless you widen the time picker. Always widen the view to 3 or 6 hours to inspect the baseline before the deploy occurred.

---

## 6. Query best practices for custom panels

Engineers building ad-hoc dashboards during long incidents or tuning boards for postmortems should adhere to these standards:

### 6.1 Avoid high-cardinality group-by queries
- Grouping metrics by `customer_id`, `booking_id`, or raw URL parameters will freeze dashboard panels and overload the metrics cluster.
- Keep aggregations grouped by bounded labels: `service`, `region`, `node`, `endpoint_group`, `status_code`, or `partner_id`.
- For individual customer or booking troubleshooting, pivot to the log search tool using index `sorrel-prod-*`.

### 6.2 Rate calculations
- Use 1-minute or 5-minute rolling evaluation windows for alert thresholds. Windows under 1 minute cause alerting flaps on momentary network blips.
- Ensure counter metrics properly handle node restarts. Use rate functions that handle counter resets gracefully rather than raw deltas.

### 6.3 Metric naming taxonomy

All Sorrel metrics exported to the collection agents adhere to this prefix scheme:

```
sorrel_<service>_<subsystem>_<measurement>_<unit>
```

Examples:
- `sorrel_api_db_pool_active_connections`
- `sorrel_web_render_duration_ms`
- `sorrel_payments_checkout_requests_total`
- `sorrel_notifier_queue_oldest_message_age_seconds`

---

## 7. Dashboard maintenance and on-call hygiene

Dashboards require regular upkeep to remain reliable operational tools:

1. **Postmortem action items:** If an incident took longer than 15 minutes to diagnose because a key metric was absent, an action item must be assigned to the service owner to add that panel to the service's dashboard.
2. **Pruning stale panels:** Dashboards with broken queries, obsolete feature flags, or dead endpoints create visual clutter during high-stress triage. If a panel displays `No Data` for more than 14 days, the owning team must either fix or delete it.
3. **Weekly review:** The platform team (Sara, Kenji Sato) audits query performance across `Sorrel / Overview` and `Sorrel / On-call` monthly to ensure boards render in under 3 seconds on standard connections.

For questions regarding board permissions, adding new alert lines, or configuring custom metric exporters, raise a ticket for the platform team in `#platform-internal`. Detailed runbooks for individual services remain in the Sorrel On-Call Handbook.
