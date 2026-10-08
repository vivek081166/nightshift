# Postmortem: api rollback stuck in the deploy queue

Date of incident: 2026-08-20 (Thursday afternoon JST)
Severity: P1
Service: api
Author: Ravi. Reviewed at the Thursday postmortem review on 2026-08-27.
Status: closed. The main action item became the move of api and payments to Shipyard on 2026-09-28.

## Summary

api deploy d-5120 went out at 14:02 JST with a change to how bookings are validated. It rejected bookings for businesses whose opening hours cross midnight, which includes most bars, late-night salons and 24-hour clinics. The api 5xx rate reached 7.2 % within four minutes. The on-call engineer started a rollback at 14:09, but the old deploy tool runs one job at a time for the whole "sorrel" project, and a web deploy that had started at 14:05 was still running and then stalled on a slow CDN upload. The api rollback sat in the queue for 38 minutes. It finally ran at 14:47 and finished at 14:53. About 2,940 booking requests failed during the incident.

## Impact

- Customers: about 2,940 booking requests failed with errors between 14:03 and 14:53 JST, across all three regions. Support counted 61 customer reports, the most for a single incident this year.
- Businesses: 212 businesses with opening hours crossing midnight could not take bookings for 51 minutes.
- Money: none moved wrongly. Failed bookings were never charged.
- Data: none exposed or lost.
- Duration: 51 minutes from the deploy's first errors to recovery.

## Timeline (JST)

| Time | What happened | Who |
|---|---|---|
| 14:02 | api d-5120 starts going out. | Ravi's team (author: Daniel) |
| 14:03 | First booking errors in the logs: `opening hours invalid`. | |
| 14:05 | web deploy d-5121 starts in the deploy tool (unrelated front-end change). | Aiko's team |
| 14:06 | api-5xx alert fires: 5xx rate above 1 % for 3 minutes. | paging tool |
| 14:07 | Page acknowledged. | Sara (platform, on-call) |
| 14:09 | Sara presses "Roll back to this" for api, back to d-5117. The deploy tool shows the rollback as "queued". | Sara |
| 14:11 | api 5xx rate at 7.2 %. Incident declared P1. Kenji takes incident commander. | Kenji |
| 14:14 | The web deploy stalls uploading assets to object storage. It holds the project lock. | |
| 14:20 | Sara asks in `#deploys` who owns d-5121. Aiko's team is in a meeting. | Sara |
| 14:31 | Aiko answers and agrees to cancel d-5121. Cancelling takes effect only after the current asset upload step finishes. | Aiko |
| 14:47 | The upload step finishes, d-5121 is cancelled, and the api rollback starts. | |
| 14:53 | api rollback complete. 5xx rate back under 0.2 %. | Sara |
| 15:10 | Status page marked resolved. | Kenji |

## What went well

- The on-call engineer picked the right first move within three minutes of the page: the deploy was seven minutes old and every endpoint group was failing.
- The incident commander kept the status page updated every 15 minutes while we waited.

## What went badly

- A rollback for one service waited for a deploy of a different service. The old deploy tool has one lock for the whole project. Nobody on the rotation knew this, because a rollback had never waited more than a minute before.
- There was no way to jump the queue. "Cancel" on a running job only takes effect between steps, and the asset upload was one long step.
- The validation change had tests, but none used a business whose opening hours cross midnight.

## Where we got lucky

- It was a weekday afternoon in Japan, not the Monday morning peak.
- Payments was not affected: failed bookings never reached checkout.

## Detection and response

- Detection was fast. The api-5xx alert fired four minutes after the deploy started, and the on-call engineer acknowledged it within a minute.
- The diagnosis was fast too: every endpoint group was failing, the deploy was seven minutes old, and the first log lines named the new validation rule.
- Everything after 14:09 was waiting. The deploy tool showed the rollback as "queued" with no reason and no position in the queue. It took eleven minutes to find out that a web deploy held the project lock, and another eleven to reach someone who could cancel it.
- Support handled 61 reports with the status page text; no business was promised anything beyond "we are working on it".

## Root cause

Two causes. The deploy itself: a validation rule that assumed opening hours never cross midnight. The length of the incident: the deploy tool's single project-wide lock, which turned a six-minute rollback into a 44-minute wait plus six minutes of work.

## Action items

| Item | Owner | Due | Done |
|---|---|---|---|
| Move api and payments to a deploy pipeline with one lane per service (Shipyard). | Kenji (platform) | 2026-09-30 | 2026-09-28 |
| Until then, no deploys of web or notifier while an api or payments incident is open. | Kenji | 2026-08-21 | 2026-08-21 |
| Add test businesses with opening hours crossing midnight to the api test data. | Daniel | 2026-09-04 | 2026-09-02 |
| Add a "queued for more than 2 minutes" warning to rollbacks in the deploy tool for web and notifier. | Sara | 2026-09-18 | 2026-09-15 |

## Notes from the review

- The review asked whether on-call should have done something other than wait. Pressing rollback again would not have helped (it would have queued a second job), and forcing the lock risked leaving web half-deployed. Waiting and getting the web deploy cancelled was right with the tools we had.
- web and notifier stay on the old deploy tool for now. Their deploys are less often urgent to undo, and the queued-rollback warning covers the gap until they move.
