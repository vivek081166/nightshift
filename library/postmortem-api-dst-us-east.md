# Postmortem: bookings an hour off after the US clock change

Date: 2024-11-05  
Owner: Ravi (api)  
Participants: Ravi (api owner), Daniel (api engineer), Sara (platform engineer), Kenji Sato (platform lead), Hana (support lead), Aiko (web owner)

---

## 1. Summary

On Sunday, 2024-11-03, daylight saving time ended in the United States at 02:00 local time (16:00 JST). Following the transition, businesses operating in the `us-east` region noticed that upcoming customer appointments were rendered one hour earlier than scheduled when viewed inside their management interface.

A total of 1,407 bookings across businesses configured with US time zones were displayed incorrectly in the business dashboard. The underlying appointment timestamps persisted in the database remained completely accurate in UTC; the defect was strictly confined to presentation-layer time conversion handled by `api` when formatting response payloads for `web`. The issue was traced to an outdated operating system time zone data package (`tzdata`) baked into the base container image on a subset of active `api` worker nodes in `us-east`. 

The underlying records required no manual adjustments or data migrations. The incident was resolved on 2024-11-04 by updating the system time zone package across base images, rebuilding, and deploying the corrected build.

---

## 2. Impact

- **Customer impact**: 1,407 bookings across 86 small businesses in the `us-east` region displayed slot times shifted by minus 60 minutes inside the calendar views of the business dashboard. Customers browsing public booking pages experienced occasional slot alignment mismatches depending on which `api` node served the availability inquiry. No bookings were dropped or double-booked.
- **Data integrity**: Zero data corruption. Inspection of database rows confirmed all appointment records retained valid UTC timestamps alongside original business time zone identifiers.
- **Financial impact**: None. Charges and checkout authorization through `payments` processed correctly. No erroneous refunds or fees occurred.
- **Support volume**: 34 customer support tickets opened by salon and clinic owners between 22:30 JST on 2024-11-03 and 10:00 JST on 2024-11-04 reporting shifted calendars.
- **Severity classification**: P2. Core booking workflows remained operational, but schedule visibility was degraded for a regional subset of business accounts.

---

## 3. Background and Architecture Context

Sorrel operates four services: `web`, `api`, `payments`, and `notifier`. All booking logic, calendar schedules, and slot availability computations live inside `api`. As detailed in section 7.14 and section 13.1 of our operations handbook, Sorrel infrastructure operates primarily in `ap-northeast` (Tokyo, JST), which does not observe daylight saving time. However, our clusters in `us-east` and `eu-west` serve merchants operating under local regional time changes.

Every appointment record created in `api` stores its start and end times in UTC, coupled with the business’s canonical IANA time zone string (for example, `America/New_York` or `America/Chicago`). When `web` requests schedule slots or dashboard calendar feeds, `api` translates UTC timestamps to the business’s configured local zone before serializing the JSON response.

In `us-east`, `api` runs eight worker nodes behind a regional load balancer, scaling out dynamically up to twenty under load. Node images are built from a base container definition maintained by the platform team. During October 2024, an image cache divergence occurred: an image rebuild for a routine dependency bump inherited an older base package mirror where local OS zone definitions contained obsolete transition rules for select US jurisdictions.

---

## 4. Timeline (all times in JST)

### 2024-11-03

- **16:00**: Daylight saving time ends in the United States (02:00 EDT shifts to 01:00 EST).
- **22:14**: Hana flags an initial ticket from a physiotherapist in New York stating their Monday morning calendar shows bookings arriving at 08:00 instead of 09:00.
- **22:45**: Two additional support tickets arrive via the business portal with identical symptoms across two separate hair salons in `us-east`.
- **23:10**: Hana posts in `#inc-live` noting an emerging pattern of US businesses reporting schedule offsets by exactly one hour.

### 2024-11-04

- **08:30**: As US business owners log in ahead of their Monday work week, incoming support tickets rise to 18. Hana updates the thread in `#inc-live`.
- **09:05**: Ravi acknowledges the thread, opens dashboard "Sorrel / api", and initiates investigation into the booking endpoint handlers.
- **09:20**: Ravi reviews `service=api` logs and inspects raw database rows for the reported business accounts. UTC timestamps in the booking table match the customer booking confirmation records exactly.
- **09:42**: Daniel joins the thread. Daniel reproduces the issue locally against production-like payloads: querying `/v1/business/calendar` against a mock `America/New_York` schedule yields offsets only when executed within one specific container image layer.
- **10:15**: Inspection of node inventory reveals that three of the eight running `api` nodes in `us-east` were running an image built from an unpinned base snapshot that carried an outdated version of the system time zone library (`tzdata 2022g`). The remaining nodes were on a build carrying updated package tables.
- **10:45**: Daniel and Sara draft an emergency package update ensuring all container base definitions explicitly pull current `tzdata` packages and pin upstream dependencies.
- **11:30**: Sara verifies the rebuilt container image across staging clusters in `us-east`. Verification queries confirm local time formatting matches wall-clock EST accurately.
- **13:00**: Aiko checks "Sorrel / web" rendering pipelines to ensure web front-ends perform no secondary time conversions on server-side renders; web relies entirely on the strings emitted by `api`.
- **14:15**: Deploy `d-3841` for `api` is reviewed by Ravi and kicked off through the deploy tool during normal working hours, replacing nodes two at a time across `us-east`.
- **14:26**: Deploy `d-3841` finishes across all eight nodes in `us-east`.
- **14:40**: Hana spot-checks the schedules of all 34 businesses that submitted support tickets. All reported calendar views reflect correct scheduled hours.
- **15:00**: Incident stood down. Hana responds to affected merchants confirming calendar alignment is restored.

