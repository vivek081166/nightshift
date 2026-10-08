# Secrets manager for on-call

Last updated: 2026-06-22  
Owner: Sara (platform)

This reference document explains how the platform team configures secrets management across Sorrel's infrastructure, what the on-call engineer can and cannot see, and the exact operational steps to take when a production credential is suspected or confirmed of being exposed.

---

## 1. Scope and Core Principles

Sorrel runs four core production services across three active regions (ap-northeast, us-east, eu-west):
- `web` (managed by Aiko)
- `api` (managed by Ravi)
- `payments` (managed by Mei)
- `notifier` (managed by Tom)

All database credentials, third-party integration tokens, cryptographic signing keys, and vendor API tokens are held centrally. 

### Fundamental Rules

1. **Centralized Storage:** Every production credential lives in the secrets manager. No configuration files, environment definitions, container manifests, or deployment repositories store plaintext secrets.
2. **Read-Only Metadata for On-Call:** On-call engineers can see which secrets exist, their names, resource tags, update history, and version metadata, but **never their raw values**. The platform team enforces strict access policies where secret payload values require elevated owner-level permissions.
3. **No Self-Service Rotation:** **Never rotate a production credential yourself; rotation is the credential owner's decision.** A manual secret rotation executed under pressure frequently breaks running application instances, invalidates distributed caching mechanisms, or triggers hard API rejection thresholds across running regional nodes.
4. **Immediate Escalation on Exposure:** If a key appears outside the secrets manager—including in log outputs, support tickets, error dumps, or communication channels—it is treated immediately as an irreversible incident. You must **page the owner of the credential** rather than attempting mitigation alone.

---

## 2. Inventory and Credential Ownership

When managing alerts or triaging issues, identify who owns the credential before initiating any escalation. Owners have direct responsibility for account settings, vendor relations, and executing key rotation procedures.

| Credential Class | Provider / Scope | Used By | Owner | Escalation Target |
|---|---|---|---|---|
| Card processing API keys & webhook signing secrets | stripe | `payments` | Mei | Mei (payments owner) |
| SMS vendor tokens, messaging account credentials | twilio | `notifier` | Tom | Tom (notifier owner) |
| Transactional email vendor keys, template delivery tokens | sendgrid | `notifier` | Tom | Tom (notifier owner) |
| CDN edge credentials, WAF tokens, cache purge keys | cloudflare | `web` | Aiko | Aiko (web owner) |
| Cloud infrastructure IAM keys, storage credentials, DNS records | aws | All services (`web`, `api`, `payments`, `notifier`) | Platform team | Kenji Sato (platform lead) / Sara |
| Relational database connection strings & read replica pools | Internal database instances | `api`, `payments` | Respective service leads | Ravi (`api`) / Mei (`payments`) |

---

## 3. On-Call Access and Verification

During an operational shift, you may need to confirm whether an application failure or connectivity degradation is tied to a missing, stale, or malformed secret path.

### What You Can Check

The platform console allows on-call engineers to inspect secret namespaces:

- **Secret existence:** Verify that the secret key name expected by a service build exists in the regional path (e.g., `sorrel/prod/payments/stripe/api_key`).
- **Last modified timestamp:** Confirm whether an automated sync job or platform deploy updated the secret metadata recently.
- **Version stages:** Check if a `CURRENT` or `PREVIOUS` version stage tag is applied.
- **Associated services:** Confirm which cluster task roles or node profiles are authorized to pull the secret into application memory at boot.

### What You Cannot See

- You cannot decrypt or view the secret string, certificate private key, or token payload.
- You cannot edit, overwrite, delete, or create production secret values.

If an application pod fails to start with an initialization error pointing to a missing secret path or permission denial, verify whether a platform change was scheduled on the change calendar. If no planned work exists, notify the platform team or the specific service owner. Do not attempt to bypass secrets manager checks or provision ad-hoc environment variables.

---

## 4. Handling Credential Exposure Incidents

