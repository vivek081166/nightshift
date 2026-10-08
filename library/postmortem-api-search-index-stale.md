# Postmortem: api search index stale for a day

Date: 2024-06-14  
Owner: Ravi (api)  
Reviewers: Kenji Sato, Sara, Daniel, Hana  
Severity: P2  
Location: Shared drive, folder "Postmortems"  

---

## 1. Summary

Between the night of 2024-06-12 and the afternoon of 2024-06-13, the automated nightly rebuild job for the search index in `api` failed silently. As a consequence, the "find a slot near me" feature in `api` returned search results that were up to 26 hours out of date. 

Customers using `web` and the partner widgets were able to browse listings, but the search responses included appointments that had already been taken earlier in the day. When customers selected these phantom openings and proceeded through checkout, the transactional booking creation step on `api` detected the conflict against the primary database and correctly rejected the reservation. In total, 112 customer booking attempts failed at the final step with the error `slot no longer available`. 

The issue was diagnosed after support received multiple complaints during the morning peak. Daniel investigated the index status, verified that the worker process responsible for the batch rebuild had exited unexpectedly without throwing an uncaught alertable error, and initiated a manual index rebuild during working hours. The manual rebuild completed in 70 minutes, restoring search freshness across all active regions. Corrective actions include wiring the rebuild job into the job monitor and adding an explicit freshness metric to the primary dashboard.

---

## 2. Impact

- **Customer impact:** Customers attempting to find local openings for salons, clinics, and tutors received outdated availability. 112 booking attempts failed at the final confirmation step with `slot no longer available`. While no double-bookings occurred and no customer accounts were corrupted, these users experienced significant friction and had to restart their search.
- **Financial impact:** No erroneous charges occurred. Checkouts failed prior to payment capture or were safely abandoned before funds moved. Support handled 19 distinct customer tickets regarding slot availability mismatches.
- **Data/Privacy impact:** None. Response isolation and tenant boundaries were verified; no private booking details, notes, or cross-tenant records were exposed.
- **Service availability:** `api` request latency and HTTP status rates remained within normal operating bounds. Overall monthly error budget consumption remained low because the overall 5xx rate did not breach thresholds, though the search endpoint group exhibited functional degradation.

---

## 3. Background & System Architecture

The `api` service maintains the core scheduling domain, business configurations, operating hours, and booking state across three regions: `ap-northeast` (Tokyo), `us-east`, and `eu-west`. While standard calendar queries and explicit business page loads read directly from the primary database or regional read replicas, geographic availability discovery—specifically queries issued via "find a slot near me"—relies on a dedicated search index on `api`.

This search index optimizes multi-factor queries combining geographic radius, service category, and open slot time windows. To keep index read latency low and prevent lock contention on the primary transactional database, `api` utilizes a nightly rebuild pipeline. Every night at 02:30 JST, a batch job aggregates confirmed calendar states, prunes booked slots, computes prospective schedule blocks, and generates a fresh index snapshot.

Prior to this incident, the search index health was assessed primarily via query execution latency (`p50`, `p95`, `p99`) and connection health. The background rebuild script ran as a scheduled task on an internal worker node, writing log entries to `sorrel-prod-*` under `service=api`.

---

## 4. Timeline (all times in JST)

### 2024-06-13

- **02:30**  
  The scheduled nightly search index rebuild job initiated across worker instances in `ap-northeast-1`.
- **02:44**  
  During the aggregation phase, an uncaught memory allocation failure occurred on the batch builder process following an unindexed join on legacy salon service tags. The process terminated abruptly. Because the task exited with an unhandled signal that bypassed standard application error logging, no alert fired, and no failure event was emitted to the central monitor. The existing search index remained online and continued serving stale snapshot data from 2024-06-12 02:30.
- **07:15**  
  The morning customer booking window commenced. Commuters in Tokyo began searching for evening and weekend appointments. As popular slots were booked through direct business URLs, the search index did not invalidate those slots for users querying through "find a slot near me".
- **08:20**  
  The first customer encountered a `slot no longer available` error during final submission on `web`. The customer refreshed, saw the slot still present in search, attempted to book a second time, and failed again.
- **09:40**  
  Businesses opened their dashboards. Front-desk staff began adjusting schedules, confirming reservations, and moving appointments, widening the drift between the actual booking state in the primary database and the stale index.
- **10:15**  
  Hana (support lead) noticed a cluster of customer inquiries in the support queue reporting that salon slots displayed on search results could not be reserved. Hana posted an inquiry in `#inc-live` asking if the booking pipeline or payments was dropping reservations.
- **10:22**  
  Sara (on-call platform engineer) checked the service dashboards. Board "Sorrel / api" showed normal request rates, clean connection pool usage (below 45%), read replica lag under 12 ms, and low 5xx rates. Board "Sorrel / payments" showed zero checkout capture anomalies. Sara checked provider status pages for `aws` and `stripe`; all external systems were operational.
- **10:35**  
  Daniel (api engineer) reviewed the logs for `service=api` filtered by `status=409` and `msg="slot conflict"`. Daniel observed that requests originating from `/search/near` had a high incidence of downstream conflicts upon hitting `/bookings/confirm`.
- **10:48**  
  Daniel checked the file timestamps and generation metadata of the active search index on the `api` worker nodes. He discovered that the current search index was generated on 2024-06-12 at 02:44 JST, meaning query responses were serving data that was over 26 hours old.
