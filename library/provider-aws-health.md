# aws: health dashboard and regions

Date: 2026-02-16  
Owner: Kenji Sato (platform lead)

---

## 1. Overview and scope

Sorrel runs its core infrastructure entirely on Amazon Web Services (aws). All four production services—`web`, `api`, `payments`, and `notifier`—as well as their backing datastores, worker queues, static storage, and routing systems reside within aws infrastructure.

Outside dependencies such as Stripe, Twilio, SendGrid, and Cloudflare handle targeted edge or delivery capabilities, but the compute nodes, regional databases, internal DNS, and ingress load balancers are managed in aws. When aws experiences an infrastructure degradation, service connectivity faults, or network partition events, the impact will manifest directly across Sorrel’s internal health signals.

This document sets down how we configure, monitor, and react to regional health events, how incoming notifications from aws are ingested and routed, where traffic flows, and the boundaries of authority when an operational degradation suggests shifting workload across regions.

---

## 2. Regional footprint and traffic distribution

Sorrel is deployed across three active cloud regions:

- `ap-northeast-1` (Tokyo)
- `us-east-1` (N. Virginia)
- `eu-west-1` (Ireland)

### 2.1 Regional weighting and sizing

Our operational centre of gravity is `ap-northeast-1`. It serves our domestic Japanese customer base and carries the largest share of our total booking, search, and checkout volume.

| Region | Primary function | Typical share of traffic | Autoscaling bounds | Primary datastores |
|---|---|---|---|---|
| `ap-northeast-1` | Domestic production core | ~65–70% of total bookings and writes | web: 6–12 nodes<br>api: 8–20 nodes<br>payments: 4 nodes<br>notifier: 3 workers | Primary relational database (`api`), primary datastore (`payments`), search index cluster, task queues |
| `us-east-1` | Americas regional traffic | ~15–20% | web: 6–12 nodes<br>api: 8–20 nodes<br>payments: 4 nodes<br>notifier: 3 workers | Regional relational database read replicas, search index replica, task queues |
| `eu-west-1` | Europe regional traffic | ~10–15% | web: 6–12 nodes<br>api: 8–20 nodes<br>payments: 4 nodes<br>notifier: 3 workers | Regional relational database read replicas, search index replica, task queues |

Because `ap-northeast-1` carries the most traffic, an incident in Tokyo produces immediate, severe changes across top-line dashboards. A networking or storage event in `us-east-1` or `eu-west-1` tends to be contained to regional customer sessions and daylight-saving time-dependent schedules, though it remains a significant degradation.

### 2.2 Sizing and resilience characteristics

Each active region maintains an independent compute allocation:
- **web:** Minimum 6 nodes behind the regional load balancer, scaling to 12. Local server-side rendering caches run on node disks.
- **api:** Minimum 8 nodes behind the regional load balancer, scaling to 20. Nodes manage connection pools to regional datastore endpoints and talk to the local search cluster.
- **payments:** 4 nodes in each active region, connecting to its dedicated regional datastore and issuing outbound network calls to Stripe.
- **notifier:** 3 worker nodes per active region reading from the message queue subsystem, accompanied by the scheduling process that handles appointment reminder dispatching.

Database architecture utilizes regional primary-replica layouts. The primary database cluster for `api` resides in `ap-northeast-1`, maintaining two local read replicas in the region along with cross-region read replicas in `us-east-1` and `eu-west-1`. Storage for static assets, backups, and deploy build outputs relies on regional object storage buckets.

---

## 3. Health dashboard alerting and notification paths

We monitor aws health through two distinct operational interfaces: the public service health dashboard and the Personal Health Dashboard (PHD) specific to our account.

### 3.1 Public health vs. Personal Health Dashboard

The public health dashboard (`health.aws.amazon.com`) reflects broad, provider-wide outages across an entire metropolitan area or service tier. Public statuses update manually, frequently lagging real-world customer impact by ten to twenty minutes.

In contrast, our account's Personal Health Dashboard reflects specific, direct hardware, tenancy, and resource notifications:
- Degraded physical hypervisors hosting specific compute instances.
- Scheduled maintenance windows on managed database clusters.
- Storage volume degradation or throttling in a targeted availability zone.
- Direct networking, load balancer, or DNS degradation impacting our provisioned resources.

### 3.2 Automated ingestion: `#aws-health`

To eliminate the need for engineers to manually poll dashboards during suspected infrastructure events, events from our account's Personal Health Dashboard are ingested directly through an event bus rule and delivered to chat.

Personal health dashboard notifications for our account are posted automatically in `#aws-health`.

When an alert fires or an unexpected regional error rate appears:
1. Check the `#aws-health` stream before opening external consoles.
2. If an event has dropped into `#aws-health`, read the impacted resource identifier, availability zone, and service designation.
3. Cross-reference the timestamp with the incident timeline.
4. Copy the raw message text or summary into the active incident thread in `#inc-live` if an incident is open.

Do not paste internal account identifiers or direct console links into external customer-facing notes. In `#inc-live`, the notification text confirms whether the problem sits within our provisioned instances or the underlying aws fabric.