Per Section 7.5 of the On-Call Handbook, any secret visible outside the secrets manager is considered compromised. Live production credentials exposed to unauthorized eyes cannot be un-seen; therefore, the first move is always to escalate.

### Rule of Action

> **If a key appears in logs, chat or a ticket: do not copy it anywhere else, link to where it appears, and page the owner of the credential.**

### Procedure Step-by-Step

```
[Key Found Outside Secrets Manager]
                │
                ▼
   DO NOT copy, paste, or echo the key anywhere
                │
                ▼
   Capture reference URL / Search query link
                │
                ▼
   Declare P1 in #inc-live (Incident thread)
                │
                ▼
   Page Credential Owner via paging tool
```

#### Step 1: Contain the Spread
- **Never copy the credential text.** Do not copy and paste the string into `#inc-live`, private chats, ticketing tools, or incident tracking documents.
- If the credential was found in a log line via the log search tool (index `sorrel-prod-*`), copy the **direct query URL** or note the exact log timestamp, service tag, and `node` identifier.
- If the credential was posted in a support ticket or chat message, record the message or ticket reference ID.

#### Step 2: Establish the Severity
- A live production credential exposure is classified as **P1** immediately, regardless of whether unusual API traffic has been detected.
- The 5-minute acknowledgement SLA applies.

#### Step 3: Page the Credential Owner
- Navigate to the paging tool.
- Select the escalation path for the owner identified in Section 2:
  - For `stripe` keys: page **Mei**.
  - For `twilio` or `sendgrid` keys: page **Tom**.
  - For `cloudflare` edge keys: page **Aiko**.
  - For `aws` root, IAM, or cross-service operational tokens: page **the platform team** (Kenji Sato / Sara).
- Include the following details in the page dispatch:
  - Incident severity: P1.
  - Affected provider/credential name.
  - The link or location identifier where the leak was observed (do not include the secret itself).
  - Confirmation that the key is exposed and awaiting owner decision.

#### Step 4: Open Incident Thread in `#inc-live`
- Open a dedicated incident thread in `#inc-live`.
- Format your initial message strictly following team standards:
  - State the symptom: live credential observed in external system/logs.
  - Provide the log search link or ticket ID.
  - Note the time in JST.
  - Note that the service owner has been paged via the paging tool.

---

## 5. Why On-Call Engineers Do Not Rotate Credentials

Engineers new to the rotation often ask why they cannot simply click "Rotate Secret" or generate a new token from a provider dashboard during a crisis. The reasons are architectural and operational:

1. **Dependent Deployments:** Many services read secrets into memory during initial node bootstrap. In `web` (autoscaling 6 to 12 nodes across regions) and `api` (8 to 20 nodes across regions), changing a secret in the backend without orchestrating an orderly zero-downtime rolling reload will cause older nodes to reject requests or fail background tasks.
2. **Dual-Key Requirements:** Providers like Stripe and Twilio often require zero-downtime rollover schemes (e.g., configuring secondary API keys, updating webhook signatures, draining queued worker messages). Service owners are trained in the exact operational sequence required to transition running jobs without dropping customer checkout attempts or scheduled appointment reminders.
3. **Database Migration Locks:** Database passwords injected across `api` connection pools require pool draining coordination. A hard rotation will immediately trip `pool exhausted` or `deadlock` conditions, dropping live customer checkout confirmations.
4. **Contractual and Vendor Authority:** Updating tokens on provider dashboards may invalidate active enterprise webhook bindings or trigger automated fraud locks on the vendor side. Only service owners possess the standing authority to coordinate these adjustments.

---

## 6. Common Leak Scenarios and Immediate Responses

Below are four realistic scenarios where on-call engineers may encounter exposed credentials, along with the precise protocol for each.

### Scenario A: Card Provider Key Found in Log Search

