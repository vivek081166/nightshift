# Postmortem: aws DNS incident in ap-northeast-1

Date: 2026-04-21  
Owner: Ravi (api)  
Severity: P1  
Incident Commander: Kenji Sato  
On-call engineer: Noor  

---

## 1. Summary

On Tuesday, 2026-04-21, between 11:14 JST and 11:37 JST, our primary region (`ap-northeast-1`, Tokyo) suffered degraded internal name resolution caused by an underlying aws network infrastructure failure. For 23 minutes, `api` nodes operating in Tokyo were intermittently unable to resolve internal DNS names, including local database primary and replica endpoints, cache clusters, and internal service targets. 

Because `api` is the core dependency for customer operations, web rendering and booking workflows routed to Tokyo experienced elevated 5xx error rates, failed slot lookups, and timed-out booking checkout confirmations. Services running in our other two active production regions, `us-east` and `eu-west`, remained completely unaffected and maintained normal request volumes, latency profiles, and error budgets throughout the duration.

Nothing on our side needed to change. The on-call engineer confirmed the fault directly on the aws health dashboard, verified that the issue was localized to regional provider infrastructure rather than a bad deploy or application configuration fault, and kept the `#inc-live` incident thread updated. Although moving traffic out of `ap-northeast-1` was evaluated alongside the incident commander, the team decided against rerouting because aws posted initial recovery notices within 20 minutes of the degradation start, well before an emergency regional drain could safely finish. Resolution occurred cleanly once provider DNS resolution stabilized at 11:37 JST.

---

## 2. Impact

### 2.1 Customer Experience
- **Japan / East Asia (Tokyo region):** Customers attempting to search for open slots or confirm appointments between 11:14 JST and 11:37 JST experienced 502/504 errors on `web` and API failures. Businesses managing schedules via the web dashboard during this late-morning peak window experienced intermittent connection drops and failed calendar writes.
- **North America (`us-east`) and Europe (`eu-west`):** Zero customer-facing degradation. All booking requests, partner traffic, and payments resolved normally without latency spikes.

### 2.2 Metrics & Error Budget
- **Duration:** 23 minutes of active failure (11:14 to 11:37 JST). Full service recovery verified across all nodes at 11:42 JST.
- **Affected Endpoints:** In `ap-northeast-1`, failure rate across the booking, search, and account endpoint groups peaked at 41% on board "Sorrel / api".
- **Error Budget Impact:** The monthly error budget for booking endpoints on `api` sustained a 12% burn during the window. Because the failure was isolated to 23 minutes, the service did not exhaust its total monthly allotment.
- **Upstream Services:**
  - `web`: Experienced a corresponding jump in edge 5xx responses for Japan traffic as server-side render requests to `api` timed out.
  - `payments`: Checkout submissions in `ap-northeast-1` dipped; transactions that could not establish upstream verification to `api` marked bookings as "payment pending" until resolution. No duplicate charges occurred.
  - `notifier`: Queued background delivery was not materially harmed; background worker nodes in Tokyo backed up temporarily while waiting on database queries but drained their queues promptly once resolution cleared.

### 2.3 Data and Financial Harm
- **Data Exposure:** None. Response tenant filters functioned properly. Zero cross-tenant leakage occurred (`api-cross-tenant` remained clean).
- **Financial Loss:** No money was moved wrongly. There were no duplicate charges, erroneous refunds, or payout discrepancies. Incomplete checkout attempts safely dropped without executing settlement authorizations against stripe.

---

## 3. Incident Timeline (all times JST)

