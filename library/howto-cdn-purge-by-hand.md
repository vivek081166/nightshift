# How to purge the CDN by hand

Last updated: 2025-05-12  
Owner: Aiko (web)

This guide covers how to execute a manual CDN cache purge for Sorrel's web assets. It is intended for engineers on the primary on-call rotation, platform engineers, and web service engineers during active incidents or post-deploy asset anomalies.

---

## 1. Context and Scope

Sorrel's `web` service renders booking and administrative interfaces on the server and relies on our CDN provider (cloudflare) for caching public HTML and serving static assets (JavaScript bundles, CSS stylesheets, icons, fonts, and client-side images). Assets are generated at deploy time, pushed to object storage on aws, and distributed to edge data centers worldwide.

During a normal automated deploy via the deploy tool, the build pipeline registers a cache invalidation request with cloudflare. However, an edge sync delay, an interrupted deploy hook, or an incomplete asset propagation can leave the edge holding stale bundles or pointing to missing static hashes. This typically manifests in elevated edge 4xx rates, broken layouts, or customer reports of blank screens (`web-blank-render` or `web-cdn-edge` alerts).

### What on-call is authorized to do

- **Allowed:** On-call may re-run a purge for web assets from the CDN dashboard.
- **Allowed:** Check purge progress, origin load, and edge status codes.
- **Forbidden:** Firewall rules are never changed without Aiko. Even if an incident involves a traffic spike, crawler surge, or high 4xx/5xx counts at the edge, rate limits and WAF rules are owned by Aiko. Changing edge firewall rules during an incident without her direct instruction can easily block legitimate customers or integration partners.

---

## 2. When to Execute a Manual Purge

Purging the edge cache by hand is an operational corrective move. It is appropriate in a narrow set of circumstances:

1. **Stale Asset Mismatch Post-Deploy:** A recent `web` deploy completed, but browsers report script errors or missing chunks because the CDN edge is still serving an older index HTML pointing to pruned asset hashes, or caching an old bundle version.
2. **Delayed Invalidation:** The automated deploy hook completed, but edge nodes in specific regions are serving stale responses well past the deploy window.
3. **Rollback Asset Re-pointing:** Following a rollback of `web` via the deploy tool (project "sorrel", service "web"), edge caches need to flush intermediate assets to ensure alignment with the previous deploy's asset set.

### When NOT to purge

- **Origin is failing:** If `web` origin nodes are returning 5xx responses (e.g., node memory pressure, server render timeouts, or inability to connect to `api`), purging the cache will strip away any healthy edge caches and force even more traffic onto failing origin nodes. Check the "Sorrel / web" metrics board first.
- **Provider-wide outage:** If cloudflare itself is experiencing a platform-wide outage or regional core disruption (check `www.cloudflarestatus.com`), manual purge API calls will either fail or queue indefinitely.

---

## 3. Critical Rule: Purge by URL Prefix Only

> **WARNING:** Always purge by URL prefix, not "purge everything". Purging everything sends all traffic to the origin at once.

The CDN dashboard provides a button labeled "Purge Everything" (or "Purge All Assets"). **Do not use this option.**

Sorrel runs between six and twelve `web` nodes per active region (ap-northeast-1, us-east-1, eu-west-1). These server nodes handle server-side rendering for public booking schedules, user sessions, and support admin dashboards. Our origin sizing assumes a steady CDN cache hit ratio for static media, bundled scripts, stylesheets, and cached public pages. 

If you issue a global purge ("purge everything"):
- Millions of cached objects across all global edge nodes are instantly evicted.
- Every incoming browser request immediately misses the cache and punches through to the origin cluster simultaneously (the "thundering herd" problem).
- `web` node CPU spikes to 100%, render queues back up, local render caches thrash, and `web` nodes begin restarting due to heap exhaustion or out-of-memory errors.
- As `web` degrades, requests to `api` back up, connection pools exhaust, and a localized asset issue cascades into a site-wide P1 incident.

Always limit manual purges to specific URL prefixes matching the updated static asset bundles or the affected subpaths.

---

## 4. Step-by-Step Purge Procedure

Follow these operational steps whenever executing a manual cache eviction.

```
+-------------------------------------------------------------+
| 1. Assess Origin Load ("Sorrel / web" Dashboard)             |
|    - Confirm node CPU and memory are stable                 |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
| 2. Open CDN Dashboard & Identify Asset Prefixes             |
|    - Target `/static/`, `/assets/`, or specific release tags |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
| 3. Submit Purge Request by URL Prefix                       |
|    - DO NOT click "Purge Everything"                        |
|    - Record the returned Purge ID                           |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
| 4. Monitor Purge Panel (Normal completion: < 1 minute)      |
|    - Check Status transition: Received -> Processing -> Done|
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
| 5. Post Purge ID and Details to Incident Thread (`#inc-live`)|
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
| 6. Verify Edge & Origin Metrics (Hit ratio, 4xx/5xx rates)  |
+-------------------------------------------------------------+
```

### Step 1: Pre-Check Origin Capacity

Before touching the CDN dashboard, open the metrics tool and check:
- Dashboard: **Sorrel / web**
- Panels:
  - `Node health: CPU, memory, restarts, per node`
  - `Request rate, split by status class`
  - `CDN: cache hit ratio, origin requests, 4xx and 5xx at the edge`

Confirm that `web` origin nodes are healthy. If memory is already climbing near limits or nodes are restarting, coordinate with Sara or Kenji Sato before invalidating anything that will increase origin request volume.

### Step 2: Open the CDN Dashboard

1. Navigate to the cloudflare management console using your platform credentials.
2. Select the zone corresponding to the environment: `sorrel.app` (production).
3. From the left navigation menu, open **Caching**, then click on **Configuration**.
4. Locate the **Purge Cache** section.

### Step 3: Configure URL Prefix Purge

1. Click on **Custom Purge** (do not click *Purge Everything*).
2. Select the **URL or Prefix** purge mode.
3. Supply the exact URL prefixes requiring eviction. Typical targets during asset deploy issues include:
   - `https://sorrel.app/static/`
   - `https://sorrel.app/assets/`
   - `https://app.sorrel.app/assets/`
