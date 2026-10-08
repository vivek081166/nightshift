# Game days

Last updated: 2025-10-20  
Owner: Sara (platform)

This document describes how the platform team runs game days at Sorrel, how they interact with the on-call rotation, and what we learned from the drills conducted during 2025.

Game days are planned exercises where we introduce controlled failures into production or staging environments to test our systems, alerts, dashboards, and escalation practices. They exist to find gaps in our automation and runbooks before real incidents expose them.

---

## 1. Principles and Scheduling Rules

Every game day must be safe, predictable to internal teams, and clearly isolated from unexpected incidents. We follow four baseline operational rules:

1. **Advance notice on the calendar.** Game days are planned exercises; every one is on the game day calendar at least 48 hours ahead. An exercise cannot run without this entry. Engineering leads and on-call engineers consult this calendar at the start of their shifts as part of normal shift preparation.
2. **On-call synchronization.** Alerts during a game day still get acknowledged; the game day owner tells on-call which ones are expected. The on-call engineer remains responsible for triaging incoming alerts. If an alert fires that was not agreed upon as expected failure behavior, or if customer-facing impact exceeds pre-set thresholds, the drill is paused or halted immediately.
3. **Synthetic traffic labeling.** Synthetic traffic in a game day carries the `X-Sorrel-Loadtest` header. This header allows proxy filters, log search queries, and analytics pipelines to separate drill-generated volume from authentic customer traffic.
4. **Immediate halt authority.** Both the on-call primary and the game day owner hold full authority to abort any drill immediately without prior consensus.

---

## 2. Roles During a Drill

To prevent confusion between running the drill and monitoring production, responsibilities are split between the exercise leads and the active rotation.

| Role | Person / Group | Responsibilities |
|---|---|---|
| **Exercise Owner** | Sara or Kenji Sato | Plans the failure scenario, publishes the calendar invite 48 hours prior, injects the fault, monitors test boundaries, announces start/stop in chat. |
| **Service Owner** | Aiko (web), Ravi (api), Mei (payments), or Tom (notifier) | Reviews the test plan before approval, verifies backward compatibility and safety bounds for their service, assists in evaluating telemetry. |
| **On-Call Primary** | Active on-call engineer | Remains on shift. Watches dashboards, acknowledges alerts, verifies runbook steps, logs entries in `#inc-live` if required. |
| **Secondary / Shadow** | Scheduled secondary | Observes communication, watches adjacent services for unexpected cascading dependencies. |

---

## 3. Pre-Drill Checklist

Before injecting faults, the exercise owner and the on-call engineer complete the following checklist in the dedicated preparation channel:

- [ ] Exercise is listed on the game day calendar (minimum 48 hours prior).
- [ ] No active customer-impacting incidents (P1 or P2) are underway.
- [ ] No production deployments are scheduled in the deploy tool for the targeted service window.
- [ ] Provider status pages (health.aws.amazon.com, www.cloudflarestatus.com, status.stripe.com, status.twilio.com, status.sendgrid.com) confirm all external dependencies are operational.
- [ ] The game day owner posts the list of expected alert names to the incident channel so the on-call engineer can distinguish drill artifacts from unrelated bugs.
- [ ] Synthetic traffic scripts confirm that every request carries the `X-Sorrel-Loadtest` header.
- [ ] Abort criteria and rollback paths are defined and written down in the run plan.

---

## 4. On-Call Handling and Triage During Drills

A game day is an exercise in human response as much as system resilience. Therefore, alert automation is not silenced during drills.

### Alert Handling Rules
- When an alert fires during an exercise, the on-call engineer acknowledges the page within the standard severity response window (5 minutes for P1, 15 minutes for P2, 1 hour for P3).
- The game day owner tells on-call which ones are expected before injection starts. If an alert matches the expected list, the on-call engineer notes it in the exercise thread (e.g., "Acknowledged, expected per game day plan").
- If an alert fires that was **not** on the expected list, the on-call engineer treats it as an unverified symptom. The on-call engineer must quickly check if authentic customer traffic is experiencing errors, or if the fault has escaped its intended blast radius.
- If real customer traffic degrades (e.g., unexpected 5xx rates on unaffected routes, or payments checkout failures), the drill is called off immediately.

