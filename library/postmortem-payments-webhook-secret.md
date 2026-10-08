# Postmortem: stripe webhooks rejected after the signing secret rotation

Date: 2026-03-03  
Owner: Mei (payments)  
Participants: Mei, Leo, Sara, Kenji Sato, Hana

---

## 1. Summary

On 2026-03-03 between 14:12 JST and 14:53 JST, nodes running the `payments` service in the `us-east` region rejected incoming webhooks sent by stripe. The failure followed a planned quarterly rotation of the stripe webhook signing secret conducted by Mei. 

While the updated secret was synchronized successfully to nodes in `ap-northeast` and `eu-west`, an automated configuration propagation step failed silently for the `us-east` cluster. Consequently, the four `payments` nodes in `us-east` continued verifying webhook signatures using the previous signing secret. Because stripe immediately began signing payloads with the newly generated secret, signature verification failed in `us-east`, and the service returned HTTP 400 responses to stripe.

The rejection loop persisted for 41 minutes until the synchronization failure was identified and the correct secret was forced onto the `us-east` nodes. During this window, affected customer bookings created in `us-east` remained in a `payment pending` state instead of transitioning immediately to paid status. 

No money moved wrongly. Customer cards were charged correctly on stripe's side at checkout, no duplicate charges or refunds occurred, and payouts were not involved. stripe retried all rejected webhook deliveries according to its exponential backoff schedule, and every deferred webhook was delivered and processed cleanly once `us-east` recognized the new signing key.

---

## 2. Impact

| Dimension | Assessment |
|---|---|
| **Severity** | P2 (degraded processing in a single region; no data corruption or lost funds) |
| **Duration** | 41 minutes (14:12 JST to 14:53 JST) |
| **Customer bookings** | 218 bookings created in `us-east` remained in `payment pending` for up to 45 minutes |
| **Financial impact** | 0 JPY / 0 USD. Zero incorrect charges, zero dropped payments, zero incorrect refunds |
| **Data integrity** | No data lost; no data cross-contamination. Audit log trails remained intact |
| **Customer reports** | 14 tickets submitted to support regarding delays in confirmation emails |

Customers completing checkout in `us-east` during the window saw a successful checkout submission screen on `web`, but their account pages and booking confirmation emails were delayed. Under normal operation, `payments` verifies the inbound `charge.succeeded` webhook from stripe and calls `api` to mark the appointment as confirmed, which triggers `notifier` to queue confirmation emails and SMS messages. Because the webhooks were rejected at the origin edge in `us-east`, bookings sat in `payment pending` awaiting verification.

---

## 3. Background

The `payments` service runs four nodes behind the load balancer in each of our three active regions: `ap-northeast`, `us-east`, and `eu-west`. When customers book an appointment requiring an upfront deposit or full payment, `payments` communicates directly with stripe to create the charge. 

Once stripe processes the transaction, it issues an asynchronous webhook (`charge.succeeded`, `charge.failed`, `refund.updated`) to our public payments endpoint. Each webhook carries a cryptographic signature in the `Stripe-Signature` header, computed using a shared signing secret. `payments` verifies this signature to guarantee authenticity before parsing the payload and informing `api`.

Per our quarterly security checklist, live API credentials and signing secrets undergo scheduled rotation. The rotation procedure requires:
1. Generating a secondary signing secret in the stripe dashboard.
2. Writing the new secret to the cloud secrets manager across all active regions.
3. Reloading node configuration so the running workers pick up the new secret.
4. Revoking the old signing secret in stripe once all regions verify payloads against the new secret.

---

## 4. Timeline (all times in JST)

