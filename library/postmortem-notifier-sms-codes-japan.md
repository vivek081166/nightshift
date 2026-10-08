# Postmortem: SMS sign-in codes delayed in Japan

Date: 2024-04-08  
Owner: Tom (notifier)  
Severity: P2  
Incident Channel: `#inc-live` (thread: `20240408-notifier-sms-delay`)

---

## 1. Summary

On Monday morning, 2024-04-08, between 07:44 JST and 08:56 JST (total duration: 1 hour 12 minutes), customers attempting to sign in to Sorrel via SMS verification codes experienced significant delays. twilio reported carrier delays for Japanese mobile numbers; sign-in codes arrived 5 to 20 minutes late instead of the typical sub-second delivery window.

Because one-time sign-in codes expire after 10 minutes, codes delayed beyond that threshold failed validation, requiring affected users to request a fresh code or use an alternative method. The web sign-in interface offers an email verification option as a fallback, which functioned without issue throughout the incident. During the 1-hour 12-minute window, 1,930 customers signed in with the email fallback.

No change on our side helped; the on-call engineer confirmed the provider incident and wrote it down. Delivery latency returned to baseline levels once the carrier routing problem cleared on the vendor side.

---

## 2. Impact

- **Customer impact**: Customers attempting to log in to their accounts via SMS one-time passcodes experienced delivery latencies between 5 and 20 minutes. A substantial portion of codes delivered after 10 minutes were expired upon receipt. Customers already logged in to browser sessions or native mobile applications were unaffected. Booking flows, checkout, and email confirmations operated normally.
- **Email fallback usage**: 1,930 customers signed in with the email fallback during the window.
- **Service impact**: `notifier` queue depth showed a modest elevation due to retry handling, but email delivery via sendgrid and core background processing remained fully operational. `api`, `web`, and `payments` were healthy throughout the window.
- **Financial impact**: None. No payment transactions failed, and no duplicate charges occurred.
- **Data impact**: None. No customer data was exposed or lost.

---

## 3. Timeline (all times in JST)

| Time | Who | Event |
|---|---|---|
| 07:40 | — | Morning traffic begins ramping up across Japan (`ap-northeast-1`), with users signing in to book services before work. |
| 07:44 | — | `notifier` board shows SMS delivery latency climbing sharply for `+81` destinations. Carrier handoffs begin taking upwards of 5 minutes. |
| 07:51 | Support | Support team notes incoming chats from users stating SMS sign-in codes are not arriving. |
| 07:53 | Alert | An alert fires for elevated SMS delivery failures/delays on Japanese destinations. |
| 07:55 | Sara | Sara acknowledges the page and begins triage. |
| 07:56 | Sara | Sara opens an incident thread in `#inc-live`, classifying the event as P2 (sign-in degraded for SMS users in Japan, but email fallback remains operational and core platform is up). |
| 07:58 | Sara | Sara inspects the "Sorrel / notifier" board. Delivery outcomes panel shows messages accepted by vendor, but carrier delivery receipts are severely lagging. Oldest message age in `notifier` remains within limits; queue workers are healthy. |
| 08:01 | Sara | Checks deploy history. `notifier` was last deployed two days prior (`d-1044` by Yuki); `web` was deployed on Friday (`d-1039` by Priya). No recent code or infrastructure changes. |
| 08:03 | Sara | Sara checks outside provider status at status.twilio.com. twilio has posted an active incident regarding carrier delays for Japanese mobile numbers (`+81`). |
| 08:05 | Sara | Sara posts twilio status link and provider message into `#inc-live`. Because twilio accepted the payloads but carriers delayed them, no rollback or code change on our side would resolve the issue. Sara writes down findings and monitors. |
| 08:12 | Hana | Support lead Hana joins `#inc-live` and confirms support agents are directing customers contacting helpdesk to use the email sign-in fallback. |
| 08:20 | Tom | Service owner Tom checks the thread. Agrees with the assessment: twilio account limits and sender numbers are unaffected; problem is purely upstream carrier transport in Japan. |
| 08:35 | Sara | Provides 30-minute status update in `#inc-live`: twilio upstream mitigation in progress; 1,140 users have successfully used the email fallback since 07:44. |
| 08:52 | twilio | status.twilio.com updates to report that downstream carrier issues in Japan have resolved and message backlogs are clearing. |
| 08:56 | Sara | "Sorrel / notifier" board shows SMS delivery receipts back under 3 seconds. Test sign-in SMS codes arrive within 2 seconds. Total incident duration: 1 hour 12 minutes. |
| 09:05 | Sara | Error rates and transit times stable. Incident declared resolved in `#inc-live`. Final tally shows 1,930 customers signed in with the email fallback during the window. |
| 09:12 | Sara | Sara enters the required line in the on-call log and closes shift tasks. |

---

## 4. Technical Analysis

### 4.1 System architecture for authentication

