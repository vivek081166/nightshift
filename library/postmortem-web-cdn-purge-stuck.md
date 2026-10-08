# Postmortem: CDN purge stuck after the summer campaign release

Date: 2025-07-22
Owner: Aiko (web)
Severity: P2

## 1. Summary

On Tuesday, 2025-07-22, at 14:15 JST, the web team deployed release `d-0891` containing user-facing changes and asset bundles for the annual summer booking campaign. As part of our standard web deploy pipeline, static assets were built, uploaded to object storage on aws, nodes were updated two at a time, and an automated cache purge request was sent to cloudflare.

Immediately following the origin switch, the cloudflare edge purge pipeline stalled. For 34 minutes, cloudflare's edge nodes failed to complete the cache invalidation across the ap-northeast region. Edge nodes had purged the previous campaign files upon receiving the invalidation request, but their purge processing pipeline failed to complete the ingestion of the new cache state or fall through cleanly to origin, resulting in edge-served 404s and cache misses for new asset bundles. Real browsers visiting booking pages received updated HTML documents referencing new stylesheet and script bundles that the edge did not have, resulting in unstyled pages, broken layout grids, and broken date-picker components for end users.

The on-call engineer acknowledged the alert, checked the CDN dashboard, confirmed that the purge status was stuck in progress, and reviewed the provider state. Rolling web back would not have helped because the old assets were already purged from the edge cache as well, meaning a rollback would have reintroduced older HTML pointing to assets that were equally absent at the edge, while restarting an identical purge cycle. The on-call engineer monitored the edge purge pipeline until cloudflare resolved the internal queue backlog at 14:52 JST, at which point asset propagation completed and page layouts recovered automatically. cloudflare later confirmed a delay in their purge pipeline affecting our region.

## 2. Impact