| Time | Event |
|---|---|
| 14:00 | Mei begins the scheduled rotation of the stripe webhook signing secret. |
| 14:05 | New signing secret generated in stripe and written to the primary secrets manager vault. |
| 14:08 | Automated deployment script triggers a configuration reload across production regions. |
| 14:10 | Reload succeeds in `ap-northeast` and `eu-west`. In `us-east`, an IAM regional replication timeout causes the configuration hook to abort without raising an alert. |
| 14:12 | Mei promotes the new signing secret to primary in stripe and retires the previous secret. Rejections begin immediately on `us-east` nodes. |
| 14:16 | The metrics board "Sorrel / payments" displays a sharp rise in webhook validation errors and retries in the `us-east` panel. `ap-northeast` and `eu-west` remain completely healthy. |
| 14:22 | On-call engineer (Sara) observes elevated webhook errors on the dashboard and notes a growing number of appointments lingering in `payment pending` in `us-east`. |
| 14:24 | Sara opens an incident thread in `#inc-live`. Sara confirms stripe's status page (`status.stripe.com`) is green with normal operation globally. |
| 14:26 | Sara checks the deploy history for `payments` and notes no code deploys within the last 48 hours. |
| 14:28 | Sara inspects logs using `service=payments outcome=failed region=us-east` and discovers signature verification failures: `msg="webhook signature verification failed" provider=stripe`. |
| 14:31 | Mei joins the thread in `#inc-live`, noting she executed the scheduled credential rotation at 14:12 and suspects a secret propagation issue. |
| 14:35 | Mei and Sara query node configuration status. They confirm all four nodes in `ap-northeast` and `eu-west` hold secret version `v4`, whereas all four nodes in `us-east` remain on version `v3`. |
| 14:42 | Sara and Leo investigate the silent failure of the reload hook in `us-east` and identify an unhandled network error during secret bundle replication. |
| 14:48 | Mei manually forces the update of the secrets manager container in `us-east` and executes a rolling restart of the four `payments` nodes in that region. |
| 14:53 | All four `us-east` nodes complete startup, loading secret version `v4`. Webhook rejections immediately cease. |
| 14:55 | stripe begins automated retries for previously rejected payloads. Inbound delivery rate increases on the `Sorrel / payments` dashboard. |
| 15:18 | All 218 pending webhooks are ingested and processed. `api` marks all corresponding bookings as paid. |
| 15:22 | `notifier` drains the resulting backlog of confirmation emails via sendgrid and SMS reminders via twilio. |
| 15:30 | Support lead (Hana) reports that customer inquiries regarding pending appointments have stopped. Incident declared resolved. |

---

## 5. Technical Root Cause

The immediate failure was caused by a configuration drift between regions during a live credential rotation:

1. **Silent Replication Abort:** The synchronization script used for updating secrets across regions relied on a sequential API push. During the execution for `us-east`, a transient AWS API throttling response caused the local secrets synchronization script to terminate prematurely. Because the exit code was masked by a wrapper script, the tooling reported overall success.
2. **Runtime Memory Caching:** The `payments` service cached the signing secret in memory at process startup. When the rotation occurred, nodes were expected to reload secrets via an in-memory hook triggered by the deployment tool. Because the script failed to update the local regional secret store, the hook loaded the stale secret `v3`.
3. **Immediate Revocation in Provider Console:** The previous secret was revoked in the stripe console immediately after the rotation script returned a nominal zero exit code. Stripe's documentation notes that multiple signing secrets can remain active concurrently. Retiring the older secret immediately prevented `us-east` nodes from falling back to verify signatures against `v3`.

```
                  +-----------------------------------+
                  |      stripe Webhook Dispatch      |
                  +-----------------+-----------------+
                                    |
                    Payload signed with Secret v4
                                    |
            +-----------------------+-----------------------+
            |                                               |
            v                                               v
  +-------------------+                           +-------------------+
  |    ap-northeast   |                           |      us-east      |
  |  Secret: v4 (OK)  |                           | Secret: v3 (STALE)|
  +---------+---------+                           +---------+---------+
            |                                               |
      HTTP 200 OK                                     HTTP 400 Bad
   Booking marked paid                             Signature Verification
                                                            |
                                                   stripe schedules
                                                    retry backoff
```

---

## 6. What Went Well

