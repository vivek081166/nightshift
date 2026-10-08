# Postmortem: partner API certificate expired

Date: 2025-04-14  
Owner: Ravi (api)  
Reviewers: Kenji Sato, Sara, Hana  

## Summary

On Monday, 2025-04-14 at 09:00 JST, the TLS certificate covering the endpoint hostname used by external integrations (`partner-api.sorrel.app`) expired. As a result, outside systems connecting to api to manage bookings and schedule synchronization immediately failed TLS negotiation with strict certificate verification errors. 

The incident lasted 47 minutes, concluding at 09:47 JST when Ravi completed a manual certificate renewal, updated the edge binding, and confirmed clean TLS handshakes across all edge points.

Automated renewal had been attempting to execute for thirty days prior to expiry but consistently failed because the automated ACME DNS-01 validation challenge record was configured in a legacy route zone that was decommissioned during cloud provider zone consolidation late last year. In addition, the pre-expiry alerts configured to fire fourteen days before certificate expiration routed solely to an unmonitored administrative distribution list rather than paging on-call or alerting active operations channels.

A total of three integration partners were impacted during the window. Regular consumer web traffic and direct browser booking flows on web were unaffected, as consumer web domains use separate certificates managed via cloudflare.

## Impact

- **Customer impact:** Consumer-facing web booking flows remained available. However, three external booking partners (representing external widgets and external calendar sync aggregators) experienced connection failures when calling api endpoints.
- **Duration:** 47 minutes (09:00 JST to 09:47 JST).
- **Service availability:** The partner API endpoint rejected 100% of incoming partner TLS handshakes during the 47-minute window. Internal service-to-service traffic was unaffected.
- **Money and data impact:** No data corruption occurred. No unauthorized access took place. A queue of booking updates was held by partner client systems and caught up upon restoration. No direct transaction financial loss was recorded, though partner booking actions were delayed for the duration.

## Background & Architecture

The api service serves both Sorrel's internal client applications (web and mobile backends) and external integration partners. External partner integrations access api via dedicated hostnames managed through cloudflare edge termination and aws application load balancers across ap-northeast-1, us-east-1, and eu-west-1.

Certificates on core endpoints renew automatically thirty days prior to expiration. Standard verification relies on automated DNS-01 challenge validation records managed via aws Route 53. If automated renewal fails to complete, alert rules are designed to notify engineering fourteen days prior to certificate expiration to allow manual remediation before expiry occurs.

## Incident Timeline (all times in JST)

| Time | Description |
|---|---|
| **09:00** | The TLS certificate on `partner-api.sorrel.app` reaches its validity deadline and expires. Systems belonging to integration partners immediately begin rejecting TLS handshakes with certificate expiry errors (`certificate has expired`). |
| **09:05** | Partner inbound traffic metrics drop sharply on Board "Sorrel / api" under the Partner traffic panel. |
| **09:08** | Hana (support lead) flags in `#inc-live` that two enterprise booking integration partners have raised urgent tickets reporting immediate TLS handshake aborts when attempting to contact the partner API. |
| **09:10** | Sara (primary on-call) acknowledges the issue and opens an incident thread in `#inc-live`. Sara confirms via command-line TLS handshake tools that `partner-api.sorrel.app` is presenting an expired certificate as of 09:00 JST. |
| **09:12** | In accordance with the On-Call Handbook (Section 7.13), Sara recognizes that on-call engineers lack permissions to generate and bind infrastructure edge certificates manually. Sara pages Ravi (service owner for api). |
| **09:15** | Ravi acknowledges the page and joins `#inc-live`. |
| **09:18** | Ravi verifies the renewal audit logs and discovers that automated renewal attempts have been failing silently since 2025-03-15 due to failed DNS challenge verification. |
| **09:22** | Ravi determines that the DNS TXT record for the ACME validation challenge exists in a deprecated aws Route 53 hosted zone rather than the active authoritative zone. |
| **09:28** | Ravi updates the authoritative DNS zone with the required validation challenge record and initiates manual certificate re-issuance. |
| **09:37** | The newly issued certificate is validated and provisioned in aws Certificate Manager. Ravi begins deployment and binding of the updated certificate across the load balancer endpoints. |
| **09:43** | Deployment completes across all active regions (ap-northeast-1, us-east-1, eu-west-1). Ravi and Sara verify clean handshakes returning valid certificate chains expiring in 90 days. |
| **09:47** | Partner traffic panel on the api dashboard shows re-established connections and incoming request volumes returning to baseline. Hana verifies with affected partners that client synchronization queues are successfully draining without errors. Incident stood down. |

