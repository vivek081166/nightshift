# cloudflare: purge and firewall notes

Last updated: 2025-12-01  
Owner: Aiko (web)  
Contributors: Kenji Sato, Sara, Priya  

This note documents our operational setup for Cloudflare, specifically how edge caching, cache purges, and Web Application Firewall (WAF) rate limits interact with `web` and `api`. It captures our baseline settings, operational thresholds, triage procedures for edge anomalies, and lessons learned from the high-traffic partner synchronization window in November 2025.

---

## 1. Overview and Architecture

Sorrel relies on Cloudflare as our edge Content Delivery Network (CDN), DDoS mitigation layer, and Web Application Firewall (WAF). It sits directly in front of `web` (static assets and server-rendered public pages) and `api` (public endpoints and partner integrations).

```
                     +----------------------------------+
                     |         Cloudflare Edge          |
                     |  - Edge cache (web static/HTML)  |
                     |  - WAF rate limiting (api/web)   |
                     +-----------------+----------------+
                                       |
                +----------------------+----------------------+
                |                                             |
                v                                             v
     +--------------------+                        +--------------------+
     |    Origin: web     |                        |    Origin: api     |
     | (ALB -> 6-12 nodes)|                        | (ALB -> 8-20 nodes)|
     +--------------------+                        +--------------------+
```

### Key Operational Boundaries

- **Account ownership:** The Cloudflare tenant configuration, edge certificates, DNS zone files, and WAF rules are owned by Aiko.
- **Incident authority:** Firewall rules are never changed during an incident without Aiko. The on-call engineer has read-only visibility into edge metrics and firewall event streams, but may not alter edge rules, disable security tiers, or bypass rate limits without explicit direction from the service owner.
- **Status page monitoring:** Outside provider status is tracked at `www.cloudflarestatus.com`. Note that for our primary user base in Japan (ap-northeast-1), Cloudflare reports edge node status for the Tokyo and Osaka data centres separately. An incident affecting transit or edge workers in Osaka does not necessarily degrade Tokyo, and vice versa. Always check both points of presence when investigating regional edge errors.

---

## 2. Cache Purges and Invalidation

### 2.1 Normal Lifecycle

When `web` deploys, the build pipeline compiles modern client bundles, uploads versioned assets (`/assets/[hash].js`, `/assets/[hash].css`, web fonts, and localized UI images) to AWS S3 object storage, and executes a targeted cache purge across the Cloudflare edge for shared HTML shells and runtime entry points.

Under standard conditions:
- Cache purges complete across all edge points of presence in under 60 seconds (typically 15–30 seconds).
- Edge propagation is confirmed via the CDN dashboard panel on the "Sorrel / web" metrics board.
- The origin nodes for `web` transition two nodes at a time, handling traffic for the newly deployed bundle once the edge has dropped stale entry points.

### 2.2 Purge Delays and Provider Stalls

A purge that is still running after several minutes is a provider-side delay. It indicates upstream contention or message queue delays within Cloudflare's internal control plane, not a failure of our deployment runners.

When a purge stalls during or immediately following a deploy:

| Metric / Panel | Normal Value | Purge Stall Indicator |
|---|---|---|
| Edge cache purge duration | < 60 seconds | > 180 seconds |
| CDN edge 4xx / 5xx | < 0.2 % | Spike above 2.0 % on missing assets |
| Front-end errors | Baseline (< 10/min) | Spike in `Failed to fetch dynamically imported module` |
| Origin requests to `web` | 80–120 req/s | > 350 req/s (origin thundering herd) |

#### Operational Steps During Purge Delays

1. **Do not re-trigger repeated bulk purges.** Issuing repeated full-zone purge calls (`purge_everything`) compounds control plane latency at the edge and drops completely valid cached resources, placing unneeded load on `web` origin nodes.
2. **Examine the Cloudflare Status Page.** Navigate to `www.cloudflarestatus.com`. Check the status of:
   - Control Plane / Dashboard & API
   - Edge Cache Purge Services
   - Tokyo and Osaka regional data centres