When a user initiates authentication on `web` via their mobile phone number:
1. `web` sends a POST request to `api` (`/v1/auth/otp/request`).
2. `api` validates the user record, generates a cryptographically random numeric code, hashes and stores the code in the shared cache with a 10-minute time-to-live (TTL), and publishes a dispatch event to the `notifier` message queue.
3. A `notifier` worker node in `ap-northeast-1` pulls the event from the queue, populates the localized SMS template, and submits an outbound SMS dispatch request to twilio via their REST API.
4. twilio acknowledges HTTP 201/accepted, enqueues the SMS across its aggregator networks, and hands it off to domestic telecommunications carriers in Japan (NTT Docomo, KDDI, SoftBank, Rakuten Mobile).
5. Upon delivery to the handset, twilio receives carrier acknowledgments and asynchronously delivers a delivery receipt webhook back to `notifier`.

```
[Browser] 
   | (1. Request OTP)
   v
 [web] 
   | (2. Create token & store in cache)
   v
 [api] 
   | (3. Enqueue notification)
   v
[notifier queue]
   | (4. Pull message)
   v
[notifier worker]
   | (5. POST /Messages)
   v
[twilio API] --- (carrier delays: 5-20m) ---> [Japan Mobile Carriers] ---> [User Handset]
```

At the same time, the `web` authentication screen provides an alternative link: "Sign in with email instead". When selected, the OTP generation route sends an email via `notifier` and sendgrid. Email delivery was operating normally throughout this period with a p95 delivery time under 4 seconds.

### 4.2 Failure progression

Starting around 07:44 JST, mobile network aggregators and carriers in Japan experienced congestion or queuing on SMS terminations. While twilio's REST API continued to accept payloads from our worker nodes with low response latencies (p95 < 180 ms), the physical transit between the carrier gateways and mobile handsets stretched from nominal (< 5 seconds) to between 5 and 20 minutes.

Because the verification tokens generated by `api` have a strict 10-minute TTL:
- Any message delayed between 5 and 10 minutes arrived while the token was still valid, but users frequently had abandoned the screen or requested a duplicate code, invalidating earlier codes.
- Any message delayed over 10 minutes arrived dead on arrival, triggering an "expired verification code" error when submitted.

### 4.3 Why our actions were non-interventional

During triage, Sara evaluated the five standard on-call moves:
- **roll back**: `notifier` and `web` had no deploys within the last 48 hours. The failure was external carrier transport. Rolling back would not alter vendor routing.
- **read logs**: Checked to verify `notifier` workers were not seeing local DNS, process, or queue exhaustion issues. Logs confirmed steady, clean HTTP 201 responses from the vendor API with zero template or worker exceptions.
- **check provider**: The alert pointed toward SMS vendor degradation. Checking status.twilio.com immediately confirmed an active carrier incident for Japanese numbers (`+81`).
- **page owner**: No money moved wrongly, no customer data was exposed or deleted, and no contract or quota decisions needed immediate executive authorization. Tom was available in working hours, but did not need an emergency wake-up page outside working hours.
- **no action**: The incident was active and degraded, requiring observation, support alignment, and documentation, so it was not a quiet ignore-and-close.

Sara confirmed the provider incident, posted the status into `#inc-live`, coordinated awareness with support, and maintained operational monitoring.

---

## 5. What Went Well

- **Fallback architecture**: The platform's existing dual-channel authentication design (offering email OTP alongside SMS OTP) prevented a full sign-in outage. 1,930 customers used the fallback to access their accounts without waiting for the carrier queues to drain.
- **Runbook clarity and provider visibility**: The on-call engineer correctly identified that twilio was the constraint by following the triage sequence and checking status.twilio.com, avoiding unnecessary code rollbacks or infrastructure restarts.
- **Cross-functional support coordination**: Hana and the support team aligned quickly with `#inc-live`, providing clear guidance to incoming customer inquiries and steering users toward the email sign-in path.

---

## 6. What Went Badly

- **User discovery of the email fallback**: Although the email option was present on the sign-in form, it was rendered as a small secondary link below the primary SMS phone number input. Many users did not notice it until contacting support or refreshing multiple times.
- **Token expiration friction**: Users whose SMS arrived at minute 11 were frustrated by expired code errors without clear in-app context explaining that mobile networks were delayed.

---

## 7. Where We Got Lucky

- **Timing of carrier recovery**: The carrier delay cleared before peak business opening hours (09:00–12:00 JST), when salon owners and clinic managers log into their business dashboards on `web` to manage day calendars.
- **Email delivery health**: sendgrid experienced zero delivery degradation during this period. Had email also experienced vendor delays, sign-in would have been completely blocked.

---

## 8. Action Items

| Item | Description | Owner | Target Date | Status |
|---|---|---|---|---|
| AI-2024-04-01 | Add a prominent line to the sign-in page informing customers that the email sign-in option exists, making the fallback clearer during transit delays. | Aiko (web) | 2024-04-08 | Done |
| AI-2024-04-02 | Review client-side messaging when an OTP code expires, advising the user to try the email alternative if SMS delivery is sluggish. | Priya (web) | 2024-04-18 | Open |
| AI-2024-04-03 | Add an automated synthetic alert check that correlates twilio status RSS updates directly to the `notifier` Slack notifications. | Yuki (notifier) | 2024-04-25 | Open |

---

## 9. Appendix: On-Call Log Entry

```
2024-04-08 07:55 JST | notifier | P2 | check provider | twilio reporting carrier delays for +81 numbers; confirmed status page and monitored fallback usage
