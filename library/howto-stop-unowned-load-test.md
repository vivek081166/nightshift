# How to stop a load test that nobody owns

Date: 2026-05-04  
Owner: Sara (platform)

This procedure explains how to identify, verify, and stop unannounced or orphaned synthetic load tests hitting Sorrel services. It applies to primary on-call engineers, secondary on-call engineers, and platform engineers.

---

## 1. Context and Scope

Sorrel runs four production services across three active cloud regions (`ap-northeast-1` in Tokyo, `us-east-1`, and `eu-west-1`): `web`, `api`, `payments`, and `notifier`. To validate capacity, connection pooling, and autoscaling, engineering teams periodically generate synthetic traffic against staging and production endpoints.

However, synthetic load generation carries operational risks if forgotten or misconfigured:
- It consumes connection pools and database read replicas.
- It can inflate error rates or burn monthly error budgets on key paths like the booking endpoints.
- It skews latency metrics (p50, p95, p99) and causes unnecessary autoscaling thrash.
- It triggers noisy alerts that distract on-call engineers during shifts.

Section 7.15 of the On-Call Handbook classifies unannounced synthetic traffic as a known failure mode. Under Section 17, the on-call engineer has explicit operational permission to stop rogue load tests immediately. You do not need prior approval from service owners or the incident commander rotation to terminate a test that has no listed owner or schedule.

### 1.1 The April 2026 Incident

In 2026-04, a forgotten soak test ran for 9 hours against `api` in `us-east` before anyone noticed.

During this incident:
- The synthetic client generated sustained traffic against `api` search and booking endpoints in `us-east-1`.
- Because the run was left running overnight without an entry on the schedule, the primary on-call engineer assumed the sustained request rate was legitimate partner activity or crawler traffic.
- Over the 9-hour period, database pool usage in `us-east` remained elevated at 75–85 %, slowly degrading search index query times and replica lag.
- The test was discovered only after shift handover when Daniel reviewed slow query logs during daytime working hours.

This runbook exists to ensure orphaned tests are recognized within minutes and stopped safely.

---

## 2. Identifying Synthetic Load Test Traffic

When request volume spikes or latency creeps upward on a service board without clear customer reports, do not assume it is an external denial-of-service attack or partner burst until you check the request headers and source addresses.

### 2.1 Key Characteristics

Legitimate Sorrel synthetic load test traffic always exhibits two strict properties:
1. **Header:** Load test traffic carries the `X-Sorrel-Loadtest` header on every HTTP request.
2. **Origin:** The traffic comes from our own address ranges (our dedicated load generation nodes and cloud subnets).

If traffic carries the header but originates outside our known IP ranges, treat it as anomalous external traffic and evaluate it under Cloudflare rate limiting rules with Aiko.

### 2.2 Dashboard Indicators

