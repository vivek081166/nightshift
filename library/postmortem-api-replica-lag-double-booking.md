# Postmortem: api replica lag double-booked slots in eu-west

Date: 2026-06-09  
Owner: Ravi (api)  
Incident Commander: Kenji Sato  
Participants: Ravi (api owner), Daniel (api engineer), Sara (platform engineer), Hana (support lead), Noor (on-call primary)

---

## 1. Summary

On Monday, 2026-06-08, during the morning write burst in the European region, database read replica lag in `eu-west` climbed to 41 seconds. During this window, `api` checked slot availability against the read replica rather than the primary database before committing new reservations. Because the replica lagged significantly behind the primary, 63 appointment slots that had just been reserved by one customer appeared open to subsequent requests. Consequently, 63 slots were booked twice across multiple small business calendars in `eu-west`.

The on-call engineer paged Ravi because resolving double bookings and determining reconciliation actions required customer contact and data-level decisions that on-call engineers are not permitted to make. The immediate incident mitigation involved deploying a flag change (`booking_reads_primary`) to force the final pre-commit availability validation query directly to the regional primary database. The flag is now enabled across all production regions (`ap-northeast`, `us-east`, and `eu-west`). Over the following 24 hours, Hana's support team contacted all 63 affected customers to reschedule or offer appropriate remedies.

---

## 2. Impact

- **Severity:** P1 (Money and customer scheduling records corrupted; two customers booked for the same physical resource/time).
- **Customers affected:** 63 customer accounts experienced a double-booked appointment across 41 businesses in `eu-west`.
- **Financial impact:** No errant card charges were made outside normal transaction flows, but deposits for the duplicate bookings required manual reconciliation, rescheduling, or refund decisions handled by support.
- **Data integrity:** 63 conflicting rows in the `bookings` table in `eu-west`. No cross-tenant data leaks occurred; no secrets were exposed.
- **Service availability:** The `api` service remained online and serving traffic, but slot reservation integrity was degraded between 16:14 JST and 16:48 JST.

---

## 3. Timeline (all times JST)

| Time | Who | Event |
|---|---|---|
| **16:00** | — | Monday morning write volume in `eu-west` peaks as salon and wellness businesses open calendars and sync weekly schedules (08:00 local time). |
| **16:12** | — | A heavy batch of calendar updates and external schedule imports from partner booking widgets begins writing to the `eu-west` primary database. |
| **16:14** | — | Replica lag on `eu-west-db-replica-1` exceeds 15 seconds. |
| **16:18** | Noor | Alert fires: `api-latency` p95 exceeding threshold on booking endpoints in `eu-west`. Replica lag on `Sorrel / api` dashboard shows 28 seconds and climbing. |
| **16:21** | Noor | Opens incident thread in `#inc-live`. Replica lag reaches 41 seconds on the database panel. |
| **16:24** | Hana | Support receives the first three customer reports from the UK indicating that booking confirmation emails from `notifier` were received for appointment times that salon owners claim were already occupied. |
| **16:26** | Noor | Noor checks logs via `service=api region=eu-west` and notices concurrent reservations committing for identical `slot_id` targets. Recognizing that customer appointments have been committed twice and customer outreach will be necessary, Noor pages Ravi via the paging tool. |
| **16:31** | Ravi | Ravi acknowledges page, joins `#inc-live`, and reviews the database panel on `Sorrel / api`. Kenji Sato joins as incident commander. |
| **16:35** | Kenji Sato | Kenji Sato updates status.sorrel.app to "Investigating: We are investigating reports of problems with bookings. We will update this page within 30 minutes." |
| **16:38** | Ravi, Daniel | Ravi and Daniel identify that while slot reservation writes use row-level locking on the primary, the preliminary `check_slot_available()` query executed immediately prior to checkout finalization was pointing to the regional read replica pool to offload primary read load. With 41 seconds of lag, the replica returned `status = OPEN` for slots that had already been updated to `RESERVED` on the primary. |
| **16:42** | Ravi | Ravi notes the dormant feature flag `booking_reads_primary` exists in the code base, originally drafted during the database pooling review by Daniel. Ravi enables `booking_reads_primary` in `eu-west`. |
| **16:48** | Ravi | Validation checks confirm that slot queries in `eu-west` are now routed exclusively to the primary instance. Replica lag begins draining as write burst subsides. No further duplicate reservations are created. |
| **16:55** | Daniel | Daniel runs an audit query on `sorrel-prod-*` and database read tables to isolate all conflicting records created between 16:14 and 16:48 JST. Exactly 63 duplicate bookings are identified across 41 merchant accounts. |
| **17:05** | Ravi | Ravi prepares the candidate list of 63 conflicting booking records and hands it over to Hana in the support channel. |
| **17:15** | Kenji Sato | Status page updated to "Resolved: The problems with bookings between 16:14 and 16:48 JST have been resolved. We are sorry for the trouble." |
| **17:30** | Hana | Support team begins triage and phone/email outreach to affected customers and businesses. |
| **18:00** | Ravi | Ravi turns on `booking_reads_primary` across `ap-northeast` and `us-east` to prevent the same condition from occurring during peak write hours in other regions. |
| **2026-06-09 15:30** | Hana | Support completes outreach: all 63 affected customer parties have been contacted and their appointments either rescheduled with merchant consent or refunded. |