### Abandoned or Stray Traffic Checks
Handbook section 7.15 notes that uncoordinated synthetic load can occasionally be discovered by on-call engineers. If high request volume appears accompanied by the `X-Sorrel-Loadtest` header from our own address ranges outside an active calendar window:
1. Check the game day calendar to verify whether an unscheduled test was logged late.
2. If nobody claims ownership in chat, stop the test through the load test tool immediately.
3. Notify the platform team (Kenji Sato, Sara).

---

## 5. Review of 2025 Game Days

2025 game days were: 2025-03-12 notifier worker loss, 2025-06-18 api replica failover, 2025-10-15 web node loss.

The specific technical notes, execution timelines, telemetry observations, and outcomes of these three exercises are detailed below.

```
2025-03-12: notifier worker loss (Tom / Sara)
   ├── 14:00 JST: Drain 2 of 3 worker nodes in ap-northeast-1
   ├── 14:08 JST: Queue depth rises; delivery latency increases
   └── 14:24 JST: Nodes restored; queue fully drained by 14:38 JST

2025-06-18: api replica failover (Ravi / Sara)
   ├── 11:15 JST: Force read replica promotion in ap-northeast-1
   ├── 11:18 JST: Connection pool reset across api nodes
   └── 11:29 JST: Connection pools settle; read lag returns to 0 ms

2025-10-15: web node loss (Aiko / Sara)
   ├── 15:30 JST: Terminate 3 of 6 web nodes in ap-northeast-1
   ├── 15:33 JST: Autoscaling provisions replacement instances
   └── 15:46 JST: Node count returns to 6; p95 page load steady
```

---

### Drill 1: Notifier Worker Loss (2025-03-12)

- **Date:** 2025-03-12
- **Focus:** notifier queue drain rate and worker resilience
- **Service Owner:** Tom (notifier)
- **Exercise Lead:** Sara (platform)
- **Target Region:** ap-northeast-1

#### Objective
Evaluate how notifier handles an abrupt drop in processing capacity during normal daytime operating hours, verifying whether message queue backlogs drain predictably without message loss or duplicate sends.

#### Method
At 14:00 JST, two of the three notifier worker nodes in ap-northeast-1 were halted, leaving a single node to pull messages from the queue. Synthetic booking notices and reminder requests tagged with `X-Sorrel-Loadtest` were injected at a steady rate of 45 messages per minute.

#### Telemetry and Observations
The "Sorrel / notifier" dashboard showed queue depth climbing steadily from an initial baseline of 18 messages to 412 messages over an eight-minute window.

```
Time (JST)   Queue Depth   Delivered/min   Vendor Responses   Notes
13:58        18            42              200 OK             Baseline
14:00        22            14              200 OK             2 worker nodes stopped
14:06        210           15              200 OK             Queue depth rising
14:12        380           14              200 OK             Oldest message age: 4.8 min
14:24        412           48              200 OK             Workers restarted
14:38        24            44              200 OK             Backlog cleared
```

- **Alert behavior:** The `notifier-queue-depth` alert did not fire because queue depth did not cross the 1,000-message threshold. The `notifier-queue-stalled` alert did not fire because delivery was ongoing (delivered per minute stayed around 14 to 15 rather than dropping to zero).
- **Vendor interaction:** Calls to twilio and sendgrid remained clean with normal 2xx response codes. No quota rejections occurred.
- **Duplicate checks:** The duplicate detection panel showed zero duplicate message IDs across the test window.

#### Findings
1. Workers process one message completely before acknowledging and removing it from the queue; terminating instances mid-flight did not produce unacknowledged message deadlocks.
2. The oldest message age climbed to 5.2 minutes at peak backlog. For non-urgent email receipts, this delay is acceptable; however, if SMS sign-in codes had been in the same queue, users would have experienced five-minute delivery delays.
3. *Follow-up action:* Tom created a tracking item to evaluate splitting authentication one-time codes into an expedited queue path so background reminder batches cannot delay sign-ins.

