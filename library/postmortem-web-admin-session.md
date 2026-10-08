# Postmortem: admin tool session left open on a shared laptop

Date: 2025-02-17  
Owner: Aiko (web)  
Participants: Aiko (web owner), Hana (support lead), Kenji Sato (platform lead), Sara (platform engineer)

---

## 1. Summary

On the morning of Tuesday, 2025-02-11, a routine internal security review identified an active administrative session on a physical support laptop in the Tokyo office. The laptop had remained unlocked and signed in to the Sorrel internal admin tool throughout the previous night (approximately 13 hours without user presence).

The admin tool, served by `web`, provides customer support staff with account lookup capabilities, confirmation resend actions, and dual-approval deletion workflows. Because web stores session state in a shared cache, an authenticated session on an unattended terminal represents an exposure vector for customer account data.

Following discovery, the session was invalidated immediately. An exhaustive audit query across `sorrel-prod-*` logs and the `api` audit log verified that zero account modifications, record views, resends, or deletions occurred over the lifetime of the unattended window. No customer data was altered or improperly accessed. 

Remediation was completed within the same week: the idle session timeout for administrative routes on `web` was lowered from 12 hours to 2 hours, and Hana updated the operational and physical security guidelines governing shared support hardware.

---

## 2. Impact

- **Customer impact**: None. No customer records were modified, deleted, or viewed outside normal business hours.
- **Data exposure**: None. Audit queries confirmed that no HTTP requests targeted `/admin/*` routes from the session identifier during the unattended window.
- **Financial impact**: None.
- **Service availability**: All services (`web`, `api`, `payments`, `notifier`) remained fully operational.

---

## 3. Incident Context and Background

### 3.1 The Admin Tool Architecture
The admin tool is rendered server-side by `web` (six nodes per region behind the regional load balancer in `ap-northeast`, `us-east`, and `eu-west`). It is restricted to authenticated support and operations personnel. While `web` maintains no persistent customer database of its own, it calls `api` to display user records, business configuration, and calendar slots.

Crucial operations within the admin tool include:
- Looking up business and end-customer accounts.
- Resending booking confirmations via `notifier`.
- Submitting account deletion requests, which require an explicit second approval from another authorized staff member before `api` processes the record purge.

Because deletion or mass alteration of accounts can only be restored from backups by service owners (section 5.1 of the handbook), physical access to an authenticated admin interface poses an elevated risk to tenant state.

### 3.2 Pre-incident Session Settings
Historically, sessions across `web` were managed with uniform configuration:
- Session data resided in the shared cache.
- Absolute session lifetime: 24 hours.
- Idle timeout: 12 hours.

The 12-hour idle timeout had been chosen during early product stages to prevent support agents from being disconnected during long shifts when toggling between helpdesk queues, email support, and phone tickets. However, this allowed a session established at mid-day to persist untouched until the following morning.

---

## 4. Timeline (all times JST)

### Monday, 2025-02-10

- **19:12**: A support team member completed customer ticket triaging on the shared support floor laptop (asset tag `tokyo-sup-04`) and closed the lid without clicking "Sign Out" in the admin tool. The laptop was placed in an open office docking station. The screen lock failed to engage because power management settings were overridden by a local peripheral setting.
- **20:00**: Support floor shifts concluded; office lights and badge access switched to after-hours security mode.
- **20:00 - 08:30**: The laptop remained powered on, docked, and connected to the internal office network segment. The active session cookie remained valid in the `web` session store.

### Tuesday, 2025-02-11

- **08:34**: Sara (platform engineer) conducted a weekly internal credential and active administrative session review, scanning active session tokens against network access points. Sara noted a persistent administrative session originating from a floor workstation that had exhibited zero network activity since 19:12 the previous evening.
- **08:42**: Sara physically inspected workstation `tokyo-sup-04` on the Tokyo support floor, verified that the browser window was open to the admin tool dashboard (`/admin/dashboard`), and confirmed the user was not present.
- **08:45**: Sara alerted Aiko (web owner) and Hana (support lead) in chat.
- **08:48**: Aiko purged the session key directly from the shared session cache, terminating the session. The browser on `tokyo-sup-04` was re-directed to the authentication sign-in screen.
- **09:05**: Aiko and Sara initiated an audit of all inbound requests associated with the expired session identifier (`sess-sup-7801a`).
- **09:40**: Aiko completed log analysis across `sorrel-prod-*` for `service=web` and `service=api`. Result: The last transaction recorded for `sess-sup-7801a` was an account lookup at 19:11:42 JST on 2025-02-10. Between 19:11:43 JST on 2025-02-10 and 08:48:00 JST on 2025-02-11, zero HTTP requests were received by `web` carrying that session cookie.
- **10:15**: Sara checked the `api` audit log stream (`component=audit`). The audit stream confirmed that no changes to bookings, opening hours, customer profiles, or account deletions were written during the night.
- **11:00**: Briefing held with Aiko, Hana, Sara, and Kenji Sato (platform lead). Decision reached to reduce admin idle timeouts on `web` immediately and overhaul the shared-device policies for the support organization.