---

## 5. What Went Well

- **Immutability of UTC data storage**: Because the application strictly stores all schedule records in UTC alongside raw time zone strings, no underlying customer data was modified, corrupted, or lost. We did not have to run database repair scripts, restore snapshots, or untangle conflicting booking slots.
- **Zero payment impact**: The checkout and refund mechanisms operated via `payments` rely exclusively on UTC slot reservations, ensuring zero billing errors occurred.
- **Support-to-engineering handoff**: Support spotted the pattern at 34 tickets and isolated the common denominator (businesses located in US states undergoing DST changeover) before broad customer confusion spread.
- **Fast verification**: Having clean endpoints and log tooling allowed Daniel to reproduce the bug within 25 minutes of beginning active debugging.

---

## 6. What Went Badly

- **Base image inconsistency**: Production nodes inside the same region were executing different versions of basic operating system utility packages. This made reproduction intermittent initially, as requests routed to five of the eight nodes produced correct output, while requests routed to the other three produced the one-hour offset.
- **Passive detection**: The issue was discovered through customer support inquiries rather than synthetic monitoring. We had no test assertions or synthetic monitors that explicitly verified daylight saving boundary transitions across our operational regions.
- **Knowledge gap around transition dates**: Because the core engineering team is based in Tokyo where daylight saving time is not observed, the team lacked ambient awareness of the impending North American clock change.

---

## 7. Where We Got Lucky

- **Quiet booking window**: The clock shift occurred on a Sunday afternoon JST (early Sunday morning US time), allowing a window before Monday morning peak business operations began in the United States.
- **No data writebacks from the web dashboard**: When business owners loaded their shifted calendars, the dashboard did not emit automatic update hooks or save changes back to the database upon rendering. Had the web interface auto-synced the displayed time back to the API, 1,407 bookings could have had their UTC records corrupted.

---

## 8. Root Cause Analysis

The root cause was a stale system `tzdata` package on a subset of deployed container instances running the `api` service.

Sorrel’s `api` service relies on the underlying runtime environment's system zone files to perform localization:

$$\text{Local Time} = \text{UTC Time} + \text{Offset}(\text{tzdata}, \text{Timestamp})$$

When an older `tzdata` package is present, changes or rule transitions for given jurisdictions fall back to stale daylight saving boundary tables. In this instance, base container builds generated prior to an upstream patch used historical changeover dates.

Furthermore, our container build pipeline allowed layer cache hits on the base operating system packages unless explicitly invalidated. When regular application deploys were rolled out in mid-October, newly scaled instances picked up base layers that had not refreshed package repositories. Consequently, requests balanced across nodes in `us-east` hit mixed environments:

| Node Identifier | Image Tag | `tzdata` Version | Behavior on 2024-11-03 |
|---|---|---|---|
| `api-useast-01` | `d-3810` | 2024a | Handled EST transition correctly |
| `api-useast-02` | `d-3810` | 2024a | Handled EST transition correctly |
| `api-useast-03` | `d-3798` | 2022g | Remained on EDT (+1 hour error) |
| `api-useast-04` | `d-3810` | 2024a | Handled EST transition correctly |
| `api-useast-05` | `d-3798` | 2022g | Remained on EDT (+1 hour error) |
| `api-useast-06` | `d-3810` | 2024a | Handled EST transition correctly |
| `api-useast-07` | `d-3798` | 2022g | Remained on EDT (+1 hour error) |
| `api-useast-08` | `d-3810` | 2024a | Handled EST transition correctly |

Because `api` instances run behind a round-robin load balancer, merchants refreshing their calendars would occasionally see appointments jump between the correct time and the one-hour shifted time, which contributed to confusion.

---

## 9. Action Items

| Item | Description | Type | Owner | Due Date |
|---|---|---|---|---|
| AI-1 | Add recurring calendar reminders for the platform team two weeks before every March and November clock change (covering US and European DST dates). | Preventative | Kenji Sato (platform lead) | 2024-11-12 |
| AI-2 | Add a synthetic CI test suite validating `api` time conversions across historical and upcoming DST boundary dates for all supported partner time zones. | Detection | Daniel (api) | 2024-11-19 |
| AI-3 | Update base container Dockerfiles across all services (`web`, `api`, `payments`, `notifier`) to ensure explicit package cache invalidation and pinned `tzdata` updates on build. | Preventative | Sara (platform) | 2024-11-26 |
| AI-4 | Audit `notifier` template rendering engines to ensure email and SMS reminders pull localized timestamps using identical timezone libraries as `api`. | Hardening | Tom (notifier) | 2024-12-03 |
| AI-5 | Prepare support macro templates in the support desk tool explaining daylight saving calendar cache refreshes for business accounts. | Mitigation | Hana (support) | 2024-11-15 |

---

## 10. Operational Lessons

Section 7.14 of the on-call handbook notes that daylight saving anomalies surface cyclically around spring and autumn transitions in `us-east` and `eu-west`. 

Because our core operations and primary engineering hub are anchored in Tokyo (`ap-northeast-1`), engineering intuition does not naturally anticipate wall-clock shifts taking place in overseas operational regions. Relying on manual awareness is insufficient. Instituting a strict operational process—specifically recurring calendar reminders two weeks prior to the March and November transitions—ensures the platform team audits base dependencies, verifies system time tables, and validates node uniformity well before customer schedules can be affected.