| Time | Event / Action |
|---|---|
| **11:14** | Underlying internal DNS resolution degrades across multiple availability zones in `ap-northeast-1`. `api` nodes in Tokyo log failures resolving internal database and cache hostnames. |
| **11:17** | Paging tool alerts fire: `api-region` indicates >20% request failure rate specifically isolated to Tokyo. Noor acknowledges the page within 3 minutes. |
| **11:19** | Noor opens an incident thread in `#inc-live` as required for P1 conditions, posting initial error rates and noting that the failure is strictly isolated to `ap-northeast-1`. |
| **11:21** | Noor inspects board "Sorrel / api". Regional panel confirms `us-east` and `eu-west` latency and error rates are completely green. Deploy history shows `api` last deployed 4 days ago; no recent release is suspect. |
| **11:23** | Noor runs log search `service=api msg="dns" region=ap-northeast-1` in the log search tool, revealing continuous upstream lookup timeouts against regional resolver addresses (`169.254.169.253`). |
| **11:25** | Noor checks provider dashboards. aws personal health dashboard and public health status (`health.aws.amazon.com`) both publish active notices confirming a regional incident regarding internal DNS resolution errors for VPC instances in `ap-northeast-1`. |
| **11:26** | Noor posts the aws status update and dashboard link into `#inc-live`, confirming the incident is driven entirely by an external provider fault. |
| **11:29** | Incident has exceeded 15 minutes. Incident commander rotation is paged. Kenji Sato assumes the incident commander role in `#inc-live`. Status page update drafted. |
| **11:31** | Status page update published to status.sorrel.app by Kenji Sato using the standard investigating template: *"We are investigating reports of problems with bookings. We will update this page within 30 minutes."* |
| **11:32** | Ravi (api owner) joins the thread. Kenji Sato, Ravi, and Noor evaluate whether to initiate an emergency regional traffic shift from Tokyo into `us-east`. |
| **11:34** | aws updates its health dashboard, stating that the root cause within the VPC DNS infrastructure has been identified and mitigation is actively propagating across Tokyo availability zones, with recovery expected in under 10 minutes. |
| **11:35** | Kenji Sato and Ravi decide against moving traffic out of the region. A cold failover of database primaries across regions carries replication latency risks and takes upwards of 30 minutes, exceeding the expected provider recovery time. |
| **11:37** | aws internal DNS stabilizes. DNS query timeouts in `service=api` logs drop to zero. Tokyo node connection pools begin reconnecting successfully to database replicas and primary instances. |
| **11:40** | Board "Sorrel / api" displays 5xx rates dropping below 0.2% across Tokyo endpoints. `web` server-side rendering latency returns to normal baseline. |
| **11:42** | Incident commander posts an updated message to status.sorrel.app using the resolved template: *"The problems with bookings between 11:14 and 11:37 JST have been resolved. We are sorry for the trouble."* |
| **11:45** | Queues on `notifier` confirmed to be draining cleanly. No stuck workers or database locks remaining. Incident formally marked resolved in `#inc-live`. |

---

## 4. Analysis and Investigation

### 4.1 Root Cause
The root cause was an external infrastructure degradation within aws Route 53 Resolver / VPC internal DNS infrastructure in `ap-northeast-1`. During the 23-minute window, EC2 instances running the eight autoscaled `api` nodes (and four `payments` nodes) experienced dropped UDP packets and 5-second timeouts when resolving AWS-internal fully qualified domain names.

Because `api` utilizes pooled database connections that occasionally refresh, alongside dynamic lookup targets for replication health checks, name resolution failures resulted in:
1. Connection pool depletion as connection attempts hung on unresolved addresses.
2. Immediate 500/503 responses returned to `web` for endpoints requiring synchronous database reads.
3. Elevated render latencies and fallback error views presented to end users on public salon and clinic booking pages.

### 4.2 Regional Independence Verification
A critical operational factor during this incident was the clean separation between regions:

| Region | Status During Incident | Request Volume | Latency (p95) | Error Rate |
|---|---|---|---|---|
| `ap-northeast-1` (Tokyo) | Degraded (Provider DNS down) | 62% of global | 4,200 ms | 41.2% |
| `us-east-1` (Virginia) | Operational | 24% of global | 185 ms | 0.04% |
| `eu-west-1` (Ireland) | Operational | 14% of global | 210 ms | 0.02% |

Our multi-region footprint prevents infrastructure incidents in Tokyo from impacting European or American businesses. However, because Tokyo is our largest customer base, regional isolation alone does not avoid significant customer friction during Japanese daylight hours.

### 4.3 Why Traffic Was Not Moved
When an entire region experiences provider-level infrastructure degradation, our runbook allows for shifting traffic to another operational region. This was actively discussed between Kenji Sato (IC), Ravi (api owner), and Noor (on-call).

