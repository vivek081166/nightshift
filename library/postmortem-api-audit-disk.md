# Postmortem: api audit log writer stopped after a disk filled

Date: 2025-12-15  
Owner: Ravi (api)  
Author: Sara (platform)  
Incident reference: INC-2025-12-11-01  
Severity: P2  
Status: Closed  

---

## 1. Summary

On Thursday, 2025-12-11, between 14:10 JST and 16:15 JST, the internal audit log writer inside `api` in the `ap-northeast` region stopped persisting records. The local disk partition dedicated to the audit spool process reached 100% utilisation, causing the background audit worker thread to halt on an uncaught write exception. 

The core user-facing flows of `api`—including appointment bookings, search queries, partner requests, and account updates—continued serving requests normally with healthy latencies and standard status codes. No customers or businesses observed any degradation, and no user-facing errors were generated. However, for a duration of 2 hours and 5 minutes, zero audit records were recorded for state changes executed across `ap-northeast`. 

The incident was identified after an internal investigation triggered by the `api-audit-gap` alert rule. A temporary disk clear restored real-time audit logging at 16:15 JST. Over the subsequent two days, Daniel (api engineer) reconstructed the missing records by parsing historical web server payloads in `sorrel-prod-*`, recovering all 18,320 omitted audit events without permanent data loss. Mitigations have been scheduled to introduce direct spool disk monitoring and automated offloading to object storage when volume utilisation reaches 70%.

---

## 2. Impact

- **Customer impact:** None. Customers were able to browse available slots, book appointments, receive confirmation notices, and process deposits or payments without disruption. Businesses experienced no interruptions managing calendars or viewing dashboard details.
- **Financial impact:** 0 JPY. No charges, refunds, or payouts were altered, delayed, or duplicated.
- **Data loss & compliance impact:** 18,320 audit trail entries covering booking creations, cancellations, reschedules, and administrative modifications were not written to the primary audit datastore at run time. Because the audit trail is required for business disputes, change tracking, and regulatory auditability, this constituted a temporary compliance gap under section 7.12 of the on-call handbook. All 18,320 entries were subsequently backfilled from structured application request logs by 2025-12-13.
- **Error budget:** Zero impact on the user-facing booking SLO error budget.

---

## 3. Background

`api` runs across three regions: `ap-northeast` (Tokyo), `us-east`, and `eu-west`. Each region operates eight nodes behind an application load balancer, scaling up to twenty during peak daytime traffic. 

When a mutating state change completes—such as a user reserving a hair salon chair or a music tutor updating weekly availability—the request worker executes the database transaction and places an audit payload onto an asynchronous in-memory ring buffer. A co-located background audit process drains this buffer, batches the changes into structured event files on a local NVMe spool disk (`/var/spool/sorrel/audit`), and synchronously flushes them to the permanent audit storage backend.

The spool volume exists to buffer audit events if the primary audit database experiences network jitter or short replication delays. The audit worker design isolates booking execution paths from audit persistence: if writing to disk or the backend database encounters an unexpected block, the main transaction pool does not block the customer's request. While this prevents customer checkouts from failing when auxiliary logging systems degrade, it allows audit failures to occur silently from the perspective of standard edge HTTP error metrics.

---

## 4. Timeline (all times JST)

### 2025-12-11