---

## 4. Identifying aws degradation during on-call triage

When an on-call engineer receives an alert, section 1 of the On-Call Handbook requires establishing severity, picking the first move, and writing the finding in `#inc-live`. Section 3.3 defines `check provider` as looking at an outside service we depend on when the alert points to one.

### 4.1 Regional symptom signatures

An infrastructure problem inside aws usually presents with distinct shapes:

```
[Customer traffic]
        │
   (Cloudflare)
        │
   [aws Regional Ingress / ALB]
        │
   ┌────┴───────────────────────────┐
   │                                │
[web nodes]                   [api nodes]
   │                                │
[Shared Cache]                [Database Pool / Local Replicas]
```

- **Isolated regional failures:** The dashboard shows `api-region` firing, with 5xx or connection drops concentrated entirely in `us-east-1` or `eu-west-1` while `ap-northeast-1` runs completely clean.
- **DNS resolution timeout:** Logs show `service=api msg="dns" region=<region>` or timeouts connecting to internal endpoints within a single VPC.
- **Node-level virtualization degradation:** A single instance repeatedly fails health checks or restarts (`web-node-restart`), but adjacent nodes deploy and serve traffic without issue.
- **Storage latency spikes:** Database replication lag jumps on read replicas in one region, or local render cache reads on `web` begin hitting disk timeouts (`web-disk` moving upward).

### 4.2 Verifying provider health

If the alert line references a provider issue, an entire region failing, or a sudden spike in infrastructure-level timeouts, execute the following triage steps:

1. **Review `#aws-health`:** See if an automated notification has arrived for the impacted region or availability zone.
2. **Review Personal Health Dashboard:** Check whether underlying hosts, network fabrics, or managed database nodes have active alerts for our resources.
3. **Check the public health page (`health.aws.amazon.com`):** Look at the summary table for `ap-northeast-1`, `us-east-1`, and `eu-west-1` across EC2, RDS, VPC, and Route 53.
4. **Inspect regional metrics:** On board "Sorrel / api", filter latency and error rates by region. On board "Sorrel / web", inspect status classes split by region.
5. **Inspect the logs:** Query the log search tool against index `sorrel-prod-*`:
   - For `api`: `service=api msg="dns" region=<region>` or `service=api level=ERROR` restricted to the start of the window.
   - For `web`: `service=web status>=500` grouped by region.

If `#aws-health` or the provider status board shows active trouble, do not roll back Sorrel services. Code did not fail; undoing deploys will not fix underlying cloud provider partition faults. Note the finding in `#inc-live` and follow provider-incident communication procedures.

---

## 5. Decision authority: moving traffic out of a region

When an entire aws region degrades—for example, prolonged compute failure or connectivity loss across multiple availability zones in `ap-northeast-1`—the question of redirecting ingress traffic or shedding load inevitably arises.

### 5.1 Strict limits on on-call authority

On-call engineers are responsible for taking the immediate first move, arresting initial damage, and waking owners when irreversible or high-impact decisions are required. 

The On-Call Handbook is unambiguous:
- **On-call engineers do not reroute regional traffic.**
- Changing region-level routing alters global state, forces failover across multi-region database connections, risks primary datastore split-brain scenarios, and stresses replica infrastructure.
- **Moving traffic out of a region is decided by the incident commander with the owners of the affected services.**

### 5.2 Who must be involved

If regional degradation persists and shifting customer traffic away from a failing region is considered, the following individuals must decide:

- **Incident Commander:** Appointed for any P1 lasting longer than 15 minutes. The commander coordinates overall response and evaluates system stability.
- **Aiko (web owner):** Manages front-end ingress, CDN edge routing rules, and Cloudflare regional origin directs.
- **Ravi (api owner):** Manages the core transactional engine, regional database replicas, replication lag constraints, and data consistency.
- **Mei (payments owner):** Manages regional checkout routing and webhooks from Stripe to avoid duplicate charges or orphaned transactions.
- **Tom (notifier owner):** Manages regional worker queue pools and vendor integration fallbacks.

```
                  ┌────────────────────────┐
                  │   Incident Commander   │
                  └───────────┬────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
   ┌──────┴──────┐     ┌──────┴──────┐     ┌──────┴──────┐
   │ Aiko (web)  │     │ Ravi (api)  │     │  Mei (pay)  │
   └─────────────┘     └─────────────┘     └─────────────┘
                              │
                       ┌──────┴──────┐
                       │  Tom (notif)│
                       └─────────────┘
```

The on-call engineer supports this group by gathering regional telemetry, monitoring replication metrics, and tracking updates posted in `#aws-health`.

### 5.3 Operational hazards of regional shifting

Why regional traffic shifts are tightly restricted:

1. **Database writes:** All core writes for `api` terminate on the primary datastore cluster in `ap-northeast-1`. Moving `web` traffic to `us-east-1` while the database remains in Tokyo incurs cross-Pacific round-trip network latency on every database write, degrading checkout and booking flows.
2. **Replication lag:** If read replicas in `us-east-1` or `eu-west-1` are lagging behind the primary, sending search and booking reads to those regions will present stale calendar slots to customers, leading to overbooking and data inconsistencies.
3. **Capacity limits:** `ap-northeast-1` handles the vast majority of our load. Shifting Tokyo's volume into `us-east-1` or `eu-west-1` without prior autoscaling adjustments will quickly exhaust connection pools and compute allocations in the receiving regions.

---

## 6. Accounts, limits, and administrative controls

Administrative governance within aws is separated between day-to-day platform engineering operations and commercial/account-level authorizations.

### 6.1 Account ownership

The aws account and its underlying cloud infrastructure are owned by the platform team:
- **Kenji Sato** (Platform Lead)
- **Sara** (Platform Engineer)

The platform team oversees VPC peering, core security groupings, base image provisioning, container base layers, cross-region replication links, and log ingestion pipelines into `sorrel-prod-*`.

### 6.2 Billing and service limits

Service quotas (such as instance limits per region, VPC elastic network interface limits, elastic IP allocations, and KMS throughput caps) periodically require adjustment as traffic grows or new nodes are provisioned.

- **Billing and limit increases go through Ravi.**
- Neither on-call engineers nor individual service owners submit service limit increase requests, enterprise support tier changes, or billing modifications directly to aws.
- When an engineering team plans an expansion that approaches regional quotas, they submit an internal request to Ravi and the platform team. Ravi handles the administrative sign-off and limit increase requests.

---

## 7. Reference operational runbook

When aws issues are suspected, follow this quick reference sequence:

```
[Alert Fires]
      │
      ▼
Check #aws-health in chat
      │
      ├─► [Notification found] ──► Confirm impacted region
      │                             Paste details in #inc-live
      │                             Action: check provider
      │
      └─► [No notification]    ──► Check health.aws.amazon.com
                                    Check "Sorrel / api" & "Sorrel / web"
                                    Read service logs (e.g. msg="dns")
                                    Action: read logs
```

### 7.1 Common scenarios and actions

| Scenario | Primary Signal | Immediate First Move | Escalation Path |
|---|---|---|---|
| Notification posted in `#aws-health` for `ap-northeast-1` | Cloud provider alert in `#aws-health`; regional error rates climbing on `api` | `check provider` | Confirm provider status. If P1 impact persists past 15 min, IC takes over. If traffic shift is considered, IC convenes owners (Aiko, Ravi, Mei, Tom). |
| Sudden connection timeouts in one region; `#aws-health` empty | `api-region` alert fires; `ap-northeast-1` clean, `us-east-1` 5xx rate > 20% | `read logs` | Search `service=api msg="dns" region=us-east-1` or connection pool exhaustion in `sorrel-prod-*`. Verify if issue is aws or internal configuration. |
| Single node health-check failure | `web-node-restart` fires twice in 30 minutes; sibling nodes healthy | `read logs` | Examine `service=web node=<node>` for OOM or disk errors. Load balancer will drain node. Do not page owner unless memory leak spreads to all nodes. |
| Approaching regional VPC or instance limits during scaling | Autoscaling capacity warnings in platform metrics | `no action` (if off-hours and non-impacting) / Ticket | File a ticket for working hours. Coordinate with Kenji and Sara; limit increase approval routed through Ravi. |

### 7.2 Log search patterns for aws infrastructure events

Run searches against index `sorrel-prod-*`, narrowing the timeframe to the immediate window of degradation:

- **Regional network or DNS lookup failures:**
  ```text
  service=api msg="dns" region=us-east-1
  ```
- **Connection timeouts from node pools:**
  ```text
  service=api msg="pool exhausted"
  ```
- **Compute instance memory or disk depletion:**
  ```text
  service=web msg="oom"
  ```
  ```text
  service=web msg="render timeout"
  ```
- **Regional payments failures:**
  ```text
  service=payments outcome=failed region=ap-northeast-1
  ```

---

## 8. Summary of team responsibilities

- **Platform team (Kenji Sato, Sara):** Maintains aws infrastructure configurations, VPC networking, `#aws-health` alerting pipelines, base operating environments, and monitoring pipelines.
- **api owner (Ravi):** Decides on database failover, data consistency safeguards, core backend topology, and approves all aws billing changes and quota limit increases.
- **web owner (Aiko):** Manages front-end compute tier and Cloudflare CDN origin configuration during cross-region routing shifts.
- **payments owner (Mei):** Oversees checkout flow integrity, Stripe webhook processing across regions, and payment provider credentials.
- **notifier owner (Tom):** Oversees background queues, worker pools, and external delivery vendor constraints across all active regions.
- **Support lead (Hana):** Handles external communication and support ticket tracking when provider disruptions produce customer-facing impact.
- **On-call rotation:** Triages incoming alerts according to the On-Call Handbook, checks `#aws-health` on regional faults, acts as first responder, and escalates to service owners and the incident commander when regional operational boundaries are exceeded.