---

### Drill 2: API Replica Failover (2025-06-18)

- **Date:** 2025-06-18
- **Focus:** api connection pool recovery under primary/replica database failover
- **Service Owner:** Ravi (api)
- **Exercise Lead:** Sara (platform)
- **Target Region:** ap-northeast-1

#### Objective
Verify that api nodes correctly shed stale connections, handle replica lag, and reconnect to promoted database instances without manual node restarts or connection pool exhaustion.

#### Method
At 11:15 JST, an automated failover of the read replica in ap-northeast-1 was executed via our infrastructure management layer. Read traffic was simulated using test runner scripts executing search and booking lookups with the `X-Sorrel-Loadtest` header.

#### Telemetry and Observations
On the "Sorrel / api" board:
- At 11:16 JST, database connections in use spiked briefly from 32 % to 88 % across the node fleet as queries in flight timed out against the demoted instance.
- Connection pools reached peak utilization at 11:18 JST, touching 89 % on two of the eight nodes in the region.
- The `api-pool` alert rule (which fires if the connection pool exceeds 90 % for 10 minutes) stayed silent because pool usage peaked under the threshold and dropped back to 36 % within 4 minutes.
- Slow query volume increased briefly on search index lookups (`duration_ms>2000`), generating 14 log entries with `timeout` before database connection pools dropped severed connections and reopened sockets against the healthy replica.

```
11:16:04 JST api-node-03 service=api msg="connection reset by peer" db=read-replica-01
11:16:05 JST api-node-03 service=api msg="pool reconnecting" db=read-replica-02
11:16:08 JST api-node-07 service=api msg="connection reset by peer" db=read-replica-01
11:17:12 JST api-node-07 service=api msg="pool healthy" active_conns=18
```

- Customer bookings completed successfully throughout the drill; write operations to the primary database were untouched.
- The audit log panel showed uninterrupted entry generation, averaging 280 entries written per minute.

#### Findings
1. The connection pool timeout on api nodes severed stale sockets within 8 seconds, safely below our 10-second request timeout threshold.
2. Replica lag on the promoted node synchronized to 0 ms within 90 seconds of failover.
3. Ravi and Daniel verified that partner API request rejection rates remained flat throughout the test window, with zero tenant filter exceptions (`msg="tenant check failed"`).

---

### Drill 3: Web Node Loss (2025-10-15)

- **Date:** 2025-10-15
- **Focus:** web load balancing, front-end rendering latency, and autoscaling response
- **Service Owner:** Aiko (web)
- **Exercise Lead:** Sara (platform)
- **Target Region:** ap-northeast-1

#### Objective
Confirm that the front-end tier tolerates an abrupt 50 % loss of node capacity without elevating edge 5xx rates, dropping static assets, or degrading browser render times beyond acceptable bounds.

#### Method
At 15:30 JST, three of the six web nodes behind the load balancer in ap-northeast-1 were forcefully terminated. Synthetic browser traffic carrying the `X-Sorrel-Loadtest` header was maintained against public booking pages and business calendar interfaces.

#### Telemetry and Observations
On the "Sorrel / web" board:
- The load balancer detected unhealthy targets within 12 seconds, pulling the three terminated nodes out of rotation cleanly.
- Request rate redistributed immediately across the three surviving nodes. CPU utilization on surviving nodes jumped from 24 % to 62 %, while memory usage remained stable at 48 %.
- p95 page load time rose from 410 ms to 890 ms on server renders, well below the 2.0-second alert threshold.
- The CDN panel showed no elevation in edge 4xx or 5xx responses; edge cache hit ratios remained constant at 94.2 %.
- Autoscaling triggered at 15:34 JST, provisioning three fresh instances. The new nodes completed asset cache warming and joined the rotation between 15:42 and 15:46 JST.
- Node health normalized at 15:48 JST, returning regional CPU utilization to 26 % across six nodes.