- **Resilient Webhook Protocol:** Because stripe's webhook delivery architecture treats non-2xx responses as retryable events, zero transaction records were permanently lost. 
- **Rapid Regional Isolation:** The dashboard layout on "Sorrel / payments" enabled the on-call engineer to instantly isolate the failure to `us-east`. Latency, card submission metrics, and charge endpoints in the other two regions remained entirely stable.
- **Log Hygiene:** The log query `service=payments outcome=failed region=us-east` accurately surfaced the signature verification error string within two minutes of opening the investigation, without logging sensitive card or secret material.
- **Zero Financial Discrepancies:** No duplicate charges or payout anomalies occurred. The state machine correctly held booking records in `payment pending` rather than dropping or corrupting them.

---

## 7. What Went Badly

- **Silent Tooling Failure:** The manual rotation script reported that the secret was updated across all regions when the update to `us-east` had in fact timed out.
- **Premature Key Revocation:** The old webhook signing secret was deleted from stripe immediately rather than kept alive in parallel during a soak period.
- **Customer Facing Delays:** 218 users experienced confusing appointment states on the booking portal, with their dashboards stating that payment was still being processed despite their card issuer apps showing a successful charge.
- **Support Burden:** Support received 14 urgent tickets within 30 minutes from salon clients worried their appointment slots were surrendered due to pending payment statuses.

---

## 8. Where We Got Lucky

- **Traffic Window:** The rotation occurred at 14:00 JST, which corresponds to the early morning hours (00:00 EST) in `us-east`. Traffic volume in that region was near its diurnal low, keeping the number of affected webhooks relatively small (218 requests). Had this occurred during the peak customer checkout window (18:00 to 23:00 local time), thousands of checkouts would have hung in `payment pending`.
- **Rapid Owner Availability:** Mei was already online and following the `#inc-live` channel when the webhook rejection metrics began climbing, allowing immediate diagnosis without needing an off-hours paging cycle.

---

## 9. Corrective Fix and Architectural Improvements

To prevent a recurrence of configuration drift during secret rotations, the platform and payments teams implemented structural changes to how secrets are ingested and validated.

### 9.1 Startup Validation and Regional Parity

The `payments` service no longer relies on ad-hoc runtime memory hooks to refresh credentials. Instead:
- The secret is now read directly from the cloud secrets manager at service start-up on every node.
- During boot and periodically during operation, every node runs an internal verification check confirming that all active regions (`ap-northeast`, `us-east`, `eu-west`) report the identical secret version metadata.
- If a node discovers a mismatch between its active signing secret version and the consensus version across regional stores, it raises a metric alarm and logs a descriptive configuration error.

### 9.2 Safe Secret Overlap Window

The operations runbook for rotating outside provider keys has been revised:
- Dual-secret verification: When rotating stripe webhook secrets, both the old secret and the new secret must remain registered in stripe simultaneously for at least 24 hours.
- Signature checking logic in `payments` now attempts verification against the primary secret, and if that fails, checks against the secondary secret before rejecting the request.
- Decommissioning of an old secret is only permitted after dashboards verify zero successful verifications against the old secret for at least two consecutive hours.

---

## 10. Action Items

| Item | Description | Type | Owner | Target Date |
|---|---|---|---|---|
| **ACT-01** | Update `payments` initialization logic to fetch secrets from secrets manager on startup and enforce cross-region version parity. | Fix | Mei / Leo | 2026-03-05 *(Completed)* |
| **ACT-02** | Update rotation script to check regional secrets manager return codes explicitly and fail closed on timeouts. | Prevent | Sara | 2026-03-08 |
| **ACT-03** | Implement dual-signing secret fallback verification in `payments` webhook ingestion path. | Mitigate | Leo | 2026-03-12 |
| **ACT-04** | Add an automated check in the deployment tool verifying configuration hash parity across all running instances in all regions. | Prevent | Kenji Sato | 2026-03-19 |
| **ACT-05** | Update Section 6.1 of the internal documentation regarding stripe key maintenance and rotation procedures. | Docs | Mei | 2026-03-10 |
| **ACT-06** | Create standard support canned responses for customers reporting prolonged `payment pending` statuses. | Process | Hana | 2026-03-09 |
