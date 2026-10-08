# How to check replica lag on api

Last updated: 2026-01-26  
Owner: Daniel (api)

This page describes how the engineering and platform teams inspect database replication lag for the `api` service across all active regions, what numbers are considered normal during regular operations, how lag manifests to users and dependent services, and what to do when numbers wander outside expected bounds.

---

## 1. Context and Architecture

The `api` service is the central core of Sorrel. It maintains all records of businesses, services, opening hours, customers, bookings, audit records, and slot availability logic. Every request served by `web` or partner integrations depends on timely reads and writes handled by `api`.

To sustain read throughput across our operational footprint, `api` uses regional database instances hosted on our cloud infrastructure (aws). The service operates in three active regions:

- `ap-northeast` (Tokyo, our largest region by volume)
- `us-east`
- `eu-west`

In each active region, the database layer consists of:
- One primary database handling all write traffic, state mutations, and transactional booking locks.
- Two read replicas per region asynchronously streaming write-ahead replication streams from the regional primary.
- A dedicated connection pool configured on each `api` node (which autoscale between eight and twenty nodes per region).

```
                      +-------------------+
                      |   api Nodes       |
                      |   (8-20 per reg)  |
                      +---------+---------+
                                |
             +------------------+------------------+
             | Writes                              | Reads
             v                                     v
   +-------------------+                 +-------------------+
   | Regional Primary  +=== (stream) ===>| Read Replica 1    |
   | Database          |                 +-------------------+
   +---------+---------+                 | Read Replica 2    |
             |                           +-------------------+
             +======== (stream) ========> (Lag tracked here)
```

Read traffic for queries such as availability browsing, search indexing, schedule inspection, and partner read calls is offloaded to the regional replicas whenever strict transactional read-your-own-writes guarantees are not explicitly demanded.

When replication delays accumulate between the primary database and its read replicas, data served from read replicas falls behind current state. This document details how to verify that lag and determine next steps.

---

## 2. Where to Check Replica Lag

Replica lag metrics are gathered continuously from database runtime statistics and published to our centralized metrics tooling.

### Dashboard Location

1. Navigate to the metrics tool.
2. Open the folder **Sorrel / Services**.
3. Select the dashboard **Sorrel / api**.
4. Scroll down to the **Database** row.

### Panel Details

Replica lag is on the 'Database' row of the api board, one line per region.

The panel visualizes the replication offset in seconds over time:
- The graph plots three distinct series corresponding to our active deployment regions: `ap-northeast`, `us-east`, and `eu-west`.
- Each regional series aggregates the maximum replication delay observed across that region's two read replicas.
- The default time range displays the last 6 hours, but you should adjust the window to match the specific period of interest or incident window when investigating symptoms.

#### Related panels on the same row

While viewing the replica lag panel on the Database row, keep an eye on the adjacent panels to provide operational context:
- **Connections in use per pool**: Tracks pool utilization against saturation thresholds per node.
- **Query time**: Displays query duration percentiles across primary and replica endpoints.
- **Slow queries**: Reports occurrences of statements taking longer than baseline expectations, often the root cause of saturated replication threads.

---

## 3. Thresholds and Operational Standards

Replication across our local database setups is typically near-instantaneous. However, large write batches, bulk calendar updates, or resource contention can occasionally induce temporary delays.

| Replica Lag Metric | Operational Assessment | Expected Action |
|---|---|---|
| **< 1.0 second** | **Normal** | Baseline condition. No intervention or logging required. |
| **1.0s – 10.0 seconds** | **Elevated** | Often transient during peak calendar batch updates (e.g., Monday 09:00–12:00 JST) or large data imports. Monitor trend. |
| **> 10.0 seconds for > 3–5 minutes** | **Abnormal** | Not normal behavior. Investigate immediately via logs and query performance metrics. |
| **Steadily climbing without plateaus** | **Critical Contention** | Indicates replication worker blockage, storage starvation, or upstream lock contention. |

Normal lag is under 1 second; over 10 seconds for more than a few minutes is worth reading logs about.

A transient spike that recovers within sixty seconds is usually tied to a bulk booking write operation, a batch update from a business dashboard opening at 09:00 JST, or an audit flush. However, when replica lag stays above 10 seconds across consecutive metric scrapes, replication threads are falling behind incoming changes, and stale data will be served to customers.

---

## 4. How Replica Lag Appears (Alerting and Symptoms)

A key operational reality for the `api` service: **Replica lag does not page on its own; it shows up as stale reads.**

