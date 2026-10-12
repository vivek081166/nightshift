# notifier: things we learned the hard way

Last updated: 2026-03-09  
Owner: Tom (notifier)  

## Maintenance

Tom keeps this page for the notifier service. The on-call rotation uses it when queue depth or delivery alerts fire for email and SMS.

## Sending-domain switch and the suppression list

After the sending-domain switch on 2026-02-24, sendgrid's suppression list picked up 2,312 addresses from soft bounces during the switch, and sendgrid stopped sending to them. Yuki checked they were valid and removed them from the suppression list on 2026-02-26.

When you see drops on known good customer addresses after domain work:
- check provider before assuming the application dropped them silently.
- check the suppression list directly in sendgrid to see if addresses were added during cutovers.
- read logs in sorrel-prod-* to confirm whether the worker received an acceptance or an outright bounce from the provider.
- if an address is suppressed on their side, notifier will not attempt redelivery on its own.

## Nightly reminder batch volume

The nightly reminder batch (02:00 to 04:00 JST) regularly pushes queue depth past 1,000; check delivered per minute before treating it as a stall.

During this window, clinics, salons, and tutors have their next-day slots queued all at once. The backlog is expected behavior rather than a broken consumer:
- do not page owner merely because the backlog crosses four digits between 02:00 and 04:00 JST.
- open the metrics tool and check delivered per minute across the workers.
- if delivered per minute remains steady and workers are draining messages, choose no action and let the batch clear.
- if delivered per minute drops to zero while the queue sits above 1,000, read logs to see if workers are stuck or encountering errors.

## Queue separation for confirmations and reminders

Email confirmations and SMS reminders use separate queues.

Because these channels and message types do not share a single pipeline, backpressure in one does not directly block the other:
- an incident involving email delivery does not imply SMS traffic is halted.
- when email confirmations back up during daytime booking spikes, SMS reminders continue moving through their own queue.
- check provider status for both sendgrid and twilio separately when triaging broader notification delays.
- read logs for the specific worker group tied to the affected queue rather than treating the service as a single pipe.

## Reminder deduplication keys

Every reminder carries a dedupe key, reminder:<booking id>:<date>; notifier drops a message whose key it has seen in the last 24 hours.

This safeguards recipients from duplicate alerts when upstream schedulers resend booking batches or when retries occur:
- when api or batch jobs re-enqueue the same reminder run, notifier drops a message whose key it has seen in the last 24 hours without raising an error.
- if a business reports that a customer did not receive a second reminder after an update on the same day, read logs to inspect whether the dedupe key reminder:<booking id>:<date> was already recorded.
- if duplicate sends are suspected, check the logs for this key pattern to see if the drop logic executed as intended.
- do not alter dedupe keys manually during an incident without consulting Tom or Yuki.

## On-call summary

When notifier triggers an alert, determine which queue is affected before taking any disruptive step. If the nightly reminder batch is running between 02:00 and 04:00 JST, check delivered per minute in the metrics tool before assuming the worker pool has failed. If delivery stops entirely across third-party endpoints, check provider dashboards for sendgrid and twilio, then read logs to verify worker state.
