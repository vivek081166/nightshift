# How to rebuild the api search index

Date: 2024-10-14  
Owner: Daniel (api)

This how-to describes the procedure for running a complete rebuild of the search index for `api`.

The `api` service powers core scheduling operations across all Sorrel environments, handling queries from `web`, mobile clients, and partner integrations. Among its responsibilities is answering location-based and availability-based queries through the "find a slot near me" feature. That feature relies on a dedicated search index maintained alongside our primary database and read replicas across our active regions: `ap-northeast`, `us-east`, and `eu-west`.

---

## 1. Scope and constraints

Rebuilding the search index is an administrative maintenance task. Keep the following operational rules in mind before considering or scheduling this procedure:

- **Working hours only:** Rebuilding the search index is a working-hours job, never a night move for on-call.
- **On-call engineers should not run this at night:** If an alert fires overnight related to search latency or an index condition, the correct first move is never to start a full index rebuild. The on-call engineer should read logs (`service=api`), review dashboard trends, evaluate customer impact, or file a ticket for working hours. If latency is high but requests still succeed without broad customer failure, follow normal handbook escalation paths rather than initiating heavy operational jobs.
- **Authority:** The rebuild is started from the job console, job `search-reindex-full`, by the api team. Engineers on other teams or on-call responders outside of the api team should coordinate directly with Daniel or Ravi before taking action.
- **Zero search downtime:** Searches do not stop while the job executes. A full rebuild takes about 70 minutes; searches keep using the old index until the new one is ready. When the build finishes and passes verification checks, the index pointer swaps atomically.

---

## 2. When to rebuild (and when not to)

The search index maintains records of businesses, active service listings, and available appointment windows. While incremental updates stream continuously from writes to the primary database, data drift, schema updates, or edge-case sync stalls can occasionally require a clean build from source records.

However, an index that is slightly behind is often within normal operating tolerance.

### Pre-check: Verify index freshness

Before doing anything else, open the metrics tool and navigate to the dashboard:
- Folder: **Sorrel / Services**
- Board: **Sorrel / api**
- Panel: **Search index: index freshness** (adjacent to **Search index: query time**)

Review the current age reported on the graph:
- **Index freshness under 6 hours:** Check the index-freshness panel on the api board first; an index under 6 hours old does not need a rebuild. Even if query latency exhibits a brief spike, an index that is less than 6 hours old is fresh enough for normal customer operations. A latency spike on a fresh index usually indicates slow database queries, connection pool saturation, or sudden traffic shifts. Check `service=api` logs for `pool exhausted` or `deadlock` instead.
- **Index freshness over 6 hours:** If freshness has degraded past 6 hours during a standard weekday, search ranking quality or newly added business offerings may begin to lag. At that stage, a full rebuild is an appropriate corrective step during working hours.

### Common scenarios

| Scenario | Symptom | Action |
|---|---|---|
| Incremental updater stalled | Freshness metric steadily climbs past 6 hours during business hours; query errors remain zero. | Run `search-reindex-full` during normal working hours. Investigate the incremental stream worker logs in parallel. |
| Nighttime latency alert | `api-latency` alerts on the search endpoint group at 03:30 JST. | **Do not rebuild.** Read logs (`service=api duration_ms>2000 endpoint=*`). File a ticket for the api team in the morning if requests are completing. |
| Customer cannot find a brand new salon | Business was registered 20 minutes ago in Tokyo. Freshness graph shows 1.5 hours. | **Do not rebuild.** An index under 6 hours old does not need a rebuild. Allow the standard sync stream to process the update. |
| Schema or mapping migration | Scheduled change to search tokens or geographical radius rules. | Plan the rebuild with Daniel or Ravi during Tuesday or Thursday afternoon deploy windows. |

---

## 3. Pre-rebuild checklist

Complete these verification steps before triggering the job console:

1. **Verify working hours:** Confirm current time is within normal business operating hours in Japan (between 09:00 and 18:00 JST), outside of deploy freezes and major traffic spikes.
2. **Review regional database health:**
   - Look at the **Sorrel / api** board.
   - Check the **Database** panel: connection pool usage must be below 70 % across all active nodes in `ap-northeast`, `us-east`, and `eu-west`.
   - Check **replica lag**: read replica lag must be steady and under 100 ms. The rebuild process streams records from the read replicas; running a full reindex against lagging replicas will extend job duration and risk connection exhaustion.
3. **Verify daily traffic cycle:**
   - Avoid launching during the lunchtime booking rush (12:00–13:00 JST) or the evening booking peak (18:00–23:00 JST), when writes on `api` and checkouts on `payments` are highest.
   - Tuesday and Thursday afternoons between 14:00 and 16:00 JST are the preferred operating windows.
4. **Communicate in chat:**
   - Drop a brief note in `#team-api`:  
     *"Starting job search-reindex-full from the job console. Index age currently at X hours. Old index will remain active during the ~70m build."*

---

## 4. Rebuild procedure

The rebuild runs asynchronously in the background via our internal administrative job system.

### Step 1: Open the job console
Navigate to the internal job console interface used by the platform and service teams. Ensure your role is authenticated with your api team credentials.

### Step 2: Select the reindex job
Locate the job definition:
- Service: `api`
- Job identifier: `search-reindex-full`

### Step 3: Verify target parameters
The job defaults to rebuilding across all active regional partitions while reading from local read replicas:
- `target_regions`: `ap-northeast`, `us-east`, `eu-west` (Tokyo is our largest partition)
- `batch_size`: `500` (default; tuned to prevent connection starvation on the replica pool)
- `swap_strategy`: `atomic_on_success`

Do not modify the default batch parameters unless previously agreed upon with Ravi or Kenji Sato.