4. If invalidating a specific broken bundle identified in browser errors (from log search `service=web msg="asset load failed"`), enter the specific URLs:
   - `https://sorrel.app/assets/app-[hash].js`
   - `https://sorrel.app/assets/vendor-[hash].js`
5. Double-check that no wildcards encompass root dynamic routes (e.g., do not purge `https://sorrel.app/*` unless specifically targeting isolated subpaths).
6. Click **Submit Purge**.

### Step 4: Track Purge Status

1. A normal purge completes within a minute; check its status on the CDN dashboard's purge panel.
2. In the CDN dashboard, navigate to **Caching** > **Purge History / Status Panel**.
3. Locate your purge request. The dashboard will show:
   - **Purge ID** (a UUID such as `prg_01hv89k2m...`)
   - **Timestamp** (UTC/JST)
   - **Scope** (Prefix list)
   - **Status** (`Received`, `Processing`, or `Completed`)
4. Refresh the status panel. A healthy purge transition should take between 15 and 45 seconds to reach `Completed` across all edge data centers.
5. If the purge remains in `Processing` for more than three minutes, suspect a provider-side delay. Check `www.cloudflarestatus.com` to see if the CDN provider is experiencing edge management or control plane latency.

### Step 5: Log the Action in Chat

Per Sorrel incident protocol, every production state modification must be documented immediately.

Write the purge id in the incident thread in `#inc-live`.

Post a message in the active incident thread following this format:

```text
Action taken: Manual CDN prefix purge executed via cloudflare dashboard.
Purge ID: prg_01hv89k2m4x8ab9c1d2e
Prefixes purged:
- https://sorrel.app/static/
- https://sorrel.app/assets/
Status: Completed on purge panel (took ~40s).
Reason: Clearing stale JS assets following web deploy d-4819.
```

---

## 5. Post-Purge Verification and Monitoring

Once the purge status indicates `Completed`, watch the metrics tool for at least ten minutes to verify resolution and ensure origin stability.

### 1. Monitor Edge vs. Origin Metrics
Open the **Sorrel / web** dashboard and observe:
- **CDN: cache hit ratio:** Expect a momentary dip in hit ratio (e.g., dropping from ~92% down to 70–75%), followed by a steady climb back toward normal within 10 to 15 minutes as assets are re-cached.
- **Origin requests:** Expect a brief, manageable bump in requests per second hitting the 6–12 origin nodes. Verify CPU remains under 65% across all active nodes.
- **CDN: 4xx and 5xx at the edge:** The edge error rate should decline back below the 1% threshold.
- **Front-end errors reported by browsers:** Script errors and `asset load failed` log entries should drop to baseline levels.

### 2. Verify Log Search
Run the following search in the log search tool on `sorrel-prod-*` for the past 5 minutes:

```text
service=web msg="asset load failed"
```

The count should taper off. If requests continue to fail, verify whether the browser is still requesting assets that were entirely omitted from the build artifact uploaded to aws object storage.

---

## 6. Escalation and Failure Paths

If the manual purge does not resolve the issue, or if secondary symptoms emerge, follow the standard escalation pathways:

| Symptom / Situation | What it means | Action |
|---|---|---|
| Purge completes, but edge continues returning old assets | Cache rule precedence conflict, or client browser caches holding stale ETags. | Check CDN cache headers in browser dev tools. Consult Priya or Aiko. |
| Purge panel shows `Failed` or stays in `Processing` > 5 min | cloudflare control plane is degraded or experiencing edge propagation delays. | Check `www.cloudflarestatus.com`. Post provider status link to `#inc-live`. Do not repeatedly spam purge requests. |
| Origin CPU hits > 85% or nodes restart post-purge | Cache stampede / origin load too high. | Autoscaling should add nodes up to 12. If nodes crash with `msg="oom"`, alert Sara or Kenji Sato. |
| Customers still see 403 Forbidden or 1020 Access Denied | Cloudflare WAF / firewall rule is blocking traffic. | **Do not modify firewall rules yourself.** Page Aiko via the paging tool (schedule "Sorrel primary" / web owner escalation). |
| Issue began immediately after a recent `web` deploy (< 30 min) and purge did not fix it | Bad front-end build or broken page template in the release. | Roll back `web` in the deploy tool to the previous deploy. Notify Aiko. |

---

## 7. Incident Log Example

For shift records, ensure your entry in the on-call log accurately reflects the sequence of events.

**Example log entry:**
`2025-05-12 14:22 JST | web | P2 | read logs | Detected asset hash 404s after deploy d-4819; executed manual CDN prefix purge prg_01hv89k2m4x8ab9c1d2e for /assets/, resolving edge errors.`

If the purge was part of an incident response where Aiko was consulted regarding CDN configuration or where support was fielding customer tickets, keep Hana updated on `#inc-live` so the support team knows when asset propagation has cleared for end users.
