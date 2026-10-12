# payments: notes for on-call

Last updated: 2026-02-02  
Owner: Mei (payments)  

Mei maintains this operational runbook page for the SRE rotation covering the payments service. Keep these operational notes handy when evaluating issues during shifts across ap-northeast, us-east, and eu-west.

## Duplicate capture on 63 bookings

On 2026-01-14, we ran into an issue where the capture call to stripe timed out from our side. The capture call to stripe was retried after a timeout and both captures went through, leading to duplicate capture on 63 bookings on 2026-01-14. Our team found it in the logs.

Leo added an idempotency key to the capture call on 2026-01-15 to ensure that network timeouts on the provider interface do not cause double execution again. Mei's team refunded the second charge the same day to make sure the affected customer balances were reconciled cleanly.

When you see this on call:
- If double captures or unexpected double line items appear in records, read logs in the log search tool to check if the idempotency key was dropped or bypassed.
- If money moved incorrectly, page owner so Mei's team can review transactions and issue necessary refunds.

## Weekly payout schedule

The weekly payout job runs on Sunday at 23:00 JST and usually takes about 38 minutes. This process settles balances earned by businesses such as salons, clinics, and tutors using Sorrel. 

Because the job handles substantial database read and write volume while contacting external card networks, background load on payments will stay elevated for the entire duration of the run. 

Points to remember regarding payout execution:
- The weekly payout job runs on Sunday at 23:00 JST and usually takes about 38 minutes, so expect resource graphs on the "Sorrel / payments" board to show persistent load during that window.
- The job touches balance ledgers sequentially, meaning brief processing spikes around 23:00 JST are typical behavior.

When you see this on call:
- When payout task timers or elevated queue depths alert close to Sunday midnight JST, check whether the job has exceeded its standard window before treating it as stalled.
- If the job halts halfway through or throws unhandled exceptions during execution, read logs first, and page owner if money moved or payouts stalled halfway through.

## Daily refund batches

Refund batches run daily at 23:30 JST. This automated batch handles customer cancellation refunds and disputed appointment adjustments that have queued up over the previous twenty-four hours.

Key operational characteristics:
- Refund batches run daily at 23:30 JST, briefly competing with other late-evening queue workers in ap-northeast.
- The job aggregates pending return requests and sends them in structured batches directly downstream to stripe.
- Failures inside a batch are isolated so that an error on an individual refund does not abort the remaining executions in the queue.

When you see this on call:
- When queue latency blips occur around 23:30 JST, read logs to confirm that the refund batches run daily at 23:30 JST without dropping database connections.
- If a batch reports unrecoverable transaction corruption, page owner to avoid duplicate accounting entries.

## Provider webhook delivery behavior

Webhooks from the card provider can arrive late, out of order, or more than once; payments is built to handle all three, so a few retries are not an incident. The ingest pipelines store events idempotently and process lifecycle state changes based on event timestamps rather than arrival order.

Network hiccups between stripe edge servers and our cloudflare or aws ingress endpoints regularly cause delayed deliveries or multiple retry deliveries of identical event payloads.

Operational points:
- Webhooks from the card provider can arrive late, out of order, or more than once; payments is built to handle all three, so a few retries are not an incident.
- Deduplication prevents duplicate accounting events when redundant events hit webhooks concurrently.

When you see this on call:
- When webhook retry alerts trigger in low numbers, no action is needed if payloads are acknowledged normally on subsequent attempts.
- If webhooks fail completely across all endpoints, check provider status before assuming our ingest nodes are down.

— Mei
