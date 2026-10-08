# Postmortem: payments checkout timeouts after the v2.31 pool change

Date of incident: 2025-11-18 (Tuesday, early morning JST)
Severity: SEV-2 at the time (P2 in today's handbook terms)
Service: payments
Author: Mei. Reviewed at the Thursday postmortem review on 2025-11-20.
Status: all action items closed.

## Summary

Payments release v2.31 went out at 02:14 JST. It cut the database connection pool on each payments node from 50 connections to 20, as part of a change meant to lower the load on the payments database during the weekly payout job. Under normal night traffic plus client retries, 20 connections were not enough. Checkouts waited for a free connection, the payments p95 latency climbed, and customers saw the checkout spinner keep turning. We rolled payments back to v2.30 and the service recovered at 03:07. 1,184 payments that had failed during the incident were replayed from the retry queue, and receipt emails for them went out by 03:20.

## Impact

- Customers: checkouts slow or failing between about 02:20 and 03:07 JST, mostly in us-east and eu-west where it was daytime or evening. Support counted 23 customer reports.
- Money: no customer was charged twice. 1,184 checkout attempts failed during the window and were replayed afterwards from the retry queue; all 1,184 completed.
- Data: none exposed or lost.
- Duration: 53 minutes from the first customer report to recovery.

## Timeline (JST)

| Time | What happened | Who |
|---|---|---|
| 02:14 | payments v2.31 deployed. The release cuts the database connection pool from 50 to 20. | Mei |
| 02:21 | First support ticket: the checkout spinner does not finish. | Hana (Support) |
| 02:30 | Alert fires: payments p95 above 2 s for 2 minutes. Page sent to on-call. | paging tool |
| 02:34 | Page acknowledged. | Ravi |
| 02:39 | payments logs show requests waiting for a database connection. | Ravi |
| 02:43 | Incident declared (SEV-2). Aiko takes incident commander. | Aiko |
| 02:47 | Mei joins and points at the pool size change in v2.31. | Mei |
| 02:50 | payments p95 peaks at 3.7 s. Client retries push the request rate up by about 80 %. | Ravi |
| 02:56 | Decision to roll back payments to v2.30. | Aiko |
| 02:58 | Rollback to v2.30 started. | Mei |
| 03:04 | Rollback complete on all payments nodes. | Mei |
| 03:07 | payments p95 back under 500 ms. Payments restored. | Ravi |
| 03:12 | 1,184 failed payments replayed from the retry queue. | Mei |
| 03:20 | Receipt emails for the replayed payments sent. | Tom |

## What went well

- The logs said "waiting for connection" in plain words, so the cause was found within five minutes of someone looking.
- Mei knew the release contents and joined quickly once paged by Aiko.
- The retry queue held every failed checkout, so nothing had to be reconstructed by hand.

## What went badly

- The release went out at 02:14, inside the night window when deploys are not allowed. The deploy tool did not enforce the window at the time; people were expected to remember.
- The alert threshold then was p95 above 2 s for 2 minutes. It fired 16 minutes after the deploy and 9 minutes after the first customer ticket.
- It took 22 minutes from acknowledging the page to deciding to roll back. Most of that was spent confirming that the provider was healthy, which the latency panel could have shown at a glance if ours and the provider's latency had been on the same panel.
- Client retries made it worse: each failed checkout came back up to three times, which is where the 80 % jump in request rate came from.

## Where we got lucky

- It was a Tuesday night in Japan. On a Friday evening in Japan, checkout volume is several times higher and the pool would have run out within a minute.
- The weekly payout job was not running. It shares the payments database.

## Root cause

The pool size was sized against the average number of connections in use, measured over a quiet afternoon. At night the average is lower, but bursts from us-east evening traffic and from client retries need far more connections for a few seconds at a time. With 20 connections per node, bursts queued, queued requests timed out, and timed-out requests were retried, which made the next burst bigger.

## Action items

| Item | Owner | Due | Done |
|---|---|---|---|
| Put our latency and the provider's latency on the same panel on "Sorrel / payments". | Mei | 2025-11-28 | 2025-11-26 |
| Make the deploy tool refuse deploys between 22:00 and 07:00 JST unless marked as a P1 fix. | Kenji (platform) | 2025-12-15 | 2025-12-09 |
| Load test any change to pool sizes against the Friday-evening traffic recording before it ships. | Mei | 2025-12-05 | 2025-12-04 |
| Move the payments latency alert to p95 above 3 s for 5 minutes, which fires on real customer pain and not on short bursts. | Ravi | 2025-12-05 | 2025-12-02 |
| Cap client checkout retries at two, with backoff. | Aiko | 2026-01-15 | 2026-01-13 |

## Notes from the review

- Someone asked whether the rollback should have happened earlier, at 02:39 when the logs pointed at connections. The review agreed that the release was 25 minutes old at that point and was the obvious first suspect; the 17 minutes spent on the provider were the cost of not having the combined latency panel, which is now fixed.
- The pool size for payments is back at 50. The change to reduce load during payouts was done a different way in v2.34: the payout job now uses its own small pool.