| Time | Who / System | Event |
|---|---|---|
| 09:15 | Traffic | Morning business traffic peak begins across Tokyo. Write requests on `api` rise to normal daytime levels. |
| 13:40 | System | The log rotation cron job for the audit spool volume on `api` worker nodes fails to prune rotated raw buffers due to an unhandled file handle lock from a weekly metrics export script. |
| 14:02 | System | Spool storage utilization on node `api-apne-03` crosses 95%. |
| 14:10 | System | Disk utilisation on `/var/spool/sorrel/audit` hits 100% on the primary writer node. The background audit flush process raises an unhandled `ENOSPC` (no space left on device) POSIX error, stops its batch execution loop, and halts. Audit entry generation ceases across the instance group. |
| 14:10–14:30 | System | Customer bookings, payments, and account actions continue processing normally. Standard `Sorrel / api` dashboard metrics show normal request rates, p95 latency under 180 ms, and zero elevated 5xx codes. |
| 14:30 | Alert system | Rule `api-audit-gap` evaluates: audit log writes have remained at zero for 20 minutes while `api` continues processing inbound booking requests above baseline. |
| 14:30 | Paging system | Paging tool sends an alert to the primary on-call engineer (Sara). |
| 14:34 | Sara | Acknowledges page within the 5-minute requirement. Opens incident thread in `#inc-live` (`#inc-live-20251211-audit`). Assesses severity as P2 (internal compliance and safety net failure; customer traffic unaffected). |
| 14:37 | Sara | Verifies dashboards in the metrics tool under "Sorrel / Services / Sorrel / api". Booking endpoints show steady volume, connection pools are healthy at 24% capacity, and replica lag is under 12 ms. Checks the SLO panel: monthly error budget consumption is zero. |
| 14:42 | Sara | Opens the log search tool and queries index `sorrel-prod-*` using the filter `service=api component=audit level=ERROR`. Discovers repeating error traces: `SystemError: /var/spool/sorrel/audit: write failed: ENOSPC`. |
| 14:46 | Sara | Checks deploy history for service `api`. Last deploy was `d-4812` released 38 hours prior (2025-12-09 23:30 JST) by Daniel. Eliminates recent software deploy as the immediate cause. |
| 14:50 | Sara | Investigates node system metrics on the host. Confirms root partitions have adequate space (42% used), but the dedicated spool mount on the background writer instance is at 100%. |
| 14:55 | Sara | Notes in `#inc-live` that the audit writer has halted due to disk exhaustion and loops in Ravi (api owner) for visibility. |
| 15:02 | Ravi | Joins the `#inc-live` thread. Reviews the spool configuration and confirms that the memory buffers have dropped pending writes, meaning audit events are no longer being spooled or transmitted to the database. |
| 15:15 | Sara, Ravi | Confirm that customer booking operations remain intact, but verify that no audit records have been committed to the primary audit datastore since 14:10 JST. |
| 15:30 | Daniel | Joins the thread to assist with data recovery planning. Reviews `service=api` request log formatting to verify whether incoming state-changing requests retain sufficient transactional metadata to allow record reconstruction. |
| 15:45 | Sara | Safely purges obsolete compressed debug dumps located in the spool mount path that were held open by the stale metrics export process. Clears 14 GB of dead files. |
| 16:10 | Ravi | Restarts the background audit daemon on the affected nodes. The process reinitialises the spool structure and re-establishes its database pipeline. |
| 16:15 | System | Audit log write rate returns to normal baseline (approx. 145 entries/min). System health checks clear. |
| 16:30 | Sara | Closes the active incident in `#inc-live`. Logs incident summary in the on-call log: `2025-12-11 14:30 JST | api | P2 | read logs | Found spool disk full via component=audit query; purged dead space and restarted writer`. Hands over data recovery tracking to Daniel and Ravi. |

---

## 5. What Went Well

- **Alerting fired accurately:** The `api-audit-gap` alert rule worked as designed. It flagged the silence in audit persistence at the 20-minute threshold despite standard edge health, uptime, and latency metrics being completely green.
- **Fail-safe architecture held:** The decoupling of the audit persistence path from the main booking request cycle ensured that business-critical operations remained uninterrupted. Hair salons, clinics, and other businesses completed reservations and collected deposits without customer-facing errors.
- **Log retention was intact:** Application request logs in `sorrel-prod-*` had complete debug fidelity and structured payload fields, retaining all booking IDs, user references, action types, and parameters needed to rebuild the lost records.
- **Handbook adherence:** Incident severity was accurately classified as P2 in accordance with Section 2 ("an internal safety net is failing... while the product still works for customers"), and the handbook's diagnostic search filters for `component=audit level=ERROR` quickly surfaced the underlying issue.

---

## 6. What Went Badly

- **Missing disk monitoring on spool volume:** While root disk partitions have standard alerting thresholds (such as the `web-disk` alert rule on web frontends), the dedicated NVMe mount used for the audit buffer spool path lacked a dedicated disk utilization threshold metric. As a result, the volume filled without proactive warnings.
- **No storage failover mechanism:** When the spool disk ran out of physical space, the audit daemon threw a terminal exception and halted rather than dropping buffered payloads to a secondary storage layer, such as an object storage bucket on aws.
- **Silent process failure:** Although the daemon threw an unhandled write exception in the logs, the parent process manager did not automatically reboot or restart the thread, relying solely on the metric gap alert to notify human operators.