## Root Cause Analysis

Two independent systemic failures led directly to this customer-facing outage:

### 1. DNS Challenge Record Misconfiguration

Automated certificate lifecycle management requires an automated DNS-01 verification response to validate domain control prior to issuance. Thirty days prior to expiration (on 2025-03-15), the certificate automation pipeline attempted renewal. 

However, during a previous DNS refactoring project, ownership of the relevant apex and subdomain records was migrated to a consolidated hosted zone in aws. The automated verification hook maintained an obsolete hosted zone ID in its configuration. When the renewal process wrote validation TXT records, they were committed to an orphaned, inactive zone that public authoritative nameservers no longer referenced. Consequently, public validation resolvers timed out, and certificate generation repeatedly stalled.

### 2. Failure of Expiry Warning Routing

Under standard operational policy (Handbook Section 7.13), certificates that fail auto-renewal trigger warning alerts two weeks ahead of the expiration date. 

Investigation revealed that these specific two-week advance warning alerts were configured to deliver notifications via an email distribution list (`tls-admin@sorrel.app`) that was established during initial company infrastructure setup. This distribution list had no active subscribers and was neither routed to an active chat channel nor connected to the on-call paging tool. Consequently, automated daily warning notifications failed to reach any engineer between 2025-03-31 and 2025-04-14.

## What Went Well

- **Rapid escalation to owner:** The on-call engineer correctly identified that certificate renewal requires owner permissions and paged Ravi immediately (within 12 minutes of the initial break), avoiding wasted time attempting rollbacks or localized restarts.
- **Clear diagnosis:** Once paged, the root issue (expired certificate) was immediately confirmed using direct TLS probe tools, allowing efforts to focus entirely on manual validation and provisioning.
- **Fast partner coordination:** Hana quickly established communication with partner contacts to confirm when connections cleared, allowing accurate validation of the fix.

## What Went Badly

- **Silent failure for 30 days:** Automated certificate renewal was broken for an entire month without anyone on the platform or api teams being aware.
- **Notification dead ends:** Two full weeks of automated pre-expiry alert warnings fired into an abandoned mailbox without paging anyone or notifying `#platform`.
- **Lack of active monitoring on certificate validity dates:** Metrics monitoring tracked operational response codes and partner limits, but there was no synthetic blackbox check alerting in `#inc-live` or via the paging tool on certificate days-to-expiry for partner endpoints.

## Where We Got Lucky

- **Limited partner count:** Only three partner systems were actively integrated and querying the endpoint during this specific early morning window, which contained the scope of third-party operational impact.
- **Consumer core separated:** The primary customer web application (`sorrel.app`) terminates TLS via cloudflare edge certificates, which were on a separate renewal cycle and unaffected by the internal DNS zone discrepancy.

## Action Items

| Action Item | Type | Owner | Target Date |
|---|---|---|---|
| Re-route all TLS certificate expiry warnings (30-day and 14-day) to `#platform` and configure the 14-day threshold to page the platform team escalation schedule. | Prevent | Sara | 2025-04-16 |
| Correct the automated DNS-01 validation hook to target the active authoritative aws Route 53 zone ID. | Prevent | Ravi | 2025-04-16 |
| Implement an external synthetic blackbox probe on all external hostnames that exposes certificate expiration days as a metric and pages on-call if any cert has < 7 days remaining. | Detect | Kenji Sato | 2025-04-21 |
| Audit all legacy infrastructure distribution mailboxes in cloud services and redirect or decommission dead notification endpoints. | Prevent | Sara | 2025-04-25 |
| Document partner endpoint certificate renewal and manual emergency re-issuance procedures in the api runbook. | Mitigate | Daniel | 2025-04-28 |
