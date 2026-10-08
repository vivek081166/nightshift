# Postmortem: web blank pages after a font upload

Date: 2024-01-23  
Owner: Aiko (web)  
Severity: P2  
Status: Closed  

---

## 1. Summary

On Tuesday, 2024-01-23 at 19:12 JST, `web` deploy `d-4821` reached production across all active regions. The deploy included an update to brand typography across the public booking flow and customer account pages. Due to an upload job failure during the static asset build phase, two Latin/Kana display font files (`sorrel-sans-display-medium.woff2` and `sorrel-sans-display-bold.woff2`) were omitted from the object storage upload, despite being registered in the front-end asset manifest.

Web browsers that implement standard font fallback or timed rendering displayed text using system fallbacks after an asset fetch 404. However, WebKit/Safari instances on iOS and macOS entered an extended render-blocking state while waiting for the font assets defined in CSS `@font-face` rules with `font-display: block`, resulting in blank viewports across primary customer flows.

The issue was diagnosed by Priya (web engineer), who noticed 404 responses for static font requests at the edge and confirmed the discrepancy by comparing the build's asset manifest against the object storage bucket listing. The missing font files were rebuilt and re-uploaded directly to the asset bucket at 19:40 JST, followed by an edge cache purge. Normal rendering returned across all browser targets by 19:43 JST. The incident lasted 31 minutes, with 9 customer support reports received.

To prevent recurrence, the asset build pipeline has been updated with a pre-deploy verification step that asserts every asset path present in the generated manifest exists in object storage before node switching can proceed.

---

## 2. Impact

- **Customer impact:** Public booking pages and customer account views rendered blank for visitors using Safari on iOS and macOS. Chromium and Firefox users experienced brief font flickering (FOUT) before falling back to system fonts, but remained functional.
- **Support impact:** Support received 9 distinct customer tickets (6 business owners reporting broken booking links from mobile devices, 3 end customers reporting that they could not see available service slots).
- **Service availability:** `api`, `payments`, and `notifier` were unaffected. Core HTTP 2xx rates on `web` remained steady because server-side page delivery succeeded; degradation was isolated to browser-side rendering and CDN edge 404s for the two missing font assets.
- **Financial and data impact:** No data exposure occurred. No incorrect charges or payment failures occurred. Booking creation rates dropped approximately 14% between 19:15 and 19:40 JST, correlating with mobile Safari traffic shares during the evening peak.

---

## 3. Timeline (all times JST)

| Time | Event |
|---|---|
| 18:58 | Priya merges pull request `#1182` updating typography tokens and font definitions in `web`. |
| 19:04 | Deploy pipeline for `d-4821` begins. Webpack build generates assets and outputs `manifest.json`. Asset upload step encounters intermittent object storage socket resets but continues without throwing an exit code error. |
| 19:12 | Deploy `d-4821` completes node roll across `ap-northeast`, `us-east`, and `eu-west`. Traffic begins routing to the new release. |
| 19:18 | First customer report arrives in the support queue: a hair salon owner notes that opening their booking link on an iPhone shows a completely blank white screen. |
| 19:20 | The alert `web-blank-render` fires (browser-reported blank renders above 1% for 2 minutes). Sara (on-call) acknowledges. |
| 19:22 | Sara opens incident thread in `#inc-live`. The board "Sorrel / web" shows origin response codes are 200, but the panel "Front-end errors reported by browsers" exhibits a sharp spike in client-side render timeouts on Safari user agents. Edge 4xx rate on the CDN panel rises from 0.1% to 1.4%. |
| 19:24 | Sara examines `service=web msg="asset load failed"` in the log search tool. Logs indicate repeated 404 errors for two files: `/static/fonts/sorrel-sans-display-medium.woff2` and `/static/fonts/sorrel-sans-display-bold.woff2`. |
| 19:26 | Sara pages Aiko (web owner) via the paging tool. Aiko acknowledges within 2 minutes. Priya joins the thread after seeing the page for deploy `d-4821`. |
| 19:29 | Support lead Hana reports 4 additional tickets arriving from mobile users unable to see salon schedules. |
| 19:31 | Priya pulls the build artifact manifest from the deploy tool and lists the contents of the production asset bucket in object storage. By comparing the asset manifest with the bucket listing, Priya identifies that every compiled script and stylesheet is present, but the two font files listed in the manifest never reached the bucket. |
| 19:35 | Aiko and Priya review mitigation options: rolling back `web` via the deploy tool or re-uploading the missing font files. Aiko approves re-uploading the assets to avoid disrupting active node sessions during the evening peak, as the previous deploy had already been superseded in the CDN edge configuration. |
| 19:37 | Priya runs a targeted asset re-upload for the missing font paths directly to the object storage bucket with production caching headers. |
| 19:40 | Bucket listing confirms both font files exist in object storage. Sara initiates a cache purge for the specific paths via the CDN dashboard. |
| 19:41 | CDN edge metrics show font asset requests returning 200 OK. Internal testing on iOS Safari confirms booking pages render typography correctly. |
| 19:43 | Browser-reported blank render metric on "Sorrel / web" drops below 0.1%. Customer reports cease. |
| 19:50 | Incident declared resolved. Sara logs the line in the on-call log and closes the incident thread. |