---

## 4. Root Cause Analysis

The booking reservation flow in `api` involves two distinct database phases during the checkout finalization step:

1. **Pre-check:** A validation call to ensure the business's slot has not been claimed, the customer account has no overlapping active reservations, and business hours match.
2. **Commit:** A transactional state update that sets the slot state from `AVAILABLE` to `BOOKED`, creates the booking record, appends an entry to the audit log, and notifies `payments`.

Historically, to preserve connection pool capacity and keep query latency low on the primary database, read queries were directed to the regional read replica pool by default. Under normal traffic conditions, replica lag across all regions (`ap-northeast`, `us-east`, `eu-west`) remains under 200 milliseconds. Under this sub-second lag, race conditions were statistically rare and usually caught by the row lock during the commit phase.

However, during Monday morning opening hours, business owners and partner integrations generate high volumes of write traffic (updating availability rules, adjusting calendars, synchronizing third-party schedules). At 16:14 JST (08:14 local time in London), a write burst saturated the replication applier process on the single primary read replica in `eu-west`. 

Lag climbed steadily, reaching a peak of 41 seconds:

```
[Replica Lag in eu-west-db-replica-1]
16:10 JST:  0.18s
16:12 JST:  4.20s
16:14 JST: 15.60s
16:18 JST: 28.10s
16:21 JST: 41.30s  <-- Peak lag
16:30 JST: 33.00s
16:48 JST:  1.10s
```

Because the pre-commit check (`check_slot_available()`) was reading from the replica, it evaluated slot availability against a database state up to 41 seconds in the past. 

Furthermore, the secondary commit logic relied on a soft optimistic lock check that compared an entity version timestamp rather than enforcing a strict unique constraint on the composite key `(business_id, slot_time, status)` at the database engine level. Because the entity version read from the replica was stale, the subsequent write operation committed without raising a deadlock or primary key collision.

As a result, 63 separate requests passed the availability validation and successfully committed new booking rows for slots that had already been committed by an earlier request.

---

## 5. What Went Well

- **Prompt identification and paging:** Noor followed handbook escalation guidelines strictly. Rather than attempting to guess or perform ad-hoc database manipulations, Noor recognized that money and scheduling records had moved incorrectly, which requires owner-level and support-level decisions. Ravi was paged within 8 minutes of the first alert.
- **Pre-existing feature flag:** Daniel had previously implemented the `booking_reads_primary` flag during a prior connection pool optimization review. Because this code path was already in the deployed release, Ravi was able to safely toggle the flag to direct read queries to the primary without needing a rapid hotfix deploy.
- **Status page adherence:** Kenji Sato took over incident commander responsibilities within 15 minutes of the P1 escalation and adhered to the handbook's communication protocols, updating status.sorrel.app within the prescribed 20-minute window.
- **Cross-team handoff:** The list of affected `booking_id` records was compiled cleanly using database audit logs without pasting masked customer PII into public channels. Hana's support team took ownership of the customer resolution process immediately.