- **Observation:** While inspecting `service=payments` logs during a triage session, you notice an unmasked live Stripe key outputted in an unhandled exception trace.
- **What NOT to do:** Do not paste the stack trace or the key into `#inc-live`. Do not attempt to log into the Stripe dashboard to revoke the key.
- **Action:**
  1. Copy the exact permalink to the log query in the log search tool.
  2. Treat as P1 (secret exposure).
  3. Page **Mei** immediately through the paging tool.
  4. Post to `#inc-live`:
     > "P1 opened for secret exposure. Live Stripe key identified in `service=payments` logs. Query link provided to owner. Mei has been paged. On-call standing by."
  5. Wait for Mei to acknowledge and establish a remediation channel. Mei will execute the dual-key rollover and coordinate any necessary code deploy.

### Scenario B: SMS Vendor Token Posted in Support Ticket

- **Observation:** A support escalations ticket reviewed by Hana indicates a partner sent an integration payload containing an active Twilio Auth Token used by Sorrel's notification workers.
- **What NOT to do:** Do not reply in the ticket. Do not copy the token to verify if it works.
- **Action:**
  1. Record the ticket reference number.
  2. Treat as P1.
  3. Page **Tom** via the paging tool.
  4. Post to `#inc-live`:
     > "P1 declared. Production Twilio token exposed in support ticket #[ID]. Tom paged. No credentials copied into chat."
  5. Tom will coordinate with Hana and Twilio to invalidate the compromised token and re-issue credentials.

### Scenario C: Cloudflare API Token Rendered in Admin Tool Error

- **Observation:** An internal admin tool screen used by support reports a render timeout and dumps an internal client configuration containing Cloudflare edge credentials.
- **What NOT to do:** Do not attempt to clear Cloudflare cache or change WAF rules.
- **Action:**
  1. Note the admin URL and session ID.
  2. Treat as P1.
  3. Page **Aiko** via the paging tool.
  4. Post to `#inc-live`:
     > "P1: Cloudflare credential exposed in web admin render failure. Aiko paged. Link shared via secure reference."
  5. Aiko will cycle the edge credentials and determine if the admin tool build needs a rollback or immediate patch.

### Scenario D: AWS Credential Appears in Notifier Worker Output

- **Observation:** A transient queue connectivity error outputs an AWS IAM secret access key in `service=notifier` container stdout.
- **What NOT to do:** Do not attempt to delete the IAM key in the AWS console.
- **Action:**
  1. Capture the log query link showing the container log.
  2. Treat as P1.
  3. Page **Kenji Sato** (platform lead) and **Tom** via the paging tool.
  4. Inform `#inc-live` that a platform credential was logged, linking to the search query without exposing the key.
  5. The platform team will review active CloudTrail access logs, rotate the IAM role or key pair, and deploy updated container definitions.

---

## 7. Post-Exposure Log Cleansing Protocol

Once the credential owner has revoked the exposed secret and deployed new credentials, the raw logs containing the secret must be purged or masked in `sorrel-prod-*`.

- **Do not run manual index deletion scripts:** Deleting indices indiscriminately destroys compliance records and audit trails.
- **Coordinate with the Platform Team:** Kenji Sato and Sara manage log retention policies and index sanitization jobs.
- **Audit Verification:** Ravi will verify that the `api` audit log integrity remained intact during the event window.
- **Postmortem Tracking:** Every P1 credential exposure mandates a postmortem document within 5 working days in the shared "Postmortems" folder. The review meeting will take place the following Thursday, led by the platform team.

---

## 8. Summary Checklist for On-Call Shifts

Before taking over primary on-call:

- [ ] Confirm access to the log search tool (`sorrel-prod-*`) and metrics boards.
- [ ] Ensure the paging tool profile is active on your mobile device.
- [ ] Review the escalation paths for owners:
  - **web:** Aiko
  - **api:** Ravi
  - **payments:** Mei
  - **notifier:** Tom
  - **platform:** Kenji Sato / Sara
- [ ] Remember: **Inspect, link, escalate. Never copy credentials; never rotate credentials yourself.**