### Step 4: Execute the job
Press **Run Job**. The console will issue a run confirmation id (e.g., `job-run-sr-8812`).

---

## 5. Monitoring during the rebuild

A full rebuild takes about 70 minutes; searches keep using the old index until the new one is ready. During this 70-minute window, active booking flows across `web` and partner integrations will continue to hit the existing index without interruption.

Keep the following metrics open throughout the run:

### Metrics to watch on "Sorrel / api"

1. **Search index: query time:**
   - p50 and p95 latency on live search requests must remain steady.
   - If query times on live customer searches begin climbing above 2.0 s, check whether database replica pools are under pressure from the rebuild reader workers.
2. **Database: connections in use per pool:**
   - Ensure the connection pool on each `api` node has headroom. If pool utilization climbs near 90 %, the reindex process might be competing with incoming booking transactions.
3. **Database: replica lag:**
   - The job streams bulk data from read replicas. A slight increase in lag (up to 500 ms) can occur, but it should not compound continuously.
4. **Error rate by endpoint group:**
   - Monitor the 4xx and 5xx panels for the search endpoint group. They should remain flat.

### Log inspection during execution

To monitor reindex worker progress or check for worker errors, run the following search in the log search tool (index `sorrel-prod-*`):

```text
service=api component=search-indexer job=search-reindex-full
```

Normal operational log output looks similar to:

```text
level=INFO service=api component=search-indexer msg="batch processed" region=ap-northeast progress_pct=34 elapsed_min=24
level=INFO service=api component=search-indexer msg="batch processed" region=us-east progress_pct=38 elapsed_min=24
level=INFO service=api component=search-indexer msg="batch processed" region=eu-west progress_pct=39 elapsed_min=24
```

If you notice batch failures, look specifically for connection pool exhaustion:

```text
service=api level=ERROR msg="pool exhausted"
```

If the reader exhausts replica connections, pause or abort the job run in the job console. Do not let database contention bubble up to the booking flow or trip the `api-pool` alert rule.

---

## 6. Verification and post-swap validation

Once the job console indicates completion (around minute 70):

1. **Confirm the pointer swap:**
   Check the job console log for the final handoff sequence:
   ```text
   level=INFO service=api component=search-indexer msg="verification passed: document count within 0.05% of replica source"
   level=INFO service=api component=search-indexer msg="atomic index swap completed across all regions"
   level=INFO service=api component=search-indexer msg="pruning old index generation"
   ```
2. **Review index freshness on dashboard:**
   Return to **Sorrel / api**.
   - The **Search index: index freshness** graph should drop immediately to near zero (typically `< 5m`).
3. **Verify query latency:**
   - Look at the **p50, p95 and p99 latency by endpoint group** panel.
   - Confirm search latency remains healthy and within normal operating bounds (well below the 2.5 s threshold defined in the `api-latency` alert rule).
4. **Run a manual search verification:**
   In your browser, visit the public booking interface via `web` (e.g., standard salon search in Tokyo) and perform a few test queries for known businesses. Verify that results return promptly with accurate slot availabilities.
5. **Close out the maintenance:**
   Post an update in `#team-api`:  
   *"Job search-reindex-full finished cleanly. Index freshness is now under 5 minutes. Query times normal across all regions."*

---

## 7. Troubleshooting failure states

If the reindex job does not complete smoothly, use the guidance below.

### Job fails midway (aborted or error status)

Because searches keep using the old index until the new one is ready, a job failure does not take down customer searches. The old index remains intact and continues serving traffic.

1. **Do not panic:** Live customer bookings are not failing.
2. **Inspect job failure reason:**
   Search logs in `sorrel-prod-*`:
   ```text
   service=api component=search-indexer level=ERROR
   ```
   Check whether the failure was caused by:
   - A transient network partition between worker nodes and database read replicas.
   - A timeout during document validation (e.g., mismatch in expected business entity counts).
   - Replica lag exceeding safety thresholds during the run.
3. **Check database status:** Confirm replica lag has returned to normal levels.
4. **Decide on retry:** If the issue was a transient replica blip, allow replica lag to settle for 15 minutes before re-triggering `search-reindex-full` in the job console. If failure persists, escalate directly to Daniel or Ravi.

### Index swap fails validation

Before swapping, the indexer checks that the record count in the newly built index matches the records in the primary database within a strict threshold. If this check fails:
- The job console marks the run as `FAILED_VERIFICATION`.
- The swap does **not** execute.
- Active traffic remains on the old index.
- Do not force a pointer swap manually. Investigate whether a batch of deleted businesses or an ongoing data cleanup created the record delta.

### Search queries become slow after the swap

If search query latency spikes immediately following the atomic swap:
1. Open the **Sorrel / api** dashboard and look at the **Search index: query time** panel.
2. Look at `service=api` logs for search query execution warnings:
   ```text
   service=api duration_ms>2000 endpoint=search
   ```
3. Check whether the search process is warming its cache or if particular complex filter queries are missing expected field statistics.
4. If latency remains elevated and risks violating our SLO error budget, consult Ravi. The job console retains the previous index generation for 2 hours post-swap, allowing the api team to roll back the pointer if an unforeseen indexing defect occurs.

---

## 8. Summary of references

- **Job Console Job:** `search-reindex-full` (Service: `api`)
- **Key Metrics Board:** `Sorrel / api` (Panels: *Search index: query time*, *Search index: index freshness*, *Database: connections in use per pool*, *Database: replica lag*)
- **Relevant Handbook Sections:**
  - Section 5.2: `api` runbook (dashboard definitions, symptoms, connection pools)
  - Section 14: Alert rules reference (`api-latency`, `api-pool`, `api-5xx`)
  - Section 15.3: Log searches for `api`
- **Primary Team Contacts:** Daniel (api), Ravi (api owner)