---

## 4. Technical Analysis

### 4.1 Asset compilation and deploy flow

The `web` service serves server-rendered HTML backed by static assets distributed via Cloudflare. When a new release is prepared in the deploy tool, the build agent runs:

1. Asset compilation (compiling SCSS, TypeScript, font declarations).
2. Manifest generation (`manifest.json`), mapping logical resource identifiers to content-hashed file paths.
3. Bucket synchronization, transferring compiled files from the build runner to AWS S3 object storage.
4. Rolling restart of `web` instances, two nodes at a time per region, while pointing the CDN to the asset set.

During the build for `d-4821`, the asset pipeline included newly added font files. The local build produced:
- `sorrel-sans-display-medium.woff2`
- `sorrel-sans-display-bold.woff2`
- `sorrel-sans-regular.woff2`

The manifest generator properly recorded all three files. However, during the synchronization step, the script relied on an unbuffered upload loop that ignored individual non-fatal network exceptions on parallel transfers. A brief network blip to the object storage endpoint resulted in failed PUT requests for the medium and bold font files. Because the script's exit code was bound only to the final script execution rather than checking transfer status codes, the build pipeline evaluated the step as successful and proceeded to deploy `d-4821`.

### 4.2 Browser behaviour and render blocking

The updated stylesheet imported the fonts with the following declaration:

```css
@font-face {
  font-family: 'Sorrel Sans Display';
  src: url('/static/fonts/sorrel-sans-display-bold.woff2') format('woff2');
  font-weight: 700;
  font-style: normal;
  font-display: block;
}
```

The property `font-display: block` instructs the browser to apply a short block period (typically 3 seconds) where the text remains invisible while the font is fetched. 

In Chromium and Firefox, when the CDN returned an immediate HTTP 404 from the origin/storage bucket, the browser runtime aborted the block period and immediately rendered the text with the system fallback font.

In Safari (WebKit), however, the interaction of `font-display: block` with our client-side single-page mount script caused the main DOM render tree to halt layout computations. When the font request failed, Safari did not drop back cleanly to the system font stack on specific dynamically injected container elements, leaving the entire viewport white until the page hit an unhandled script render timeout. This accounted for why the issue was reported exclusively by users on Safari and iOS web views.