- **10:55**  
  Daniel conferred with Ravi (api owner). Because rebuilding the index consumes significant database read replica capacity and memory, they evaluated whether to delay the rebuild until the quiet hours (after 22:00 JST). However, with 112 booking attempts already failing and daytime search volume climbing, Ravi decided to proceed immediately with an on-demand manual rebuild.
- **11:05**  
  Daniel started a manual index rebuild job on a designated background node in `ap-northeast`, assigning it to read strictly from read replica 2 to avoid impacting primary database connection pools or booking transaction latency.
- **11:35**  
  Daniel monitored the rebuild progress. Query latency on the "Sorrel / api" board remained stable (p95 at 180 ms for search endpoints). Database replica lag briefly rose to 85 ms on replica 2, well within tolerable thresholds.
- **12:15**  
  The manual rebuild completed successfully. The build process took exactly 70 minutes.
- **12:18**  
  The updated index files were synced across all `api` nodes in `ap-northeast`, and propagated to secondary regions. Daniel validated the new index generation timestamp (2024-06-13 12:15 JST).
- **12:30**  
  Daniel and Sara verified via log search (`service=api msg="slot conflict"`) that post-rebuild search queries returned fresh slot states. The rate of `slot no longer available` conflicts dropped back to baseline noise (< 1 per hour, typical for concurrent bookings on the same slot).
- **12:45**  
  Hana updated the open support tickets, confirming that search availability was synchronized. Ravi declared the operational response complete.

---

## 5. What Went Well

- **Data consistency guarantees held:** The transactional boundaries in `api` operated exactly as designed. When the search index presented an unavailable slot, the booking validation engine re-checked row-level locks on the primary database during checkout. It refused to persist double bookings or move money for invalid slots, preventing any data corruption or financial disputes.
- **Fast diagnosis once investigated:** Once support flagged the specific pattern to engineering, Daniel isolated the gap to search index snapshot freshness within 25 minutes using application log traces.
- **Safe manual execution:** Running the rebuild against an isolated read replica prevented the 70-minute process from exhausting connection pools or degrading live booking latency during the middle of the working day.

---

## 6. What Went Badly

- **Silent failure mode:** The nightly rebuild job lacked exit-code validation and heartbeat reporting. When the worker process terminated at 02:44 JST, the scheduler recorded the invocation without verifying successful output generation.
- **Lack of dashboard visibility:** Board "Sorrel / api" contained panels for request rates, latencies, connection pools, and database replica lag, but it did not display search index generation age or index freshness. On-call engineers had no visual metric showing that the index was drifting past its 24-hour freshness target.
- **Slow customer-driven discovery:** The platform team remained unaware of the failure for nearly eight hours after the scheduled job died. We relied on customer support tickets filed during business hours rather than an internal system alert.

---

## 7. Where We Got Lucky

- **Timing of booking peaks:** The index failure occurred during the quiet overnight hours (02:44 JST), meaning that slot divergence was relatively small until business hours began around 08:00–09:00 JST.
- **Replica headroom:** Read replica 2 had sufficient compute and memory headroom to absorb the 70-minute rebuild concurrently with the lunchtime booking traffic surge without saturating the `api` connection pool or causing replication lag to exceed alerting limits.

---

## 8. Root Cause Analysis

The search index rebuild script was invoked via a local cron daemon on a background worker rather than an instrumented pipeline. During the 02:30 run, the aggregation script encountered an unexpected nested array in service custom tags for legacy accounts, resulting in an out-of-memory exception handled by the operating system kernel killing the process (`SIGKILL`). 

Because the process was terminated abruptly by the kernel:
1. No application-level exception handler executed to log `level=ERROR` or emit a failure webhook.
2. The calling wrapper script simply completed with a non-zero exit code that was discarded by standard output redirection.
3. The serving nodes in `api` continued serving the last cleanly generated index file located in the local directory.
4. No freshness health-check existed within `api` to verify that the active index generation timestamp was less than 24 hours old.

---

## 9. Action Items

| Action Item | Type | Owner | Target Date | Status |
|---|---|---|---|---|
| Wire the nightly search index rebuild job into the centralized job monitor with expected heartbeat and non-zero exit alerting. | Prevent | Daniel (api) | 2024-06-18 | Done |
| Add an "Index Freshness" metric panel to dashboard "Sorrel / api" displaying the age (in hours) of the active search index. | Detect | Sara (platform) | 2024-06-16 | Done |
| Define an alerting rule (`api-search-index-stale`) that pages on-call if the search index age exceeds 26 hours. | Detect | Ravi (api) | 2024-06-19 | In Progress |
| Optimize the index builder aggregation query to handle untyped service tags safely and run bounded heap limits. | Prevent | Daniel (api) | 2024-06-25 | In Progress |
| Add a runbook section under 5.2 describing how to execute an out-of-band search index rebuild safely using read replicas. | Mitigate | Ravi (api) | 2024-06-21 | Done |

---

## 10. Lessons Learned & On-Call Guidance

For on-call engineers handling reports where customers state that displayed availability cannot be booked:
1. Distinguish between transactional booking failures (which report 5xx errors or connection pool exhaustion on `api`) and business conflict rejections (`status=409` or `slot no longer available`).
2. When `slot no longer available` spikes without an accompanying deploy or database pool issue, check index freshness immediately. 
3. Verify the generation timestamp on the newly added "Index Freshness" panel on dashboard "Sorrel / api". If the index age is older than 24 hours, the background rebuild has failed, and an out-of-band rebuild must be coordinated with the service owner (Ravi).
