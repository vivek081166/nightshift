Source: scan-twilio-maintenance-2025.pdf · tag 52e64b63 · made 2026-10-09

**Scheduled maintenance: Messaging API, Tokyo region**

twilio · Maintenance notice · Sent 2025-02-04

| Reference | MNT-58213 |
| :--- | :--- |
| **Window (JST)** | 2025-02-18 02:00 to 04:00 JST |
| **Window (UTC)** | 2025-02-17 17:00 to 19:00 UTC |
| **Action required** | None |

We will carry out planned maintenance on the Messaging API in our Tokyo region. During the window, SMS sends may be delayed by up to 10 minutes. Messages will be queued, not dropped. Delivery receipts may arrive up to 30 minutes late.

### Affected products

| Product | Expected impact |
| :--- | :--- |
| Messaging API: SMS to Japanese numbers | Sends delayed by up to 10 minutes |
| Delivery receipts (status callbacks) | Up to 30 minutes late |
| One-time sign-in codes sent as SMS | Delayed by up to 10 minutes |
| Voice | Not affected |

If you have questions about this maintenance, reply to this notice and quote reference MNT-58213.

*notifier deploy freeze booked for this window. Tom 2/5*