- **Customer impact**: Customers loading public booking pages and business calendar dashboards experienced broken layouts, missing styling, and non-functional interactive elements (date pickers and calendar slot selectors) across modern web browsers. Page layout distortion affected businesses primarily in the Tokyo region (ap-northeast-1).
- **Core services and data**: No customer data was exposed, corrupted, or deleted. No appointments were lost or double-booked. No payment charges, refunds, or customer balances were impacted; backend transactions across api and payments operated without degradation.
- **Support volume**: 42 customer reports were logged via support tickets and chat during the incident window, mostly inquiring whether booking pages were broken or down for maintenance.
- **Duration**: The degradation lasted 34 minutes, from 14:18 JST (when the first edge 404 spike alerted) to 14:52 JST (when cloudflare's purge pipeline caught up and asset delivery normalized).

## 3. Incident Timeline (all times JST)

| Time | Event |
|---|---|
| 14:10 | Priya initiates deploy `d-0891` for web via the deploy tool following standard review, targeting the summer campaign visual refresh. |
| 14:15 | Build steps complete. Static assets are uploaded to aws object storage. Nodes complete rolling replacement two at a time. The automated purge hook triggers against cloudflare. |
| 14:18 | `web-cdn-edge` fires: edge 4xx rate exceeds 2 % on cloudflare edge nodes in ap-northeast. Browser reports of failed asset loads begin climbing on the "Sorrel / web" dashboard. |
| 14:21 | Sara (primary on-call) acknowledges the alert within the 15-minute P2 response window and opens the incident thread in `#inc-live`. |
| 14:23 | Hana notes an influx of customer tickets reporting unstyled salon booking layouts and broken calendars. |
| 14:25 | Sara reviews the "Sorrel / web" dashboard: server-side render latency is nominal (p95 at 180 ms), origin HTTP response codes are 99.8 % 2xx, but edge 404s for `.css` and `.js` chunks are elevated to 14 % in Tokyo. |
| 14:28 | Sara accesses the cloudflare CDN dashboard to inspect cache invalidation state. The dashboard reports the purge initiated at 14:15 JST is still marked "In Progress" (normal completion is under 60 seconds). |
| 14:31 | Aiko joins the `#inc-live` thread. The team evaluates whether to execute a rollback to `d-0890`. Sara and Aiko determine that rolling back web will not help: the edge cache invalidation already wiped the references for `d-0890` assets, meaning a rollback would point incoming requests back to old bundles that the edge no longer serves, while initiating another purge request into an already stalled provider pipeline. |
| 14:34 | Sara checks `www.cloudflarestatus.com`. The status page initially shows "All Systems Operational". |
| 14:38 | Sara checks log search index `sorrel-prod-*` for `service=web msg="asset load failed"` to confirm specific paths. Client browsers report 404 errors for fingerprinted campaign assets (`/assets/campaign-2025-*.css`). |
| 14:43 | Kenji Sato joins the thread to monitor. Sara continues monitoring the CDN purge status panel every 3 minutes. Origin servers remain fully healthy and idle at low memory pressure. |
| 14:48 | cloudflare posts an update on their operational board noting a regional delay in cache management and invalidation propagation affecting ap-northeast edge data centers. |
| 14:52 | The cloudflare CDN dashboard marks the purge job for `d-0891` as "Complete". Asset fetch requests from edge to origin succeed, and cache hit ratios begin climbing. |
| 14:55 | Edge 4xx rate drops below 0.2 % on the "Sorrel / web" board. Client-side asset load failures return to baseline zero. |
| 15:02 | Hana confirms support tickets have stopped arriving and verifies sample salon booking links render styling correctly across mobile and desktop browsers. |
| 15:10 | Sara closes the incident thread in `#inc-live` and logs the event in the on-call log. |

## 4. Technical Analysis

### 4.1 How web asset delivery is architected

The web service consists of six nodes per region behind an aws load balancer, scaling dynamically to twelve. The service server-renders HTML templates on the fly and retrieves dynamic booking and merchant configuration directly from api. It maintains no local persistence, relying on a shared cache for customer sessions.

Static assets—such as UI stylesheets, client-side bundle chunks, vendor libraries, and promotional images—are compiled during the build phase of a deploy, fingerprinted with cryptographic hash suffixes (for example, `app-bundle-3f8a1c.js`), and pushed to an aws object storage bucket. When a browser requests a page, the origin server outputs HTML referencing these hashed asset URLs, which resolve through cloudflare's CDN.

```
Browser -> cloudflare Edge -> (Cache Hit)  -> Static Assets (Served instantly)
                           -> (Cache Miss) -> aws Object Storage Origin
```

Under normal deploy conditions:
1. New assets with new hash names are uploaded to aws object storage.
2. Web nodes are updated two at a time to render HTML pointing to the new file hashes.
3. A purge call is dispatched to cloudflare via their API to clear cached index pages, root assets, and shared bundles so edge nodes fetch fresh resources immediately.
4. Purges typically complete in under 60 seconds worldwide.

### 4.2 The failure mechanism

When deploy `d-0891` ran at 14:15 JST, the upload of new campaign stylesheets and scripts succeeded without error. However, cloudflare experienced an internal pipeline delay in their regional control plane.

When our automated deploy script called the purge endpoint, the edge invalidation entered cloudflare's processing queue. Cloudflare edge nodes dropped their current cache tables for our zone, but the distributed pipeline responsible for confirming the invalidation and synchronizing origin-pull rules stalled. 

During this 34-minute delay:
- Browsers requesting booking pages received the new HTML rendered by web nodes running `d-0891`.
- The new HTML told browsers to download new files (e.g., `campaign-summer-7a2e.css`).
- Browsers sent requests to cloudflare edge nodes for these new files.
- Because the purge pipeline was blocked in an intermediate state, edge nodes failed to execute clean origin pulls for the newly introduced hashes, returning edge-generated 404 responses or connection timeouts to clients.
- Concurrently, because the previous files (from `d-0890`) had already been dropped from edge memory, any cached browser sessions or references to older assets were also failing.

### 4.3 Why rolling back was not the correct move

In many incidents occurring immediately after a deploy, rolling back the alerting service to its previous deploy is the standard first move. However, the on-call engineer correctly recognized that the failure was entirely located within the edge provider's purge queue rather than inside the web container code or origin rendering logic.

Had on-call initiated a rollback to `d-0890` in the deploy tool:
1. The tool would have reverted web nodes to the prior version over a four-minute window.
2. The nodes would have begun rendering HTML referencing old asset hashes (`campaign-spring-9b1d.css`).
3. Because the initial invalidation had already wiped the old assets from edge cache, cloudflare would have had to fetch those old assets from aws storage.
4. The rollback would have issued another automated purge request to cloudflare, adding another job to an already stuck queue.
5. Users would have continued to receive broken layouts, and the incident duration would have been extended.

Waiting for the provider to complete processing while confirming origin health on the "Sorrel / web" board was the technically sound decision.

## 5. What Went Well

- **Alerting accuracy**: The `web-cdn-edge` alert fired promptly at 14:18 JST, within three minutes of the edge error rate crossing the 2 % threshold.
- **Root cause isolation**: The on-call engineer went directly to the provider's management console and dashboard rather than attempting invasive code changes or unnecessary infrastructure restarts.
- **Avoided harmful actions**: The team avoided an unnecessary rollback that would have exacerbated edge cache inconsistency.
- **Service isolation**: api and payments were completely insulated from the front-end layout failures; no transaction processing errors occurred.

## 6. What Went Badly

- **Provider visibility lag**: The public status page at `www.cloudflarestatus.com` remained green for more than 30 minutes after our alert fired, delaying external confirmation of the incident. We had to rely entirely on internal metrics and the provider's specific account dashboard.
- **Premature campaign notification**: The marketing team and partner channels were alerted that the summer campaign was live as soon as the deploy script finished origin rollout, rather than waiting for CDN cache propagation to complete. This resulted in customers landing on broken layouts immediately upon receiving announcement links.
- **Lack of automated purge verification in deployment scripts**: The deploy tool marked the release as complete as soon as origin instances reported healthy, without confirming that the downstream CDN purge request had transitioned to a completed state.

## 7. Where We Got Lucky

- The incident occurred at 14:18 JST on a Tuesday. According to Sorrel's traffic profiles, Tuesday early afternoon is significantly quieter than our evening peak (18:00–23:00 JST), which kept the number of affected booking attempts low.
- Backend API endpoints and checkout routes were not cached at the edge and continued to operate normally. Customers who had previously loaded pages or were in active checkout sessions were able to finalize bookings without financial discrepancy.

## 8. Action Items

| Action Item | Type | Owner | Target Date |
|---|---|---|---|
| Update the web release checklist to require engineers to verify that the CDN purge reports complete in the dashboard before announcing any campaign or visual updates. | Process | Aiko | 2025-07-25 |
| Update the deploy pipeline hooks for web to query the cloudflare purge status API and block deploy completion until the purge state is verified as complete, with a 5-minute timeout. | Prevent | Sara | 2025-08-08 |
| Add a direct synthetic monitor to our metrics suite that requests the newly deployed primary CSS bundle through the CDN edge immediately post-deploy, alerting if the edge returns non-200. | Detect | Priya | 2025-08-15 |
| Document CDN edge purge delay troubleshooting steps directly within section 5.1 of the internal runbooks for faster on-call reference. | Document | Aiko | 2025-07-29 |