```
Time (JST)   Active Nodes   Surviving CPU   p95 Load Time   CDN 5xx   Notes
15:28        6              24 %            410 ms          0.00 %    Baseline
15:30        3              62 %            840 ms          0.01 %    3 nodes terminated
15:34        3              64 %            890 ms          0.00 %    Autoscale triggered
15:42        5              38 %            520 ms          0.00 %    2 new nodes joined
15:46        6              26 %            420 ms          0.00 %    Cluster restored
```

- **Alert behavior:** The `web-node-restart` alert did not fire because instances were terminated directly rather than restarting within their existing container runtime. The `web-5xx` and `web-page-load` alerts remained green throughout the drill.

#### Findings
1. Static asset delivery remained fully insulated from node churn because files were properly cached at the edge and served via object storage rather than local disk.
2. Admin tool endpoints and business calendar dashboards experienced zero 5xx spikes during the transition.
3. Aiko and Priya confirmed that session state held in the shared cache persisted cleanly across the failover, with no recorded user session drops.

---

## 6. Planning and Running a Game Day

Engineers planning future exercises must use the following standard lifecycle:

```
[48h Before]        [24h Before]         [Day of Drill]        [Post-Drill]
Add to Calendar  -> Team Review      ->  Verify Health      -> Publish Notes
Set Scenarios       Agree on Alerts      Inject Fault          Update Runbooks
Define Headers      Check Deployments    Monitor on-call       File Action Items
```

### 1. Planning Phase (Minimum 48 Hours Prior)
- Define the hypothesis: describe the exact failure mode to simulate and the expected behavior of the system.
- Select an active region (ap-northeast-1, us-east-1, or eu-west-1).
- Add the event to the game day calendar at least 48 hours in advance. Include:
  - Target service (web, api, payments, or notifier).
  - Exercise owner and participating service owner.
  - Targeted time window (must avoid peak hours, 18:00–23:00 JST, and the 22:00–07:00 JST deploy restriction window).
- Share the test plan with the platform lead (Kenji Sato) and the respective service owner (Aiko, Ravi, Mei, or Tom).

### 2. Coordination Phase (24 Hours Prior)
- Review the change calendar to confirm that no major feature rollouts or provider maintenance windows coincide with the test.
- Check with the active on-call engineer to verify they have reviewed the scenario and know what alerts are anticipated.
- Ensure that all load generation tooling is configured to inject `X-Sorrel-Loadtest` headers on every outbound HTTP request.

### 3. Execution Phase
- Open an exercise coordination thread in chat.
- Confirm baseline dashboard metrics across web, api, payments, and notifier.
- Announce the official start of fault injection.
- The on-call primary monitors telemetry boards and acknowledges alerts.
- Keep fault injection windows constrained to a maximum of 30 minutes.
- If unexpected metrics emerge, execute the abort procedure: revert injection, allow clusters to stabilize, and verify node health.

### 4. Post-Drill Wrap-Up
- The exercise owner posts a summary to the team drive within 48 hours of completion.
- Any tooling gaps, missing dashboard panels, or alert threshold bugs uncovered during the drill must be logged as tickets for the owning team.
- Review findings during the regular Thursday platform review meeting.

---

## 7. Common Failure Modes and Safety Boundaries

When planning scenarios, consult Section 7 of the on-call handbook to ensure drill mechanics respect known system constraints:

- **Database and storage constraints:** Never execute primary database failovers or storage detach drills during Friday booking peaks or Sunday night payout runs (payments weekly payouts execute at 23:00 JST on Sundays).
- **External provider rate limits:** Synthetic traffic must never target outside vendors directly in ways that consume production quota. Avoid generating artificial volume that triggers twilio SMS limits or sendgrid daily email thresholds.
- **Payment provider integrity:** Under no circumstances should game days simulate duplicate charges or forced webhook mutations against live stripe endpoints. Testing payments must use mock configurations or non-destructive validation checks approved by Mei.
- **Tenant isolation filters:** If exercising api routing or search endpoints, ensure synthetic test requests do not trigger `api-cross-tenant` alerts. Tenant check failures in the response filter page on-call unconditionally.

By keeping game days visible on the calendar, maintaining strict communication with the on-call rotation, and clearly tagging artificial load, we keep production safe while continuously validating our operational resilience.