The team decided against regional traffic failover for three specific technical reasons:
1. **Database Consistency:** `api` uses a regional primary database model. Shifting writes from `ap-northeast-1` to `us-east` requires promoting a cross-region read replica to a primary state. This operation risks write divergence and replication lag reconciliation issues, requiring significant coordination by the owner.
2. **Execution Time:** A structured multi-region drain and database repointing takes between 25 and 35 minutes to execute safely without risking orphaned bookings or split-brain records.
3. **Provider Recovery Projections:** aws updated their health dashboard within 20 minutes of the degradation stating that the mitigation was already propagating. Initiating a failover at 11:35 JST would have introduced substantial operational disruption and extended downtime long past the moment the provider actually recovered (11:37 JST).

The decision to remain in-place and await provider recovery was the correct choice and minimized customer impact.

---

## 5. What Went Well

- **Rapid Identification:** Noor correctly followed the on-call guidelines: rather than guessing or attempting an unsafe code change, she checked the board "Sorrel / api", ruled out recent deploys (last release was days old), verified that the failure was strictly regional, and confirmed the provider's status directly on the aws personal health dashboard.
- **Accurate First Move:** The first move taken was checking the provider. No unnecessary rollbacks were attempted, preventing additional service restarts or CDN cache disruptions during an active network fault.
- **Clean Incident Channel Communication:** Status updates in `#inc-live` were logged every 5 to 10 minutes with clear, factual metrics (error rates, specific log errors, provider status links) rather than speculative summaries.
- **Strict Role Boundaries Respected:** The on-call engineer did not attempt to alter regional routing or DNS topologies unilaterally. Shifting traffic was rightly escalated to the incident commander and service owner.
- **Customer Status Communication:** Kenji Sato updated status.sorrel.app within the prescribed 20-minute window, ensuring support teams had clear external documentation to point customers to.

---

## 6. What Went Badly

- **Application-Level DNS Caching:** `api` nodes were querying the local VPC DNS resolvers too frequently on new database connection attempts. Although connection pools reuse established TCP sockets, transient pool recycling under load forced new name resolutions that immediately blocked worker threads for the full 5-second resolver timeout.
- **Alert Storm on Downstream Services:** When `api` in Tokyo began dropping requests, alerts on `web` (`web-5xx`) and `payments` (`payments-checkout`) fired in rapid succession. While expected given service dependencies, the incident channel was initially noisy before Noor established that `api` connection timeouts were the single origin.
- **Lack of Local Hosts Fallback:** Our deployment configuration relies on AWS-managed DNS names for database read replicas rather than static local IP configurations or local cache daemons (like `nscd` or `systemd-resolved` with aggressive negative caching protections).

---

## 7. Where We Got Lucky

- **Provider Resolution Speed:** aws resolved the underlying network routing fault within 23 minutes. Had the incident persisted for over 45 minutes, customer impact in Japan during the lunch peak would have forced an emergency regional drain, introducing substantial recovery overhead.
- **Timing:** The event occurred at 11:14 JST, just before the primary lunchtime booking rush (12:00–13:00 JST). Had the DNS outage occurred 45 minutes later, the volume of impacted appointments and salon customer inquiries would have tripled.
- **No Background Queue Corruption:** In-flight background tasks on `notifier` handling SMS reminders via twilio and email confirmations via sendgrid backed up gracefully on their local queues without crashing workers or generating duplicate message ids.

---

## 8. Action Items

| Action Item | Owner | Target Date | Description |
|---|---|---|---|
| **Tune Node-Level DNS Caching** | Sara (platform) | 2026-05-08 | Configure local DNS caching daemon on `api` and `payments` node base images to cache positive internal DNS lookups for at least 300 seconds, smoothing over brief provider lookup blips. |
| **Connection Pool Timeout Hardening** | Daniel (api) | 2026-05-15 | Reduce the TCP connection acquisition and resolver timeout in `api` database pools from 5,000 ms to 1,500 ms so worker threads fail fast rather than locking request threads under DNS degradation. |
| **Runbook Documentation for Regional Drain** | Kenji Sato (platform lead) | 2026-05-22 | Document a formal checklist and decision tree for cross-region traffic shifting to guide incident commanders during multi-hour single-region provider outages. |
| **Support Lead Incident Summary** | Hana (support lead) | 2026-04-24 | Share an incident summary with support staff to address customer inquiries from salon and clinic owners regarding the booking drop between 11:14 and 11:37 JST. |
| **Review Cloud Health Notification Integration** | Noor (SRE) | 2026-05-01 | Ensure aws personal health dashboard notifications pipe directly into the platform operations alert stream to further accelerate provider-correlation during regional outages. |