```
+-------------------------------------------------------------------+
| web build: d-4821                                                 |
| 1. Compile assets: OK                                             |
| 2. Generate manifest.json: Lists 3 font files                     |
| 3. Upload to AWS S3: 2 files dropped due to silent socket error   |
+-------------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------------+
| AWS S3 (Origin Storage)                                           |
| - sorrel-sans-regular.woff2 (Present)                              |
| - sorrel-sans-display-medium.woff2 (MISSING)                      |
| - sorrel-sans-display-bold.woff2   (MISSING)                      |
+-------------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------------+
| Cloudflare CDN Edge Cache                                         |
| - Passes request to S3 origin -> Caches HTTP 404 for missing fonts|
+-------------------------------------------------------------------+
           |                                             |
           v                                             v
+-------------------------------+             +-------------------------------+
| Chrome / Firefox              |             | Safari / WebKit (iOS & macOS) |
| - Receives 404                |             | - Receives 404                |
| - Cancels block period        |             | - Block period stalls render  |
| - Falls back to system font   |             | - Viewport remains BLANK      |
| Result: Degraded visuals      |             | Result: Total failure (Blank) |
+-------------------------------+             +-------------------------------+
```

---

## 5. What Went Well

- **Alert accuracy:** The `web-blank-render` alert rule fired within 8 minutes of full deployment, correctly highlighting front-end browser failures despite origin HTTP status codes being predominantly 200 OK.
- **Log clarity:** Server-side logs and browser error beacons in `sorrel-prod-*` explicitly flagged missing asset paths (`msg="asset load failed"`), preventing the team from pursuing false leads in `api` or database query latency.
- **Rapid root cause isolation:** Priya quickly checked the physical bucket contents against the manifest rather than assuming the compiled bundle code had a logic bug.
- **Minimal disruption during fix:** Re-uploading the missing assets directly to object storage repaired the issue cleanly without triggering another round of node restarts during our evening peak traffic window (18:00–23:00 JST).

---

## 6. What Went Badly

- **Build pipeline verification was weak:** The deploy pipeline trusted the build runner without verifying that every asset referenced by `manifest.json` actually landed in the storage bucket.
- **Silent failure in asset script:** The synchronization tool consumed transfer exceptions without returning a non-zero exit code, masking the network failure from the CI/CD pipeline.
- **Inadequate cross-browser testing for assets:** Font updates were verified in Chromium during local review; the `font-display: block` failure mode specific to Safari was not caught prior to deployment.
- **Status page delay:** Because the initial assessment wavered between a localized edge failure and a deployment issue, the status page was not updated within the 20-minute window specified for user-visible P1/P2 issues. By the time the decision to post was reached, the fix was already deployed.

---

## 7. Where We Got Lucky

- The deploy occurred at 19:12 JST, just before the absolute peak of customer checkout volume (19:30–21:00 JST). Had the failure persisted an hour longer, checkout abandonment would have been significantly higher.
- The failure was confined to the two display font weights. Had the regular font file also failed, fallback failure rates on desktop browsers would likely have climbed.
- The build artifacts remained preserved on the CI runner workspace, allowing Priya to locate the exact uncompressed source files and upload them without having to trigger a complete multi-stage re-compilation of `web`.

---

## 8. Action Items

| Action Item | Type | Owner | Target Date |
|---|---|---|---|
| Update `web` build pipeline to validate that every entry in `manifest.json` exists in object storage before releasing. | Prevent | Priya | 2024-01-26 |
| Modify the asset upload script to fail immediately (`set -e`) on any non-200 response from object storage. | Prevent | Sara | 2024-01-26 |
| Change `@font-face` definitions across `web` from `font-display: block` to `font-display: swap` to ensure text is never invisible on network or asset failures. | Mitigate | Priya | 2024-01-29 |
| Add automated front-end smoke tests running headless WebKit against staging deployments to catch render-blocking issues. | Detect | Aiko | 2024-02-09 |
| Add a dashboard widget on "Sorrel / web" tracking edge 404 responses specifically broken down by static asset extension (`.woff2`, `.js`, `.css`). | Detect | Sara | 2024-02-02 |
| Review status page escalation procedure during shift handovers to ensure support updates are pushed promptly when user-facing bugs cross 15 minutes. | Process | Hana | 2024-01-30 |

---

## 9. Review and Approvals

- **Service Owner:** Aiko (web) — *Approved 2024-01-24*  
- **Platform Lead:** Kenji Sato — *Approved 2024-01-25*