There is no dedicated paging rule that triggers a pager solely because replica lag crossed 5 or 10 seconds. Instead, high replication lag generates secondary symptoms across the product, leading to user-visible confusion or downstream alerts:

### Symptoms seen by customers and businesses

1. **Ghost Availability**: A customer selects an appointment slot that another user booked seconds earlier, proceeding to checkout only to have `payments` or the primary write transaction fail with an availability conflict.
2. **Missing Calendar Changes**: A salon or clinic owner edits their opening hours or adds a block on their dashboard, refreshes their view, and sees their old schedule because the browser read was serviced by a lagged replica.
3. **Search Desynchronization**: The "find a slot near me" search index or regional query endpoints return listings that were recently altered or disabled, driving an increase in 4xx validation rejections or user confusion.
4. **Partner Inconsistencies**: External scheduling widgets or calendar sync tools query the partner API, receive outdated state, and attempt conflicting slot reservations.

### Downstream dashboards and alerts affected

When replica lag is sustained, you will often see correlations on other boards:
- **Sorrel / api**: Elevated p95 or p99 latency on the search endpoint group or partner endpoints; query time spikes on the database panel.
- **Sorrel / web**: Customer reports forwarded through support (handled by Hana's team) claiming calendar edits "reverted themselves" or slots were unavailable upon selection.
- **Sorrel / payments**: Checkout validation errors or transient booking reconciliation mismatches where payments completed but the slot verification took longer to sync.

---

## 5. Investigation Workflow

When you suspect or observe replication lag on the `Sorrel / api` dashboard exceeding 10 seconds, follow this step-by-step diagnostic workflow.

```
+-----------------------------------------------------------+
| 1. Check "Sorrel / api" -> Database row                   |
|    - Is lag > 10s for several minutes?                    |
|    - Which region is affected? (ap-northeast, us-east, eu)|
+-----------------------------+-----------------------------+
                              |
                              v
+-----------------------------------------------------------+
| 2. Isolate Scope & Concurrent Symptoms                    |
|    - Check Database Slow Queries & Pool Usage             |
|    - Check Deploy History (Was there a recent deploy?)    |
|    - Check aws health status if isolated to one region    |
+-----------------------------+-----------------------------+
                              |
                              v
+-----------------------------------------------------------+
| 3. Read Service Logs (index: sorrel-prod-*)               |
|    - Query service=api for lock contention, timeouts      |
|    - Check for replication or connection pool exhaustion  |
+-----------------------------+-----------------------------+
                              |
                              v
+-----------------------------------------------------------+
| 4. Assess Impact & Escalate if Necessary                  |
|    - If hardware failure / split-brain / promotion needed: |
|      Page Ravi (api owner).                               |
|    - Do NOT attempt replica promotion alone.              |
+-----------------------------------------------------------+
```

### Step 1: Confirm timing, duration, and region

Open the **Sorrel / api** board and check the **Database** row.
- Identify the exact region affected. Is it restricted to `ap-northeast`, or present globally?
  - If confined to one region, check if regional query latency is also spiked.
  - Check the provider status (health.aws.amazon.com or the account personal health dashboard) for AWS storage (EBS) or database performance degradation in that region (e.g., `ap-northeast-1`).
- Establish the timeline: When did the line deviate from the < 1.0s floor? Did it coincide with the top of the hour, a batch run, or a deploy?

### Step 2: Compare against recent deployments

Cross-reference the onset time with the deploy history in the deploy tool.
- Was a release recently deployed?
- While a bad deploy may cause pool exhaustion or slow queries, remember that deploys several hours or days old are rarely the spontaneous cause of sudden replication lag.
- Check if database migrations were applied during the last release that could be holding long table locks or performing heavy sequential scans.

### Step 3: Read logs in the log search tool

Go to the log search tool, targeting the index `sorrel-prod-*`. Limit your query window strictly to the few minutes preceding the rise in lag.

Run the standard diagnostic filters:

```text
service=api level=ERROR
```

Look for the earliest errors rather than the highest volume. Specifically scan for:

```text
service=api msg="pool exhausted"
service=api duration_ms>2000 endpoint=*
service=api msg="deadlock"
service=api msg="timeout"
```

Look for statements that indicate heavy write locks on tables like `bookings`, `slots`, or `business_hours`. A long-running transactional write on the primary database prevents the replication process from applying subsequent changes concurrently, causing replica lag to accumulate rapidly on both read replicas in that region.

### Step 4: Inspect connection pools and slow queries

Examine the **Connections in use per pool** panel on the Database row:
- Are connection pools nearing 90% or 100% capacity?
- When slow queries run on replicas, replica connection pools fill up. Once full, incoming read requests block, queue, and eventually time out, increasing 5xx errors on `api` and generating 5xx errors upstream on `web`.
- If connection pools are exhausted across multiple nodes, check if specific endpoints (such as `/search` or partner sync calls) are dominating the pool.

---

## 6. What You Can and Cannot Do

When diagnosing database replication lag during an on-call shift, clear boundaries govern operational interventions:

### What the On-Call Engineer Can Do

- **Inspect dashboards**: Read the Database row on `Sorrel / api`, check query durations, pool metrics, and error rates.
- **Read logs**: Search `service=api` logs for deadlocks, slow queries, slow transactions, and pool exhaustion events.
- **Correlate with dependencies**: Check AWS health dashboards if the issue is strictly isolated to one region (e.g., storage degradation in `ap-northeast-1`).
- **Engage support communication**: If customer inquiries mount regarding stale booking displays or calendar updates reverting, coordinate with support lead Hana so support staff have visibility into the fact that read lag is occurring.
- **Log the findings**: Post notes and dashboard snapshots in `#inc-live` detailing the observed lag, region, and initial log analysis.

### What the On-Call Engineer CANNOT Do

- **Promoting a replica is a decision for Ravi, never an on-call move.**
- You must never attempt to execute a database failover, promote a read replica to primary, detach replication streams, or rebuild a replica instance by hand during an incident.
- You must not alter connection pool limits, change database configurations, or kill long-running database processes on production clusters without owner approval.
- You must not modify partner rate limits or change regional routing alone.

### Why Promoting a Replica Is Strictly Reserved for Ravi

Read replicas by definition run behind the primary. Promoting a replica while lag exists guarantees immediate **data loss** or **silent data divergence**:
- Transactions committed on the primary that have not replicated will be orphaned or overwritten.
- Two databases could momentarily accept writes (split-brain), producing conflicting booking records, corrupted slot assignments, and audit trail gaps.
- Correcting split-brain data states requires forensic database restoration from point-in-time backups.
- Only the service owner (Ravi) has the authority to assess transactional loss trade-offs and make failover or promotion decisions.

---

## 7. Escalation Guidelines

If replica lag is severe, persistent, and causing customer-visible harm, escalate according to our handbook policies.

### When to Page Ravi

Page Ravi (api owner) using the paging tool under the following conditions:
1. **Irreversible harm / data state corruption**: If there is evidence that inconsistent reads have allowed double-bookings where money was collected twice, or data corruption has occurred across tenants.
2. **Persistent severe lag with connection saturation**: Replica lag in any region exceeds 10 seconds for more than 15 minutes continuously, connection pools are exhausted, and read queries are timing out at scale across nodes.
3. **Primary hardware failure**: The primary database in a region has crashed or stopped accepting writes, the read replicas are stalled, and a failover or promotion decision must be evaluated.
4. **Unresolvable deadlocks**: Widespread write locking has halted the replication stream and normal query timeouts are not clearing the queue.

### How to Page

1. Open the paging tool and page the schedule for **Ravi** (owner of `api`).
2. Include the alert or symptom details, the affected region, the observed replica lag value, and what you have verified in the logs.
3. If Ravi does not acknowledge within 10 minutes, the paging tool will automatically escalate to the incident commander rotation.

---

## 8. Summary Checklist for On-Call

When investigating an alert or incident involving `api` where stale reads or slow performance are suspected, keep this quick reference in mind:

- [ ] Go to **Sorrel / api** dashboard -> **Database** row.
- [ ] Inspect the **Replica lag** panel: verify if lag is under 1 second (normal) or exceeding 10 seconds.
- [ ] Determine if the issue is global or limited to a single region (`ap-northeast`, `us-east`, or `eu-west`).
- [ ] Check adjacent panels: **Connections in use per pool**, **Query time**, and **Slow queries**.
- [ ] If single-region, inspect the cloud provider health status (AWS Personal Health Dashboard) for storage or networking incidents.
- [ ] Search logs in `sorrel-prod-*` for `service=api` focusing on `pool exhausted`, `deadlock`, and slow queries.
- [ ] Document observed lag values and log findings in `#inc-live`.
- [ ] Remember: **Replica promotion is never an on-call action; page Ravi if a failover or manual promotion decision is required.**