3. **Check the Origin Health.** Inspect the "Sorrel / web" dashboard. Check the CDN panel: is the edge serving errors, or is the origin? If the origin is serving 200s but the edge is serving 404s for chunked bundles, the edge is attempting to fetch assets that were purged before object storage uploads finished, or the edge is returning stale HTML pointing to removed revisions.
4. **Determine Triage Action.**
   - If a deploy just completed within the last 10 minutes and users are reporting blank pages or broken layouts due to missing assets, refer to the handbook: decide the severity based on user impact.
   - If edge errors exceed 2 % for 5 minutes (`web-cdn-edge` alert), and the symptoms point to provider edge stalls, do not attempt to manipulate origin routing or flush caches manually via custom API calls.
   - If the deploy tool shows an active deploy, and the rollback criteria are met, roll back `web` via the deploy tool (project "sorrel", service "web"). A rollback re-points the nodes to the previous deploy and re-points the CDN to the previous asset set. This process takes about four minutes.

---

## 3. Web Application Firewall (WAF) and Rate Limiting

Cloudflare sits in front of `api` to protect booking endpoints, search queries, and partner integrations from abusive patterns, scraping bots, and misconfigured external scripts.

### 3.1 Architecture of `api` Edge Limits

Traffic reaching `api` falls into four distinct endpoint groups:

1. **Public booking flow (`/api/v1/bookings/*`):** High priority, heavily guarded against scraping and slot hoarding.
2. **Search (`/api/v1/search/*`):** Read-heavy, subject to regional crawling activity.
3. **User accounts (`/api/v1/me/*`, `/api/v1/auth/*`):** Low burst volume, strictly throttled to prevent credential stuffing.
4. **Partner API (`/api/v1/partners/*`):** Exclusively utilized by authorized integration partners (calendar synchronization tools, third-party booking widgets, and national franchise enterprise systems).

Each partner connects using dedicated API tokens. Requests are authenticated at the edge and counted against contracted volume thresholds.

```
Incoming Request -> [Cloudflare Edge WAF]
                         |
                         +--> Matches IP/Token Denylist? ----> Drop (403)
                         |
                         +--> Exceeds WAF Rate Limit? -------> Block (429)
                         |
                         v (Allowed)
                 [Sorrel api Origin]
                         |
                         +--> Origin Contract Checks --------> 429 (Partner Quota Exceeded)
                         +--> Application Handlers ----------> 2xx / 4xx / 5xx
```

### 3.2 The November Partner Sync Season

As documented in section 13.3 of the On-Call Handbook, November is the busiest month for partner integrations. Large salon chains, physiotherapy groups, and schedule aggregators push full schedule synchronizations for the upcoming calendar year.

During November 2025:
- Partner API traffic increased by approximately 340 % over baseline October volumes.
- Edge rate limits configured to standard thresholds caused edge rejections (HTTP 429) for valid enterprise partner traffic, particularly from partners conducting massive schedule syncs from concentrated corporate egress IPs in Tokyo.
- To accommodate this planned volume, the platform team and Aiko adjusted the Cloudflare rate-limiting rules on 2025-10-31, increasing the sliding-window burst allowance for partner endpoint definitions.

### 3.3 Post-Sync Reversion (2025-12-01)

As scheduled on the change calendar, the elevated partner limits expired at the close of November.

On **2025-12-01 at 10:30 JST**, Aiko executed the planned reversion:
- Partner rate limits were lowered from the temporary seasonal thresholds back to the standard baseline.
- WAF sensitivity rules for `/api/v1/partners/*` were restored to strict sliding-window buckets to safeguard origin database connection pools ahead of normal December retail booking patterns.

The table below documents the standard baseline thresholds restored on 2025-12-01 versus the seasonal November configuration:

| Endpoint Path / Identifier | Normal Baseline (Post 2025-12-01) | November Sync Threshold | Window | Action When Exceeded |
|---|---|---|---|---|
| `/api/v1/partners/*` (Per Partner Key) | 600 req / min | 2,500 req / min | 60 s | HTTP 429 with `Retry-After` |
| `/api/v1/partners/*` (Aggregate per IP) | 1,200 req / min | 4,000 req / min | 60 s | HTTP 429 |
| `/api/v1/search/*` (Client IP) | 120 req / min | 120 req / min (unchanged) | 60 s | Managed Challenge |
| `/api/v1/auth/*` (Client IP) | 30 req / min | 30 req / min (unchanged) | 60 s | HTTP 429 |
| `/admin/*` (Internal Admin Tool) | Internal egress only | Internal egress only | N/A | Block non-corporate IPs |

