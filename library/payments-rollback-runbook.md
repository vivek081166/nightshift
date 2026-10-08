# Payments rollback runbook

Last updated: 2024-03-11
Author: Mei (payments)
Applies to: payments, all regions

Use this when a payments deploy has gone bad and you need to put the previous version back. It is written for the on-call engineer at night, so every step is spelled out. If you have done this before, the short version is at the bottom.

## Before you start

- Make sure it really is the deploy. Open the board "Sorrel / payments" and check that checkout failures or our own latency went up after the last deploy went out, not before. If charge attempts are timing out while our own latency is normal, the card provider is the problem, and rolling back will not help.
- Check that money has not already moved wrongly. If refunds or charges are being counted twice, stop here and page Mei. A rollback does not reverse a charge or a refund.
- Open a thread in `#inc-live` if there is not one already, and write that you are about to roll back payments.

## Find the deploy to go back to

1. On your laptop, run:

   ```
   dtool history sorrel/payments --last 5
   ```

2. The newest deploy is at the top. Note its id (for example `d-3920`) and the id of the deploy just below it (for example `d-3917`). The one below is the one you are going back to.
3. Check the age of the newest deploy. If it went out more than a day ago, it is probably not the cause. Read the logs first.

## Roll back

1. Run the revert, pointing at the deploy you are going back to:

   ```
   dtool revert sorrel/payments --to d-3917 --drain-checkouts
   ```

2. `--drain-checkouts` is required for payments. It tells the nodes to finish the checkouts already in progress before they switch. Without it, customers in the middle of paying get an error page and some of them pay twice when they retry. The tool refuses to revert payments without it, but type it anyway so you remember why it is there.
3. dtool asks you to confirm with the deploy id. Type it.
4. The revert takes about five minutes. dtool prints each node as it switches: `payments-apne1-01 drained, switched to d-3917`.
5. If dtool prints `lock held by another job`, someone else's deploy is running in the project. Wait for it to finish, or ask in `#deploys` who is running it. Do not force the lock.

## Check that it worked

1. Watch "Sorrel / payments": checkout success should return to where it was before the bad deploy within ten minutes.
2. Run `dtool history sorrel/payments --last 3`. The top line should now say `revert to d-3917`.
3. Write in the incident thread: the bad deploy id, the deploy you went back to, the time the revert finished, and what the board shows now.

## Region notes

- A revert always runs in all three regions (ap-northeast, us-east, eu-west). dtool does them one region at a time, ap-northeast first, because it carries the most checkout traffic in the Japan evening.
- If only one region is failing and the other two are clean, it is usually not the deploy. Check the region's network and the card provider first, then read the logs for that region.
- During the weekly payout job (Sunday 23:00 JST, about forty minutes) dtool waits for the payout job to finish before it switches the last node in each region. A revert started at 23:10 on a Sunday can take up to 35 minutes. That is expected. Do not cancel it.

## Common dtool messages

| Message | What it means | What to do |
|---|---|---|
| `lock held by another job` | Another deploy or revert is running in the project. | Wait, or ask in `#deploys`. Never force the lock. |
| `--drain-checkouts required for sorrel/payments` | You left the flag off. | Run the command again with the flag. |
| `d-XXXX not in last 20` | The deploy you asked for is too old to revert to. | You are going back too far. Stop and talk to the payments team. |
| `drain timeout on payments-useast1-03` | A node had a checkout that did not finish within 90 seconds. | dtool switches it anyway. Note the node in the thread; Mei's team checks those checkouts in the morning. |
| `confirmation mismatch` | The id you typed at the prompt is not the one in the command. | Start again. |

## Who to tell

- The incident thread in `#inc-live`, every time, with both deploy ids.
- `#deploys`, one line: "reverting sorrel/payments to d-XXXX", so nobody starts a deploy while the revert holds the lock.
- Mei, in the morning, or by page if the revert did not help or money has moved wrongly.
- Support (Hana's team), if customers saw errors at checkout, so they can answer tickets with the right times.

## The morning after

- Leave a note for Mei with both deploy ids and the time of the revert. She decides whether the bad deploy gets fixed and redeployed or dropped.
- If any node printed `drain timeout`, list those nodes in the note too.
- Do not redeploy the bad version yourself, even if you think you know what was wrong.

## If it did not help

- If checkout failures are still high fifteen minutes after the revert finished, the deploy was not the cause. Do not revert again to an older deploy. Read the logs and page Mei.
- Going back more than one deploy: talk to the payments team first. Migrations are only guaranteed to work with the previous deploy.

## Things that are not a rollback

- Turning off a feature flag. That is Mei's call.
- Restarting the nodes. That does not change the version and usually hides the problem for an hour.
- Changing anything in the card provider's dashboard. Never during an incident.

## Short version

```
dtool history sorrel/payments --last 5
dtool revert sorrel/payments --to <previous deploy id> --drain-checkouts
```

Confirm with the id, wait about five minutes, watch "Sorrel / payments", write both ids in the thread.

## History of this page

- 2023-07-02: first version, after the July checkout incident.
- 2023-11-20: added `--drain-checkouts` after customers were charged twice during a revert.
- 2024-03-11: dtool moved to version 4; `dtool rollback` was renamed `dtool revert`. Updated the commands.