Open the metrics tool and check the relevant service board:
- **Sorrel / web:** Look at the "Request rate, split by status class" and "Error rate by route" panels. Look for uniform, mechanical request curves that do not match the normal business calendar diurnal curve (see Section 13.1 of the handbook).
- **Sorrel / api:** Look at the "Request rate by endpoint group" and "Database: connections in use per pool" panels. Synthetic tests usually target search or booking endpoints repeatedly. Check the SLO panel to verify how much error budget is being consumed.
- **Sorrel / payments:** Check the "Checkout submissions, successes and failures per minute" panel. (Synthetic load tests should rarely target payments directly; if card generation scripts are running against production checkout without Mei's supervision, treat this with extreme urgency).

### 2.3 Log Verification Queries

To confirm that incoming requests are synthetic, run targeted log searches in the log search tool against `sorrel-prod-*`. Narrow the search window to the last 15–30 minutes to keep queries fast.

#### Check for the Load Test Header

```text
service=api http_header_x_sorrel_loadtest=*
```

Or for `web`:

```text
service=web http_header_x_sorrel_loadtest=*
```

#### Identify the Test Identifier and Source Nodes

Our load generation runner injects the test identifier and agent metadata into the header value or structured request tags:

```text
service=api http_header_x_sorrel_loadtest=* | stats count by http_header_x_sorrel_loadtest, client_ip, endpoint
```

Look at the output fields:
- `http_header_x_sorrel_loadtest`: Typically formatted as `test-<name>-<uuid>` or `soak-<region>-<id>`.
- `client_ip`: Verify that the IP falls within our internal cloud VPC blocks or dedicated egress IPs.
- `endpoint`: Shows which paths are absorbing the synthetic throughput.

---

## 3. Decision Matrix: Game Day Calendar vs. Rogue Run

Do not terminate a test blindly if it is part of an authorized, active exercise. Breaking an active disaster recovery drill or game day disrupts team planning and wastes engineering time.

Follow this decision sequence:

```
                      [Alert / Traffic Anomaly]
                                  |
                                  v
                [Verify X-Sorrel-Loadtest Header
                  and Internal Address Ranges]
                                  |
                   +--------------+--------------+
                   |                             |
             Matches both                 Header missing /
                   |                      External origin
                   v                             |
        [Check Game Day Calendar]                v
                   |                    [Investigate traffic
         +---------+---------+          via normal runbooks:
         |                   |          crawler, partner API,
     Found on            Not found /     or DDoS attack]
     calendar             No owner
         |                   |
         v                   v
   [Contact Owner      [STOP TEST IMMEDIATELY:
    before stopping]    loadctl stop <test id>]
                             |
                             v
                       [Post in #platform
                        and incident thread]
```

### 3.1 Step 1: Check the Game Day Calendar

Before executing any stop commands, open the change calendar:
1. Go to the shared team calendar and filter by "Game Days" and "Planned Tests".
2. Check whether an exercise was scheduled for this date and window.
3. Look for the listed test coordinator or owner (e.g., Kenji Sato, Sara, Daniel, Yuki, Leo, Priya, or Noor).

### 3.2 If the Test is on the Calendar

- **Rule:** Check the game day calendar first; if the test is on it, ask its owner before stopping it.
- Send a direct message in `#platform` or the dedicated exercise channel tagging the owner.
- Provide clear operational data:
  - Current service impact (e.g., "us-east api connection pools at 88 %, p95 search latency up to 2.1 s").
  - Ask: *"The test `soak-us-east-04` is pushing api close to alert thresholds. Can you throttle back or terminate now?"*
- **Exception:** If the test has caused an unhandled P1 (e.g., real customers cannot book, error budget burn rate breaches P1 thresholds, or database connection pools completely exhaust causing widespread 5xx responses), the on-call engineer can halt the traffic immediately to protect production, then notify the owner.

### 3.3 If Nobody Owns It

- If there is **no entry on the calendar**, or the listed calendar window ended hours ago, or the test has no identifiable person in the tags: **it is an orphaned test**.
- Proceed immediately to Section 4 and stop the test using the command-line tool.

---

## 4. How to Stop the Test with `loadctl`

All synthetic load runners across our regions are controlled by the central load test management utility, `loadctl`.

### 4.1 Prerequisites

- Connect to the management bastion or access the platform CLI environment via your authenticated developer terminal.
- Ensure your local environment has administrative credentials for the load generation coordinator.

### 4.2 Step-by-Step Termination

#### 1. List Active Load Test Runs

Run `loadctl list` to view all active test runners across all regions:

```bash
loadctl list
```

Example output:

```text
TEST ID                 REGION         TARGET SERVICE    TARGET REGION    RPS     STARTED              OWNER
soak-us-east-8192a      us-east-1      api               us-east-1        450     2026-05-04 01:15 JST  UNKNOWN
capacity-tokyo-01       ap-northeast-1 web               ap-northeast-1   120     2026-05-04 09:30 JST  daniel
```

Examine the output:
- Identify the `TEST ID` that corresponds to the traffic seen in the logs or metrics.
- Note the `OWNER`, `STARTED` time, and current `RPS`.

#### 2. Stop the Test

- **Rule:** If nobody owns it, stop it with the load test tool: `loadctl stop <test id>`, and tell `#platform`.

Execute the stop command using the exact test ID:

```bash
loadctl stop <test id>
```

Example:

```bash
loadctl stop soak-us-east-8192a
```

The tool will send an interrupt signal to all worker nodes in the load cluster:

```text
[loadctl] Sending SIGTERM to worker cluster (8 agents)...
[loadctl] Draining active connections...
[loadctl] soak-us-east-8192a stopped successfully.
[loadctl] Total requests terminated: 0. Workers idle.
```

#### 3. Force Kill (Emergency Only)

If `loadctl stop <test id>` hangs or worker nodes fail to terminate connections within 30 seconds, force the termination:

```bash
loadctl stop <test id> --force
```

This immediately drops agent worker processes and severs TCP connections to our load balancers.

---

## 5. Post-Action Communication and Logging

Stopping the test is only the mechanical half of handling the incident. You must leave an audit trail so the team understands what happened and why traffic dropped.

### 5.1 Notify `#platform` Immediately

As soon as the test is terminated, post a summary in the `#platform` chat channel:

> **Heads-up:** Stopped orphaned load test `<test id>` running against `<service>` in `<region>`.  
> - **Test ID:** `<test id>`  
> - **Traffic rate:** `<RPS>` rps  
> - **Symptom:** `<e.g., api connection pool reached 85 % in us-east-1 / p95 latency elevated>`  
> - **Calendar check:** No entry on Game Day calendar, no owner found in metadata.  
> Please claim this run if you started it.

### 5.2 If an Incident Thread Was Open in `#inc-live`

If the load test caused alerts (such as `web-traffic`, `api-pool`, or `api-latency`) that resulted in an incident thread in `#inc-live`:
1. Post an update with the concrete action:
   > "Identified synthetic traffic with X-Sorrel-Loadtest from internal range. No owner on calendar. Executed `loadctl stop <test id>` at 14:22 JST. Request volume returning to baseline."
2. Watch dashboards for 10 minutes to verify:
   - Connection pools recover to normal baseline levels (< 50 %).
   - Latency returns to expected percentiles.
   - 5xx and 4xx rates clear.
3. Close the incident according to standard handbook procedures.

### 5.3 On-Call Log Entry

Every alert requires an entry in the on-call log as defined in Section 9.1 of the handbook. Format the line exactly:

`<date> <time JST> | <service> | <severity> | <first move> | <one sentence: what you saw and why you chose that move>`

#### Example Log Entries

For an alert triggered by unannounced load test traffic where you confirmed synthetic origins:

```text
2026-05-04 14:20 JST | api | P3 | read logs | Saw api-traffic spike in us-east, read logs to confirm internal X-Sorrel-Loadtest header, found no game day owner, and stopped test via loadctl.
```

If pool limits alerted:

```text
2026-05-04 14:22 JST | api | P2 | read logs | Connection pool alerted at 91 %, read logs showing synthetic soak test with no calendar owner, halted run via loadctl stop soak-us-east-8192a.
```

*(Note: The handbook rules strictly mandate that the first move recorded in the on-call log must be one of the five canonical actions: `roll back`, `read logs`, `check provider`, `page owner`, or `no action`. When investigating anomalous traffic, reading the service logs to identify the header and IP is the correct first move).*

---

## 6. Service Impact Reference Guide

When assessing whether synthetic traffic requires an immediate stop or an escalated incident, use the following service-specific guidelines:

| Service | Owner | Critical Panels on Service Board | Risk of Unowned Load Tests |
|---|---|---|---|
| **web** | Aiko | Request rate by status, p95 page load time, Node health (CPU/memory), CDN edge errors | Can exhaust render cache, saturate node memory on SSR workers, trigger false autoscaling (spinning up to max 12 nodes). |
| **api** | Ravi | Connection pools in use, p95/p99 latency by endpoint group, SLO error budget burn, replica lag | Saturated database connection pools cause timeouts across search and booking. May burn monthly SLO budget quickly. |
| **payments** | Mei | Checkout submissions/min, provider response times, validation errors, webhook retries | High danger if test hits live provider endpoints (Stripe). If synthetic card runs touch production, notify Mei immediately. |
| **notifier** | Tom | Queue depth, messages added/delivered per minute, vendor error codes and daily quota | Tests injecting fake notifications will saturate worker queues, backlog customer reminders, and burn Twilio/SendGrid vendor quotas. |

### 6.1 Database Connection Pool Exhaustion on `api`

Synthetic tests against `api` are the most common source of self-inflicted degraded performance. 
- Each of the 8 nodes per active region maintains its own pool.
- If a test floods heavy queries (e.g., "find a slot near me" search queries), connections stay open longer.
- If pool utilization stays above 90 % for 10 minutes, the `api-pool` alert pages on-call.
- Requests begin timing out once the pool is completely full.

If you observe `msg="pool exhausted"` in logs alongside `X-Sorrel-Loadtest` headers, do not wait for the test owner to reply in chat: **stop the test immediately**.

---

## 7. Prevention and Cleanup

To prevent repeats of the April 2026 9-hour incident:

1. **Mandatory Metadata:** All test configurations passed to `loadctl` must specify `--owner <name>` and `--duration <minutes>`. The tool will reject tests without an owner tag.
2. **Hard Timeouts:** All load tests have a default automated safety ceiling of 120 minutes. Soak tests exceeding 2 hours require an explicit `--soak` flag and an approved entry linked to the Game Day calendar.
3. **Calendar Requirement:** Any test intended to generate over 100 requests per second against production must be logged on the Game Day calendar at least 24 hours in advance.
4. **Postmortem Action Items:** If an unowned test runs for more than 30 minutes undetected or degrades production metrics, file a tracking ticket assigned to the platform team (Kenji Sato / Sara) to investigate why runner timeouts failed and audit load test runner infrastructure.