---

## 6. What Went Badly

- **Silent optimistic concurrency failure:** The database schema did not enforce a hard uniqueness constraint on active slot bookings. Relying on application-level read checks enabled stale reads from lagging replicas to commit invalid business states.
- **Alerting threshold on replica lag:** While `api-latency` alerted on booking endpoint delays, there was no high-priority dedicated alert for database replica lag exceeding 10 seconds. The on-call engineer had to identify the replica lag manually on the `Sorrel / api` dashboard panel.
- **Delayed customer impact awareness:** The on-call team was alerted by endpoint latency rather than a specific slot conflict metric; the actual realization that slots were being double-booked was only confirmed once support received initial inbound complaints.

---

## 7. Where We Got Lucky

- **Subsided write burst:** The spike in merchant updates in `eu-west` peaked and subsided within 35 minutes. Had the write burst continued at the same volume, replica lag could have grown larger, compounding the number of double bookings.
- **Flag availability:** Having `booking_reads_primary` already baked into the codebase avoided an emergency release during peak business hours.
- **Limited geographic scope:** The issue was confined to `eu-west`. `ap-northeast` was in its evening quiet period (around 16:00 JST), and `us-east` was still in early morning off-peak hours, preventing simultaneous global occurrences.

---

## 8. Remediation and Action Items

| Item | Description | Owner | Target Date | Status |
|---|---|---|---|---|
| **ACT-01** | Enable `booking_reads_primary` globally in `ap-northeast`, `us-east`, and `eu-west`. | Ravi | 2026-06-08 | **Done** |
| **ACT-02** | Add a database migration adding a unique constraint index on `(business_id, slot_timestamp)` where status is active (`status != 'CANCELLED'`) to reject conflicting commits at the database engine level. | Daniel | 2026-06-18 | Open |
| **ACT-03** | Implement a dedicated alert rule `api-replica-lag` that fires when read replica lag exceeds 10 seconds for more than 2 minutes in any active region. | Sara | 2026-06-15 | Open |
| **ACT-04** | Complete all support outreach and customer resolutions for the 63 double-booked bookings. | Hana | 2026-06-09 | **Done** |
| **ACT-05** | Evaluate primary database connection pool headroom in `eu-west` and `ap-northeast` to ensure routing final booking checks to the primary does not exhaust connection pools during lunchtime traffic spikes. | Ravi | 2026-06-22 | Open |
| **ACT-06** | Audit partner integration calendar sync jobs to add rate limiting on bulk write operations, smoothing out write peaks on Monday mornings. | Daniel | 2026-06-25 | Open |

---

## 9. Appendix: Technical Reference and Log Verification

### Log Pattern Observed During Incident
To verify the extent of the stale read window, the following log search was executed on `sorrel-prod-*` for the timeframe `2026-06-08 16:14:00` to `2026-06-08 16:50:00`:

```text
service=api region=eu-west msg="booking committed"
```

Cross-referencing the resulting records with conflicting `(business_id, slot_time)` showed duplicate booking creations starting at 16:16:02 JST and terminating at 16:47:49 JST.

```text
2026-06-08T16:16:02.104Z service=api region=eu-west slot_id=s-88219 booking_id=b-40112 outcome=success
2026-06-08T16:16:29.892Z service=api region=eu-west slot_id=s-88219 booking_id=b-40119 outcome=success
```

### Connection Pool and Query Metrics
Prior to enabling `booking_reads_primary`, connection pool utilization on `eu-west` primary database nodes hovered around 42 %. Following the activation of the flag across `eu-west` at 16:42 JST, pool utilization rose to 51 %, well below the 90 % threshold that triggers the `api-pool` alert. Latency on the primary database remained stable with p95 query times below 15 ms, confirming that routing final validation queries to the primary is sustainable across all regions.