---

## 5. Investigation and Audit Findings

Following the discovery, the primary concern was confirming whether any unauthorized person in the building or on the network had used the console.

### 5.1 Web Layer Verification
Using the log search tool over index `sorrel-prod-*`, Aiko ran targeted searches across the incident window (`2025-02-10 19:00:00` to `2025-02-11 09:00:00 JST`):

```
service=web route=/admin/* session_id=sess-sup-7801a
```

The output showed:
- Total matching requests between 19:12:00 (Feb 10) and 08:48:00 (Feb 11): `0`.
- Last recorded request: `GET /admin/accounts/acc-88219` at 19:11:42 JST (status 200).
- No POST, PUT, or DELETE requests occurred during the final hour of the agent's shift.

A broader search for admin deletions during the entire 24-hour window:
```
service=web route=/admin/* action=delete
```
This query returned zero results. No deletion requests were submitted, and rule `web-admin-bulk` was never triggered.

### 5.2 API Layer Verification
To ensure no direct internal network calls bypassed web front-ends, Sara reviewed the `api` audit logs:
```
service=api component=audit level=ERROR
```
No audit pipeline errors were present; `api-audit-gap` was green and healthy throughout the period. The audit database logs matched `web` records precisely: zero administrative modifications took place while the office was empty.

The evidence demonstrated conclusively that the laptop sat untouched and the session remained completely idle until invalidated.

---

## 6. Root Causes

Two underlying conditions enabled this incident:

1. **Permissive Inactivity Timeout in Software**:
   The admin tool's session lifetime policy allowed up to 12 hours of total inactivity before expiring session tokens. This threshold was too broad for high-privilege administrative access, failing to account for overnight workstation abandonments.

2. **Inadequate Physical and Hardware Session Controls on Shared Devices**:
   Support staff frequently hand off shared hardware between shift rotations. Station `tokyo-sup-04` had power management rules that prevented standard OS-level sleep/lock triggers when docked to specific external display hardware. Furthermore, team practices relied on manual browser sign-outs rather than mandatory workstation locking upon leaving the desk.

---

## 7. What Went Well

- **Proactive detection**: The open session was spotted during regular internal platform security checks rather than following an incident or external report.
- **Comprehensive audit visibility**: The `api` audit log and `web` access logging made it straightforward to trace every interaction for that specific session token. We were able to prove within an hour that zero customer accounts had been accessed, modified, or deleted.
- **Rapid operational coordination**: Aiko, Hana, and Sara mobilized within minutes to kill the token and verify system state without interrupting standard platform operations.

---

## 8. What Went Badly

- **Overly generous idle windows**: A 12-hour session timeout on an administrative interface was an unnecessary vulnerability that had remained in place without review.
- **Workstation policy gaps**: Shared support laptops were treated with the same local sleep profiles as personal development machines, despite being accessible to multiple staff on the office floor.

---

## 9. Corrective Actions

Following the briefing on February 11, the following remediation actions were tracked and completed:

| Action Item | Owner | Target Date | Status |
|---|---|---|---|
| Lower idle timeout for `/admin/*` sessions on `web` from 12 hours to 2 hours | Aiko (web) | 2025-02-13 | Completed (d-1482 deployed 2025-02-12) |
| Enforce browser-level tab-close / window-unload session termination for admin routes | Priya (web) | 2025-02-18 | Completed |
| Update operational security rules for shared support laptops (mandatory logout, OS lock) | Hana (support) | 2025-02-14 | Completed |
| Audit Tokyo office hardware profiles to enforce 5-minute OS screen lock on all docked laptops | Sara (platform) | 2025-02-14 | Completed |
| Add a dashboard metric tracking active `/admin/*` sessions older than 4 hours | Kenji Sato (platform) | 2025-02-20 | Completed |

---

## 10. Technical Changes Implemented

### 10.1 Web Inactivity Timeout Adjustment
Aiko and Priya updated the session management middleware within `web`. While regular consumer booking sessions retain longer persistence to support normal browsing behaviour, any session bearing the `role=support_admin` capability now enforces:
- Maximum idle time: 120 minutes (2 hours).
- Absolute session lifetime: 8 hours (matching the standard support shift).

If no request is made within 120 minutes, the session is purged from the shared cache, forcing the user back to the primary authentication screen. This was released under deploy `d-1482` on Wednesday afternoon (2025-02-12) following standard review, well outside the Friday deploy freeze and evening quiet hours.

### 10.2 Support Floor Hardware Policy Changes
Hana implemented strict rules for the support team regarding shared machines:
- Shared machines may no longer be left on docks overnight; they must be logged out, powered off, and locked in the secure storage cabinet at the end of the shift.
- Support agents must explicitly log out of the admin tool before stepping away from the desk for breaks.
- Local power settings were centrally locked to force system sleep and require screen password unlock after 5 minutes of peripheral inactivity.

---

## 11. Review and Sign-off

- **Web Owner**: Aiko (2025-02-17)
- **Support Lead**: Hana (2025-02-17)
- **Platform Lead**: Kenji Sato (2025-02-17)