---

## 4. Triage and Incident Response for Edge Anomalies

### 4.1 Evaluating Rate Limit Alerts

When an alert fires regarding partner drops or edge rate limiting:

1. **Differentiate Edge 429s from Origin 429s:**
   - **Edge 429s (Cloudflare):** Generated at the edge by the WAF before reaching our servers. The origin log index `sorrel-prod-*` with `service=api` will **not** show these requests, or will show them flagged in CDN edge logs. On the "Sorrel / api" board, check the Partner Traffic panel: if requests dropped precipitously without origin 429 logs, Cloudflare is rejecting them at the edge.
   - **Origin 429s (api service):** Generated by our application code when a partner exceeds their specific contract limits. These lines appear in logs as `service=api partner=<id> status=429`.
2. **Review Alert Details:**
   - If the alert is `api-partner-reject` (one partner's rejections above 50 % for 15 minutes), check the partner panel on the dashboard.
   - Remember the operational rule: partners are limited by their contract; changes to a partner's limit are decided by Ravi with the partnerships team, never by on-call.
3. **Check Firewall Rules:**
   - **Never change firewall rules during an incident without Aiko.**
   - If an integration partner claims they are being blocked at the edge following the 2025-12-01 limit reduction, verify whether their egress IP has triggered an edge rate-limit rule or managed challenge in Cloudflare WAF analytics.
   - Do not disable the WAF rule or add arbitrary IP whitelists. If partner traffic requires adjustments, contact Ravi for partner contractual clearance and page Aiko if an edge rule modification is required.

### 4.2 Regional Cloudflare Outages (Tokyo vs. Osaka)

Because Cloudflare reports edge node status for the Tokyo and Osaka data centres separately, incident commanders and on-call engineers must verify regional impact specifically:

```
[Customer Traffic: Western Japan]  --> Osaka PoP (Degraded?)  \
                                                               --> Origin: ap-northeast-1 (Tokyo)
[Customer Traffic: Eastern Japan]  --> Tokyo PoP (Operational) /
```

1. **Customer Symptom Check:** If reports originate exclusively from businesses or users in Kansai/Western Japan while Kanto/Eastern Japan operates cleanly, check the Osaka data centre status on `www.cloudflarestatus.com`.
2. **Origin Verification:** Open the "Sorrel / web" and "Sorrel / api" boards.
   - Check if requests from ap-northeast-1 origin instances are experiencing dropped connections or sudden latency spikes from edge origin fetches.
   - Compare origin latency against edge p95 latency.
3. **First Action:** If Cloudflare confirms an incident in Tokyo or Osaka, follow the outside provider protocol:
   - Check the provider status page.
   - Confirm whether our code changed (check deploy age in alert). If our code did not change, rolling back will not help.
   - Note the status in the incident thread in `#inc-live`. Provide the status page URL and data centre status.
   - Do not adjust DNS routing or origin security certificates without platform lead (Kenji Sato) or service owner (Aiko) approval.

---

## 5. Summary Reference for On-Call Shifts

To keep on-call decisions aligned with team policy:

- **Purge takes > 1 minute:** Normal is < 60 seconds. If running for several minutes, it is an upstream Cloudflare delay. Do not trigger repeated full-cache purges. Check `www.cloudflarestatus.com` (specifically Tokyo and Osaka) and check `web` origin error rates before taking any action.
- **Firewall rule changes:** Absolutely forbidden for on-call engineers to alter during an incident without Aiko.
- **Partner rejections:** Partner sync rules returned to normal on 2025-12-01. If a partner experiences 429s, confirm whether it is an edge block or an origin contract limit. Contractual limit changes belong to Ravi; edge rule modifications belong to Aiko.
- **Logging edge issues:** When searching logs during edge errors, use:
  - `service=web status>=500 route=*` to identify if origin is generating errors or if edge is failing to fetch.
  - `service=web msg="asset load failed"` to detect browser-side delivery failures caused by mismatched or stale cached bundles.
  - `service=api partner=* status=429` to inspect origin-side partner rejections.
