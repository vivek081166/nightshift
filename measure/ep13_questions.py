"""EP13 measurement, not episode code: builds tickets/questions-ep13.json (the 40 EP12 questions unchanged + 20 steps
+ 10 half), checks every step line is on its page word for word, greps the 127 pages to prove each half question's
missing part is in no page, and runs keyword search's top 5 on every new question (local, free, no model call).

    python3 measure/ep13_questions.py            # write the file, the checks, and runs/ep13/2026-10-12-q-build.json
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import lookup, search

S = lambda step, line, page=None: {"step": step, "line": line, **({"page": page} if page else {})}

STEPS = [
    # ---------------------------------------------------------------- web
    {"id": "st-cdn-purge", "service": "web", "page": "howto-cdn-purge-by-hand",
     "question": "after the web deploy the CDN is still serving the old js bundle. how do i purge it by hand?",
     "truth": [["prefix"], ["purge everything"]], "wrong": [],
     "steps": [
         S("check web origin nodes are healthy first", "Confirm that `web` origin nodes are healthy."),
         S("pick the sorrel.app zone in cloudflare", "Select the zone corresponding to the environment: `sorrel.app` (production)."),
         S("Caching > Configuration > Purge Cache", "From the left navigation menu, open **Caching**, then click on **Configuration**."),
         S("Custom Purge, never Purge Everything", "Click on **Custom Purge** (do not click *Purge Everything*)."),
         S("URL or Prefix mode", "Select the **URL or Prefix** purge mode."),
         S("enter the exact URL prefixes", "Supply the exact URL prefixes requiring eviction."),
         S("Submit Purge", "Click **Submit Purge**."),
         S("a normal purge completes within a minute; check the purge panel", "A normal purge completes within a minute; check its status on the CDN dashboard's purge panel."),
         S("Processing > 3 min: suspect the provider, check cloudflarestatus", "If the purge remains in `Processing` for more than three minutes, suspect a provider-side delay."),
         S("write the purge id in #inc-live", "Write the purge id in the incident thread in `#inc-live`."),
         S("watch metrics at least 10 minutes", "watch the metrics tool for at least ten minutes to verify resolution and ensure origin stability."),
         S("log search for asset load failed", "service=web msg=\"asset load failed\""),
         S("purge did not fix it and deploy < 30 min: roll back web, notify Aiko", "Roll back `web` in the deploy tool to the previous deploy. Notify Aiko."),
     ]},
    {"id": "st-web-rollback", "service": "web", "page": "handbook-5",
     "question": "walk me through rolling back web, the last deploy broke the booking pages",
     "truth": [["roll back to this"]], "wrong": ["shipyard"],
     "steps": [
         S("deploy tool, project sorrel, service web, previous deploy, Roll back to this", "In the deploy tool, project \"sorrel\", service \"web\", choose the previous deploy and press \"Roll back to this\"."),
         S("nodes re-pointed two at a time, CDN to previous asset set, about four minutes", "The tool re-points the nodes to the previous version, two at a time, and re-points the CDN to the previous asset set. It takes about four minutes."),
         S("watch error rate and page load back to pre-deploy level", "Watch error rate and page load on the board until they return to the level before the deploy."),
         S("write the rollback in the incident thread with both deploy ids", "Write the rollback in the incident thread with both deploy ids."),
         S("tell Aiko in the morning, page her if it did not help", "Tell Aiko in the morning, or page her if the rollback did not help."),
     ]},
    {"id": "st-web-blank", "service": "web", "page": "handbook-5",
     "question": "booking pages are coming up blank for customers. what are the first checks on web, step by step?",
     "question_v1": "customers say the booking pages are blank. what are the first things i check on web?", "reworded_why": "v1 top 5 had no handbook-5 (payments-rollback-runbook ranked first); v2 uses the runbook's own 'first checks'",
     "truth": [["deploy"], ["CDN"]], "wrong": [],
     "steps": [
         S("blank pages: usually a front-end change, failed asset upload or assets missing at the CDN", "Blank pages or broken layouts reported by customers: usually a front-end change, a failed asset upload, or assets missing at the CDN."),
         S("open Sorrel / web, find when it started", "Open \"Sorrel / web\" and find when the symptom started."),
         S("compare with web deploy history, note the age of the last deploy", "Compare with the deploy history for web. Note the age of the last deploy."),
         S("all nodes or one, all routes or one, all regions or one", "Check whether the symptom is on all nodes or one node, all routes or one route, all regions or one region."),
         S("check api's board", "Check api's board. If api is unhealthy, web's errors are usually a consequence."),
         S("check the CDN panel: edge or origin", "Check the CDN panel: is the edge serving errors, or is the origin?"),
         S("read service=web logs for the start of the window", "Read `service=web` logs for the start of the window."),
     ]},
    {"id": "st-crawler", "service": "web", "page": "team-web-notes",
     "other_pages": ["handover-2026-09-14", "handover-2026-06-29", "handover-2026-06-15", "handover-2026-06-08",
                     "handover-2026-01-26", "handover-2025-10-13", "handover-2026-04-06", "handbook-7"],
     "question": "a search-engine crawler burst on the public business pages tripped web-traffic. what should i do?",
     "question_v1": "web-traffic alert just fired, looks like a search engine crawler hammering the business pages. what do i do?", "reworded_why": "v1 top 5 was five handovers that log web-traffic alerts, no team-web-notes; v2 uses the note's words 'crawler burst' and 'public business pages'",
     "truth": [["no action"]], "wrong": [],
     "steps": [
         S("crawler bursts are harmless when 5xx and page load stay flat", "Search-engine crawler bursts on public business pages trip web-traffic a few times a month; they are harmless when 5xx and page load stay flat."),
         S("check error rates and latency are unaffected", "check the metrics tool to confirm error rates and response latencies remain unaffected"),
         S("if healthy, no action and log it in the shift notes", "if metrics are healthy, take no action and log it in the shift notes."),
         S("last time: no action, ticket for Aiko about crawler limits", "First move: no action; ticket for Aiko about crawler limits.", "handover-2026-09-14"),
         S("same, in a handover the v2 search does return", "First move: no action; ticket for Aiko about crawler limits.", "handover-2026-06-29"),
     ]},
    {"id": "st-admin-deletions", "service": "web", "page": "handbook-5",
     "other_pages": ["handbook-7", "handbook-3"],
     "question": "lots of customer accounts were deleted through the admin tool in the last hour. what should on-call do?",
     "question_v1": "the admin tool shows a load of customer accounts got deleted in the last hour. what do i do?", "reworded_why": "v1 top 5 had no handbook-5; v2 says 'deleted' and 'on-call' as the runbook's admin-tool line does",
     "truth": [["Aiko"]], "wrong": [],
     "steps": [
         S("unexpected deletions in the admin tool are for Aiko, never fixed by on-call alone", "Any unexpected deletion, mass change or access pattern in the admin tool is a matter for Aiko and is never fixed by the on-call engineer alone, because deleted accounts can only be restored by the owner from backups."),
         S("restores come from backups and are done by the owner", "Restores come from backups and are done by the owner.", "handbook-7"),
         S("whether it was legitimate is not something on-call can decide", "Whether it was legitimate (a support request, a business closing) or not (a compromised account, a script gone wrong) is not something on-call can decide.", "handbook-7"),
         S("page owner: accounts or records deleted cannot be undone", "Things you cannot undo include: customer data seen by the wrong person, money moved wrongly, accounts or records deleted, secrets exposed.", "handbook-3"),
     ]},
    # ---------------------------------------------------------------- api
    {"id": "st-replica-lag", "service": "api", "page": "howto-api-replica-lag",
     "question": "api replica lag has been above 10 seconds for a while. walk me through what i check",
     "truth": [["Ravi"], ["promot"]], "wrong": [],
     "steps": [
         S("Sorrel / api, Database row", "Open the **Sorrel / api** board and check the **Database** row."),
         S("which region is affected", "Identify the exact region affected. Is it restricted to `ap-northeast`, or present globally?"),
         S("one region: check aws health for storage or database degradation", "Check the provider status (health.aws.amazon.com or the account personal health dashboard) for AWS storage (EBS) or database performance degradation in that region (e.g., `ap-northeast-1`)."),
         S("compare onset with the deploy history", "Cross-reference the onset time with the deploy history in the deploy tool."),
         S("check whether the last release applied migrations holding locks", "Check if database migrations were applied during the last release that could be holding long table locks or performing heavy sequential scans."),
         S("logs: service=api level=ERROR, earliest errors", "Look for the earliest errors rather than the highest volume."),
         S("search pool exhausted, deadlock, timeout, slow queries", "service=api msg=\"pool exhausted\""),
         S("check connections in use per pool", "Examine the **Connections in use per pool** panel on the Database row:"),
         S("never promote a replica; that is Ravi's decision", "**Promoting a replica is a decision for Ravi, never an on-call move.**"),
         S("do not change pool limits or kill DB processes without owner", "You must not alter connection pool limits, change database configurations, or kill long-running database processes on production clusters without owner approval."),
         S("page Ravi if > 10 s for > 15 min with pools exhausted", "Replica lag in any region exceeds 10 seconds for more than 15 minutes continuously, connection pools are exhausted, and read queries are timing out at scale across nodes."),
         S("post lag values and findings in #inc-live", "Document observed lag values and log findings in `#inc-live`."),
         S("tell Hana if customers ask about stale data", "coordinate with support lead Hana so support staff have visibility into the fact that read lag is occurring."),
     ]},
    {"id": "st-reindex", "service": "api", "page": "howto-api-search-index-rebuild",
     "question": "how do i run a full rebuild of the api search index?",
     "truth": [["search-reindex-full"]], "wrong": [],
     "steps": [
         S("working hours only, never a night move", "Rebuilding the search index is a working-hours job, never a night move for on-call."),
         S("the api team starts it; others coordinate with Daniel or Ravi", "Engineers on other teams or on-call responders outside of the api team should coordinate directly with Daniel or Ravi before taking action."),
         S("check index freshness first: under 6 hours needs no rebuild", "an index under 6 hours old does not need a rebuild."),
         S("between 09:00 and 18:00 JST", "Confirm current time is within normal business operating hours in Japan (between 09:00 and 18:00 JST), outside of deploy freezes and major traffic spikes."),
         S("pool usage below 70 %", "connection pool usage must be below 70 % across all active nodes"),
         S("replica lag under 100 ms", "read replica lag must be steady and under 100 ms."),
         S("avoid 12:00-13:00 and 18:00-23:00 JST", "Avoid launching during the lunchtime booking rush (12:00–13:00 JST) or the evening booking peak (18:00–23:00 JST)"),
         S("prefer Tuesday/Thursday 14:00-16:00 JST", "Tuesday and Thursday afternoons between 14:00 and 16:00 JST are the preferred operating windows."),
         S("note in #team-api", "Drop a brief note in `#team-api`:"),
         S("job console, job search-reindex-full", "The rebuild is started from the job console, job `search-reindex-full`, by the api team."),
         S("do not change the default batch parameters", "Do not modify the default batch parameters unless previously agreed upon with Ravi or Kenji Sato."),
         S("press Run Job", "Press **Run Job**."),
         S("about 70 minutes; searches use the old index meanwhile", "A full rebuild takes about 70 minutes; searches keep using the old index until the new one is ready."),
         S("watch query time, pools, replica lag, errors", "Keep the following metrics open throughout the run:"),
         S("if the reader exhausts replica connections, pause or abort", "If the reader exhausts replica connections, pause or abort the job run in the job console."),
         S("confirm the swap, freshness < 5 min, latency, a manual search", "The **Search index: index freshness** graph should drop immediately to near zero (typically `< 5m`)."),
         S("post the finish in #team-api", "Post an update in `#team-api`:"),
     ]},
    {"id": "st-load-test", "service": "api", "page": "howto-stop-unowned-load-test",
     "other_pages": ["handbook-7"],
     "question": "theres load test traffic with the X-Sorrel-Loadtest header hitting api and nobody seems to own it. how do i stop it?",
     "truth": [["loadctl stop"]], "wrong": [],
     "steps": [
         S("check the game day calendar first", "Check the game day calendar first; if the test is on it, ask its owner before stopping it."),
         S("no calendar entry or owner: it is orphaned, stop it", "Proceed immediately to Section 4 and stop the test using the command-line tool."),
         S("loadctl list to see the runs", "Run `loadctl list` to view all active test runners across all regions:"),
         S("loadctl stop <test id>, tell #platform", "If nobody owns it, stop it with the load test tool: `loadctl stop <test id>`, and tell `#platform`."),
         S("--force only if stop hangs 30 s", "If `loadctl stop <test id>` hangs or worker nodes fail to terminate connections within 30 seconds, force the termination:"),
         S("post in #platform at once", "As soon as the test is terminated, post a summary in the `#platform` chat channel:"),
         S("if an incident thread is open, post the action in #inc-live", "Post an update with the concrete action:"),
         S("watch dashboards for 10 minutes", "Watch dashboards for 10 minutes to verify:"),
         S("on-call log line; first move read logs", "When investigating anomalous traffic, reading the service logs to identify the header and IP is the correct first move"),
     ]},
    {"id": "st-api-rollback", "service": "api", "page": "deploying-with-shipyard",
     "other_pages": ["handbook-5"],
     "question": "how do i roll back api now that it's on shipyard?",
     "truth": [["shipyard rollback api"]], "wrong": ["deploy tool, project"],
     "steps": [
         S("list the releases", "shipyard releases payments"),
         S("shipyard rollback <service> --to <release>", "Run `shipyard rollback api --to <previous release>` (releases are named like `r-212`), or press \"Roll back to this release\" on api's Releases page in Shipyard.", "handbook-5"),
         S("use the release just below the live one", "Use the release just below the `live` one in the list."),
         S("type the service name to confirm", "Shipyard asks you to type the service name to confirm."),
         S("or the browser: shipyard.sorrel.internal, Releases, Roll back to this release", "Open `shipyard.sorrel.internal`, pick the service, open **Releases**."),
         S("api replaces nodes two at a time, about six minutes", "api replaces its nodes two at a time; about six minutes."),
         S("copy both release names into the incident thread", "Copy both release names into the incident thread yourself as well."),
         S("one release needs no approval", "**The on-call engineer can roll back one release, with no approval.**"),
         S("two or more releases need Ravi", "Rolling back two or more releases needs the service owner's approval in Shipyard: Ravi for api, Mei for payments."),
         S("still unhealthy 10 min after: do not roll back again, page the owner", "Do not roll back again to see if an older release helps; that is the two-or-more case and it needs the owner."),
     ]},
    {"id": "st-audit-actions", "service": "api", "page": "postmortem-api-audit-disk",
     "question": "the api audit log writer stopped last december after a disk filled up. what did we change afterwards?",
     "truth": [["75"]], "wrong": [],
     "steps": [
         S("disk usage alert on api spool volumes at 75 %", "Configure a proactive disk usage alert on all `api` spool volumes that fires when disk usage exceeds 75%."),
         S("spooler offloads to aws object storage past 70 %", "Re-architect the audit spooler to automatically offload batches to aws object storage whenever local disk utilization passes 70%."),
         S("catch ENOSPC and recover instead of killing the worker", "Update the background audit worker error handling to catch `ENOSPC` and filesystem write exceptions, automatically attempting recovery rather than terminating the worker thread."),
         S("review log-export cron tasks release file locks", "Review the auxiliary log-exporting cron tasks to ensure file locks are released cleanly after execution."),
         S("a replay tool to rebuild audit events from request logs", "Create an automated replay tool to reconstruct audit events from request logs in case of future auxiliary ingestion stalls."),
     ]},
    # ---------------------------------------------------------------- payments
    {"id": "st-trace-refund", "service": "payments", "page": "howto-trace-a-refund",
     "question": "customer says their refund never showed up. how do i trace it through the logs?",
     "truth": [["refund sent"], ["refund settled"]], "wrong": [],
     "steps": [
         S("narrow the window to 2-4 hours", "Always bound your query to the specific 2- to 4-hour window surrounding when the customer requested the cancellation or when the support ticket was filed."),
         S("never search for card numbers", "**Never search for card numbers; they are never logged.**"),
         S("only a booking id: find the ref from the refund requested line", "Look for the `\"refund requested\"` line and copy the `ref` value (format: `ref_...`)."),
         S("search refund sent for the ref", "service=payments msg=\"refund sent\" ref=\"<ref>\""),
         S("HTTP 200 = in stripe's ledger; 4xx/5xx = check status.stripe.com; none = never left us", "**No result found**: The refund never left our cluster."),
         S("search refund settled for the ref", "service=payments msg=\"refund settled\" ref=\"<ref>\""),
         S("settled but no money: bank delay of 5-10 business days", "it is a matter of inter-bank processing delays (which typically take 5–10 business days depending on their card issuer), not a technical failure within Sorrel."),
         S("not settled and sent < 6 hours ago: normal", "If it was sent fewer than 6 hours ago, this is normal behavior."),
         S("check webhook health and webhook retries for the ref", "service=payments msg=\"webhook\" outcome=retry ref=\"<ref>\""),
         S("two refund sent lines: stop and page Mei", "If one reference shows two 'sent' lines, money may have moved twice: stop and page Mei."),
         S("give support the facts; on-call never talks to the customer about lost funds", "Never communicate directly with businesses or consumers regarding lost funds or duplicate payouts."),
     ]},
    {"id": "st-two-sent", "service": "payments", "page": "howto-trace-a-refund",
     "question": "i see two 'refund sent' lines for the same ref in the payments logs. what do i do now?",
     "truth": [["Mei"], ["P1"]], "wrong": [],
     "steps": [
         S("stop investigating: no scripts, no webhooks, no DB updates", "**Stop your investigation immediately.** Do not attempt to rerun scripts, do not issue cancellation webhooks, and do not execute ad-hoc database updates."),
         S("do not roll back as the first move", "**Do not attempt to roll back code** as your first move if the money has already left our accounts."),
         S("declare a P1", "**Declare a P1 incident.**"),
         S("page Mei directly", "**Page Mei directly via the paging tool.**"),
         S("paste the alert line, the ref, both timestamps, both stripe refund ids", "The Stripe refund IDs associated with each line (e.g., `re_AAA...` and `re_BBB...`)."),
     ]},
    {"id": "st-stripe-key", "service": "payments", "page": "team-secrets-manager",
     "other_pages": ["handbook-7", "provider-stripe-notes"],
     "question": "i just found a live stripe key printed in the payments logs. what do i do?",
     "truth": [["Mei"], ["P1"]], "wrong": [],
     "steps": [
         S("do not copy the key anywhere; link to where it appears", "**If a key appears in logs, chat or a ticket: do not copy it anywhere else, link to where it appears, and page the owner of the credential.**"),
         S("copy the permalink to the log query", "Copy the exact permalink to the log query in the log search tool."),
         S("treat it as P1", "Treat as P1 (secret exposure)."),
         S("page Mei", "Page **Mei** immediately through the paging tool."),
         S("post to #inc-live without the key", "\"P1 opened for secret exposure. Live Stripe key identified in `service=payments` logs. Query link provided to owner. Mei has been paged. On-call standing by.\""),
         S("do not try to revoke it in the stripe dashboard", "Do not attempt to log into the Stripe dashboard to revoke the key."),
         S("wait for Mei; she does the rollover", "Wait for Mei to acknowledge and establish a remediation channel."),
     ]},
    {"id": "st-webhook-secret-actions", "service": "payments", "page": "postmortem-payments-webhook-secret",
     "question": "what did we change after stripe webhooks got rejected following the signing secret rotation?",
     "truth": [["secrets manager"]], "wrong": [],
     "steps": [
         S("secret read from the secrets manager at start-up on every node", "The secret is now read directly from the cloud secrets manager at service start-up on every node."),
         S("every node checks all regions report the same secret version", "every node runs an internal verification check confirming that all active regions (`ap-northeast`, `us-east`, `eu-west`) report the identical secret version metadata."),
         S("old and new secret both registered for 24 hours", "both the old secret and the new secret must remain registered in stripe simultaneously for at least 24 hours."),
         S("verify against the primary, then the secondary secret", "Signature checking logic in `payments` now attempts verification against the primary secret, and if that fails, checks against the secondary secret before rejecting the request."),
         S("old secret retired only after 2 hours of zero use", "Decommissioning of an old secret is only permitted after dashboards verify zero successful verifications against the old secret for at least two consecutive hours."),
         S("rotation script checks regional return codes, fails closed", "Update rotation script to check regional secrets manager return codes explicitly and fail closed on timeouts."),
         S("deploy tool checks config hash parity", "Add an automated check in the deployment tool verifying configuration hash parity across all running instances in all regions."),
         S("docs update", "Update Section 6.1 of the internal documentation regarding stripe key maintenance and rotation procedures."),
         S("support canned responses for payment pending", "Create standard support canned responses for customers reporting prolonged `payment pending` statuses."),
     ]},
    {"id": "st-payout-alert", "service": "payments", "page": "team-payments-notes",
     "question": "the payout job alert fired around sunday midnight JST. what should i check?",
     "truth": [["38"]], "wrong": [],
     "steps": [
         S("payout runs Sunday 23:00 JST, about 38 minutes", "The weekly payout job runs on Sunday at 23:00 JST and usually takes about 38 minutes."),
         S("check whether it has run past its standard window before calling it stalled", "check whether the job has exceeded its standard window before treating it as stalled."),
         S("if it halts or throws: read logs first", "If the job halts halfway through or throws unhandled exceptions during execution, read logs first, and page owner if money moved or payouts stalled halfway through."),
     ]},
    # ---------------------------------------------------------------- notifier
    {"id": "st-stuck-workers", "service": "notifier", "page": "howto-notifier-queue-panels",
     "question": "notifier delivered per minute is 0 and the oldest message is 40 min old. what do i do?",
     "truth": [["deploy"], ["log"]], "wrong": [],
     "steps": [
         S("oldest > 30 min with delivered 0 = workers stuck", "**Oldest message age above 30 minutes while delivered per minute is zero means the workers are stuck.**"),
         S("confirm delivered is 0, oldest climbing, added still > 0", "**Messages added per minute** shows items are still being queued by other services."),
         S("check notifier deploy history, note the age", "Check the deploy history in the deploy tool for project \"sorrel\", service \"notifier\". Note the age of the last deploy."),
         S("deploy within 30 min: roll back", "In this case, your first move is **roll back** to the previous deploy."),
         S("no recent deploy: read logs", "If there has been no recent deploy, your first move is **read logs**."),
         S("search level=ERROR, worker stuck / worker idle", "Look for worker loop errors: `service=notifier msg=\"worker stuck\"` or `service=notifier msg=\"worker idle\"`."),
         S("check for crashes from memory or timeouts on the three workers", "Check if the worker processes crashed due to memory or execution timeouts across the three worker nodes in each active region"),
         S("page Tom if a P1 runs 30 min without relief", "An incident commander determines that an unresolved P1 queue issue has run past 30 minutes without relief from the initial triage move."),
     ]},
    {"id": "st-night-batch", "service": "notifier", "page": "howto-notifier-queue-panels",
     "other_pages": ["team-notifier-notes", "handbook-7"],
     "question": "notifier queue depth alert at 3am, depth is about 1,300. walk me through it",
     "truth": [["delivered per minute"], ["no action"]], "wrong": [],
     "steps": [
         S("the nightly batch: depth 1,000-1,500, drains by 06:00 JST", "**During the nightly reminder batch, depth commonly reaches 1,000 to 1,500 and drains by 06:00 JST.**"),
         S("check delivered per minute is high and steady", "Verify that **Messages delivered per minute** is high and steady."),
         S("check oldest message age stays controlled", "Verify that **Oldest message age** remains controlled (messages are flowing through, even if deep in the stack)."),
         S("healthy and draining: no action, write the on-call log line", "choose **no action**, record the entry in the on-call log, and move on."),
         S("do not page the owner for a four-digit backlog 02:00-04:00", "do not page owner merely because the backlog crosses four digits between 02:00 and 04:00 JST.", "team-notifier-notes"),
         S("delivered drops to 0 with queue > 1,000: read logs", "if delivered per minute drops to zero while the queue sits above 1,000, read logs to see if workers are stuck or encountering errors.", "team-notifier-notes"),
     ]},
    {"id": "st-sendgrid-quota", "service": "notifier", "page": "provider-sendgrid-quota",
     "question": "sendgrid is returning quota errors on notifier. how do i handle it?",
     "truth": [["Tom"]], "wrong": [],
     "steps": [
         S("first move: check provider", "**check provider:** If the alert explicitly cites vendor errors, quota limits, or third-party timeouts, look at `status.sendgrid.com` first."),
         S("never change the sendgrid plan; raising quota is Tom's purchasing call", "Raising the quota is a purchasing decision for Tom, not an on-call action."),
         S("which stream: marketing or transactional (Vendor quota usage panel)", "Review the **Vendor quota usage** panel on the `notifier` board."),
         S("marketing at 100 %: customer email unaffected, holds until 09:00 JST, P3", "Customer transactional emails (confirmations, receipts) are entirely unaffected due to stream separation."),
         S("transactional at 100 %: confirmations delayed; time until reset", "If the **Transactional stream** is at 100 %: Customers booking appointments will experience delayed confirmations. Evaluate time until reset (09:00 JST)."),
         S("confirm workers defer and do not drop", "Verify that workers are safely deferring jobs and not dropping messages."),
         S("long daytime transactional delay: page Tom with alert, severity, depth", "If transactional delivery will be delayed for a prolonged period during peak daytime hours, page Tom using the paging tool with the alert line, current severity, and current queue depth."),
         S("write the on-call log line", "Record the entry in the on-call log following the standard format:"),
     ]},
    {"id": "st-template-actions", "service": "notifier", "page": "postmortem-notifier-template-crash",
     "question": "what did we change after a bad template stalled the notifier queue?",
     "truth": [["park"]], "wrong": [],
     "steps": [
         S("poison-pill parking: a message that crashes a worker twice goes to parked", "Configure `notifier` queue consumers and the broker so that any message that crashes a worker twice is automatically routed to a `parked` (dead-letter) queue without human intervention."),
         S("harden template rendering: escape/strip control characters, log a warning", "Wrap the Jinja2 template interpolation block in a defensive sanitization handler that escapes or strips invalid control characters and logs a warning instead of raising an unhandled exception."),
         S("api name validation rejects control characters", "Update `api` profile name validators to reject unprintable Unicode control characters and invalid direction overrides at submission time."),
         S("review visibility timeout / crash retry backoff", "Review worker crash retry semantics to ensure failed workers back off with a non-zero visibility timeout, preventing hot crash loops."),
         S("status page drill on the 20-minute window", "Run a refresher for on-call engineers and incident commanders on updating `status.sorrel.app` within the 20-minute window on silent P1 failures."),
     ]},
    {"id": "st-duplicates", "service": "notifier", "page": "howto-notifier-queue-panels",
     "question": "the duplicate detection panel on notifier is spiking. what do i check?",
     "truth": [["duplicate id"]], "wrong": [],
     "steps": [
         S("a spike is > 100 in 10 minutes", "A sudden spike (> 100 duplicates over a 10-minute window) indicates either an upstream service (such as api) repeatedly enqueuing duplicate jobs, or worker nodes failing to acknowledge queue receipts after successful vendor dispatch."),
         S("logs: msg=\"duplicate id\", find the producing service", "Open logs: `service=notifier msg=\"duplicate id\"`. Identify the producing service generating the duplicate submissions."),
         S("compare with recent notifier or api deploys", "Compare against recent deploys of notifier or api."),
         S("find out why before anything else", "Duplicates: the same message sent more than once. Customers get annoyed, and support gets tickets. Find out why before anything else.", "handbook-5"),
     ]},
]

HALF = [
    {"id": "half-pay-4107", "page": "handover-2026-01-12",
     "question": "Refunds failed with PAY-4107 back in January. What did Mei's team do for those customers, and how many days did they wait for their money?",
     "answered": "what Mei's team did", "missing": "how many days the customers waited",
     "truth": [["bank transfer"]], "wrong": [],
     "steps": [S("paid the three customers back by bank transfer", "Mei's team paid those three customers back by bank transfer instead.")],
     "grep": [r"PAY-4107", r"bank transfer"], "grep_note": "both appear in one page only (handover-2026-01-12, line 19); that paragraph gives the charge age (180 days) and no wait time"},
    {"id": "half-10dlc-cost", "page": "handover-2026-06-08",
     "question": "Texts to US numbers stopped arriving in June. What fixed it, and how much does the 10DLC registration cost us?",
     "answered": "what fixed it", "missing": "the cost",
     "truth": [["10DLC"]], "wrong": [],
     "steps": [S("Tom approved registering our 10DLC campaign with twilio", "Tom approved registering our 10DLC campaign with twilio; registration went through on Friday and delivery is back to normal.")],
     "grep": [r"10DLC|A2P", r"(10DLC|A2P|twilio).*(cost|fee|price|\$|¥|per month)|(cost|fee|price|\$|¥).*(10DLC|A2P)"],
     "grep_note": "10DLC/A2P only in handover-2026-06-08; no cost, fee or price for it in any page"},
    {"id": "half-hanabi-v1", "page": "handover-2026-03-23",
     "question": "When were the old v1 partner endpoints switched off, and when is Hanabi Booking going to stop their v1 test script?",
     "answered": "the switch-off date", "missing": "when Hanabi stops the script",
     "truth": [["2026-03-18", "March 18", "18 March"]], "wrong": [],
     "steps": [S("switched off on 2026-03-18", "On Wednesday 2026-03-18, the old v1 partner API endpoints were switched off, after the last partner moved to v2.")],
     "grep": [r"hanabi", r"test script"], "grep_note": "Hanabi in handover-2026-03-23 and handover-2026-05-25; neither gives a date for the script to stop"},
    {"id": "half-payout-total", "page": "handover-2025-12-29",
     "question": "How long did the December 2025 year-end payout take, and how much money did it pay out to businesses in total?",
     "answered": "how long", "missing": "the total paid out",
     "truth": [["2 h 05", "2h05", "2 hours 5", "2 hours and 5", "125 min", "2:05", "2 h 5"]], "wrong": [],
     "steps": [S("2 h 05 min instead of the usual 38", "The year-end payout on Sunday 2025-12-28 took 2 h 05 min instead of the usual 38 min, because of year-end volume.")],
     "grep": [r"payout.*(¥|yen|jpy|\$|usd|amount|total|million)|(¥|yen|jpy|\$|usd|million).*payout"],
     "grep_note": "no page gives a payout amount (the one hit is handbook-7's generic 'for the wrong amount')"},
    {"id": "half-tofu-count", "page": "team-web-notes",
     "question": "When did Priya fix the kanji names showing up as empty boxes on the booking page, and how many bookings were hit?",
     "answered": "when", "missing": "how many bookings",
     "truth": [["2026-06-11", "June 11", "11 June"]], "wrong": [],
     "steps": [S("Priya added a fallback to the full Noto Sans JP font on 2026-06-11", "Priya added a fallback to the full Noto Sans JP font on 2026-06-11.")],
     "grep": [r"tofu|kanji|noto|empty box"], "grep_note": "only team-web-notes (lines 10, 12) carries the incident; it gives no count of bookings or customers"},
    {"id": "half-capture-total", "page": "team-payments-notes",
     "question": "How many bookings got a duplicate capture in January 2026, and how much money did we refund in total?",
     "question_v1": "How many bookings got charged twice in January 2026, and how much money did we refund in total?", "reworded_why": "v1 top 5 had no team-payments-notes ('charged twice' is the EP12 other-words gap); v2 uses the page's 'duplicate capture'",
     "answered": "how many bookings", "missing": "the total amount",
     "truth": [["63"]], "wrong": [],
     "steps": [S("duplicate capture on 63 bookings on 2026-01-14", "leading to duplicate capture on 63 bookings on 2026-01-14.")],
     "grep": [r"duplicate capture|captures went through|2026-01-14", r"(¥|yen|jpy|\$|usd|amount|total)"],
     "grep_note": "the incident is only in team-payments-notes; that page has no amount (the second pattern is checked on that page only)",
     "grep_second_on": ["team-payments-notes"]},
    {"id": "half-suppression-tickets", "page": "team-notifier-notes",
     "question": "How many addresses ended up on sendgrid's suppression list after the February domain switch, and how many support tickets did it cause?",
     "answered": "how many addresses", "missing": "how many tickets",
     "truth": [["2,312", "2312"]], "wrong": [],
     "steps": [S("2,312 addresses from soft bounces", "sendgrid's suppression list picked up 2,312 addresses from soft bounces during the switch, and sendgrid stopped sending to them.")],
     "grep": [r"suppression list|domain switch|sending-domain|soft bounce", r"ticket"],
     "grep_note": "the switch is only in team-notifier-notes; 'ticket' does not appear on that page",
     "grep_second_on": ["team-notifier-notes"]},
    {"id": "half-golden-week-2025", "page": "handover-2026-05-04",
     "question": "What was the booking peak per minute during Golden Week 2026, and what was it in Golden Week 2025?",
     "answered": "the 2026 peak", "missing": "the 2025 peak",
     "truth": [["1,960", "1960"]], "wrong": [],
     "steps": [S("1,960 bookings per minute on 2026-05-02", "Golden Week: booking volume peaked on Saturday 2026-05-02 at 1,960 bookings per minute on api, at about 11:00 JST.")],
     "grep": [r"golden week", r"bookings per minute|per minute on api"],
     "grep_note": "Golden Week figures only in handover-2026-05-04 (2026); handbook-13 mentions Golden Week with no number; 'bookings per minute' appears once"},
    {"id": "half-restore-size", "page": "handover-2026-04-27",
     "question": "Who owns the weekly restore test for the payments database, and how big is that database?",
     "answered": "the owner", "missing": "the size",
     "truth": [["Leo"]], "wrong": [],
     "steps": [S("Leo owns it going forward", "Leo owns it going forward, so incoming shifts will track this run cadence.")],
     "grep": [r"restore test", r"\b(GB|TB|MB)\b|gigabyte|terabyte|database size|size of the"],
     "grep_note": "the restore test is only in handover-2026-04-27; the only size in any page is 14 GB of dead files on an api spool disk (postmortem-api-audit-disk)"},
    {"id": "half-cert-credits", "page": "postmortem-api-partner-certificate",
     "question": "When the partner API certificate expired in April 2025, how many partners were affected, and how much did we credit them?",
     "answered": "how many partners", "missing": "the credit",
     "truth": [["3 partners", "three partners", "three integration partners", "3 integration partners", "three external", "three of", "3 of"]], "wrong": [],
     "steps": [S("three integration partners", "A total of three integration partners were impacted during the window.")],
     "grep": [r"credit|compensat|goodwill|refund", r"partner.*(credit|compensat)|(credit|compensat).*partner"],
     "grep_note": "no credit/compensation/refund on the postmortem page (first pattern checked on that page), and no page links partners to a credit",
     "grep_first_on": ["postmortem-api-partner-certificate"]},
]


def lines_with(pages, pat, only=None):
    out = []
    for p in pages:
        if only and p["id"] not in only:
            continue
        for i, line in enumerate(p["text"].split("\n"), 1):
            if re.search(pat, line, re.I):
                out.append({"page": p["id"], "line": i, "text": line.strip()[:240]})
    return out


def build():
    pages = lookup.pages()
    assert len(pages) == 127, len(pages)
    by_id = {p["id"]: p for p in pages}
    ep12 = json.load(open("tickets/questions-ep12.json"))
    problems, checks = [], []
    new = []
    for q in STEPS:
        new.append({"id": q["id"], "kind": "steps", "service": q["service"], "page": q["page"],
                    "other_pages": q.get("other_pages", []), "question": q["question"], "truth": q["truth"],
                    "wrong": q["wrong"], "steps": q["steps"],
                    **{k: q[k] for k in ("question_v1", "reworded_why") if k in q}})
    for q in HALF:
        new.append({"id": q["id"], "kind": "half", "page": q["page"], "question": q["question"],
                    "answered": q["answered"], "missing": q["missing"], "truth": q["truth"], "wrong": q["wrong"],
                    "steps": q["steps"], **{k: q[k] for k in ("question_v1", "reworded_why") if k in q}})
    for q in new:                                    # every step line is on its page, word for word
        for s in q["steps"]:
            pid = s.get("page", q["page"])
            if s["line"] not in by_id[pid]["text"]:
                problems.append(f"{q['id']}: line not on {pid}: {s['line'][:80]}")
    for q in HALF:                                   # the grep proof for the missing part
        rec = {"id": q["id"], "missing": q["missing"], "note": q["grep_note"], "patterns": []}
        for k, pat in enumerate(q["grep"]):
            only = q.get("grep_first_on") if k == 0 else q.get("grep_second_on") if k == 1 else None
            hits = lines_with(pages, pat, only)
            rec["patterns"].append({"regex": pat, "case_insensitive": True, "searched": only or "all 127 pages",
                                    "hits": len(hits), "lines": hits})
        checks.append(rec)
    return pages, ep12, new, problems, checks


if __name__ == "__main__":
    pages, ep12, new, problems, checks = build()
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    retrieval = []
    for q in new:
        top = [p["id"] for p in search.keyword_search(q["question"], pages, 5)]
        retrieval.append({"id": q["id"], "kind": q["kind"], "question": q["question"], "page": q["page"], "top5": top,
                          "rank": top.index(q["page"]) + 1 if q["page"] in top else None})
        print(f"{q['id']:26} {'HIT ' + str(top.index(q['page']) + 1) if q['page'] in top else 'MISS  '}  {top}")
    exp = {r["id"]: r["rank"] is not None for r in retrieval}
    for q in new:
        q["retrieval_expected"] = exp[q["id"]]
    qfile = {"written": "2026-10-12, before any EP13 model call; the 40 EP12 questions copied unchanged from "
                        "tickets/questions-ep12.json",
             "grading": ep12["grading"] + " EP13 adds kind 'steps' (a procedure or list on the page; 'steps' lists "
                        "every step or fact the answer page gives, each with its exact page line; 'page' is the main "
                        "answer page, 'other_pages' also carry some of it) and kind 'half' (the page answers one "
                        "part, the other part is in no page: right = the first part AND says the pages do not give "
                        "the second). Steps and half answers are graded by hand, claim by claim. retrieval_expected = "
                        "the main page was in keyword search's top 5 at the freeze. The mix is designed.",
             "questions": ep12["questions"] + new}
    json.dump(qfile, open("tickets/questions-ep13.json", "w"), indent=1, ensure_ascii=False)
    out = {"what": "EP13 Q build: step lines checked on their pages, half-question grep proofs, keyword top 5 on every "
                   "new question (search.keyword_search, local, before the freeze)",
           "step_line_problems": problems, "half_grep": checks, "retrieval": retrieval}
    json.dump(out, open("runs/ep13/2026-10-12-q-build.json", "w"), indent=1, ensure_ascii=False)
    for c in checks:
        print(c["id"], [(p["regex"], p["hits"], sorted({h["page"] for h in p["lines"]})) for p in c["patterns"]])