---

## 7. Where We Got Lucky

- **Steady, predictable daytime traffic:** The outage occurred during an afternoon plateau rather than during our morning rush (07:00–09:00 JST) or evening peak (18:00–23:00 JST). If write volume had been three times higher, reconstructing the omitted request sequences from the log stream would have taken significantly longer.
- **Request log completeness:** No request log drops occurred on the central logging forwarders during the 2-hour window. Had the log collection pipeline experienced indexing backpressure at the same time, complete recovery of the 18,320 entries would have been impossible without querying read replicas for state differentials.

---

## 8. Root Cause Analysis

The root cause was an unmonitored disk filling on an auxiliary mount point combined with a brittle file-handling dependency. 

In `api`, audit logging runs asynchronously to preserve low API latency. The audit worker writes batches to `/var/spool/sorrel/audit` before ingestion into the primary database. On the night of 2025-12-10, an auxiliary cron job designed to export log summaries for metrics analysis generated file locks across several completed batch files. When the local log pruning utility ran at 13:40 JST on 2025-12-11, it could not unlink the locked files. 

Because disk space metrics for `api` only tracked the host root filesystem (`/`), the growth on `/var/spool/sorrel/audit` went undetected. Once the spool reached maximum physical capacity at 14:10 JST, the next batch write resulted in an unhandled `ENOSPC` POSIX error. The background thread crashed, and the application stopped spooling events. Because the API connection pool, request routers, and primary database connections were healthy, `api` continued serving requests, leaving the audit system completely non-operational until manually restarted.

---

## 9. Reconstruction and Recovery

Following the restoration of the live audit logging daemon at 16:15 JST on 2025-12-11, Daniel initiated the recovery process to resolve the 2-hour, 5-minute data gap.

### Recovery Strategy
1. **Extraction:** A parser script was written to query `sorrel-prod-*` for all mutating operations handled by `api` between 14:10:00 JST and 16:15:00 JST on 2025-12-11 (`method IN [POST, PUT, PATCH, DELETE]`).
2. **Reconstruction:** For each matched entry, the parser extracted the authenticated actor ID, business ID, targeted endpoint (e.g., `/v1/bookings`, `/v1/accounts/schedules`), request payload parameters, and server timestamp.
3. **Validation:** The generated audit payloads were compared against state changes recorded in the primary database during that timeframe to verify sequential accuracy and ensure no duplicate events were created.
4. **Backfill:** On 2025-12-13 at 11:30 JST, the reconstructed records were ingested into the primary audit store in batches of 500 entries.

A total of 18,320 audit log records were successfully restored, completely reconciling the gap.

```
+-------------------------------------------------------+
| Reconstructed Audit Entries Breakdown (Total: 18,320) |
+-------------------------------------------------------+
| Appointment Bookings Created / Confirmed :     11,412 |
| Cancellations & Reschedule Events        :      3,894 |
| Business Opening Hours / Schedule Edits  :      2,110 |
| Account Details & Staff Settings Changes :        904 |
+-------------------------------------------------------+
```

---

## 10. Action Items

| Action Item | Type | Owner | Target Date |
|---|---|---|---|
| Configure a proactive disk usage alert on all `api` spool volumes that fires when disk usage exceeds 75%. | Preventative | Sara (platform) | 2025-12-22 |
| Re-architect the audit spooler to automatically offload batches to aws object storage whenever local disk utilization passes 70%. | Architectural | Daniel (api) | 2026-01-15 |
| Update the background audit worker error handling to catch `ENOSPC` and filesystem write exceptions, automatically attempting recovery rather than terminating the worker thread. | Hardening | Ravi (api) | 2026-01-20 |
| Review the auxiliary log-exporting cron tasks to ensure file locks are released cleanly after execution. | Preventative | Kenji Sato (platform lead) | 2025-12-19 |
| Create an automated replay tool to reconstruct audit events from request logs in case of future auxiliary ingestion stalls. | Tooling | Daniel (api) | 2026-02-05 |

---

*This postmortem was reviewed and approved by Ravi (api owner) and Kenji Sato (platform lead) on 2025-12-15.*
