"""EP11 measurement harness, not episode code: the team's documents that exist only as PDFs.

    python3 measure/ep11_docs.py html       # write library/pdf/<slug>.html (+ rev2) and <slug>.truth.json from the data below
    python3 measure/ep11_docs.py pdf        # print every HTML to PDF with headless Chrome (fresh --user-data-dir)
    python3 measure/ep11_docs.py scan       # the three scans: print, rasterise, degrade, wrap back into an image-only PDF
    python3 measure/ep11_docs.py freeze     # md5 + page count of every PDF -> library/pdf/PROVENANCE.json

The content below is the single source: the HTML and the truth file are both written from it, before any extractor runs.
Names are the four owners from sorrel/oncall.py only. Dates 2023-01 to 2025-12.
"""
import hashlib, html, json, os, re, subprocess, sys, tempfile, time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "library", "pdf")
BUILD = os.path.join(OUT, "build")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# ------------------------------------------------------------------ the documents

DOCS = {}

DOCS["postmortem-notifier-reminder-backlog"] = {
    "kind": "postmortem",
    "title": "Postmortem: notifier reminders delayed by a stuck queue worker",
    "crumb": "Sorrel Engineering / Postmortems / 2023",
    "meta": [("Incident date", "2023-03-14 (Tuesday, morning JST)"), ("Severity", "SEV-2"), ("Service", "notifier"),
             ("Incident commander", "Aiko"), ("Author", "Tom"), ("Status", "Final, reviewed 2023-03-16")],
    "summary": "On 2023-03-14 the morning batch of SMS reminders left up to 77 minutes late. One of the three notifier "
               "queue workers lost its queue lease every few seconds, after a config change the day before had cut the "
               "lease time from 60 s to 6 s, and the two healthy workers could not keep up with the batch. Setting the "
               "lease time back to 60 s and restarting the workers cleared the queue by 08:47.",
    "impact": ["Customers: 4,212 SMS reminders for appointments between 09:00 and 11:00 JST were delayed; the last one "
               "left 77 minutes late.",
               "41 appointments started before their reminder arrived. Support counted 17 customer reports, most of "
               "them from businesses.",
               "Money: none moved. Data: none exposed or lost.",
               "Email confirmations were not affected; they use a separate queue."],
    "timeline": [
        ("07:30", "The scheduler puts the morning reminder batch on the notifier queue: 4,212 SMS reminders for "
                  "appointments between 09:00 and 11:00 JST.", "notifier scheduler"),
        ("07:38", "Alert fires: notifier queue depth above 2,000 for 5 minutes. The paging tool pages the on-call "
                  "engineer.", "paging tool"),
        ("07:41", "Page acknowledged. Ravi opens a thread in #inc-live with the alert line and a screenshot of the "
                  "queue depth panel.", "Ravi"),
        ("07:49", "notifier logs show worker 2 of 3 repeating \"lease renewal failed\" about once a second and taking "
                  "no new messages. Workers 1 and 3 are sending but cannot keep up with the batch.", "Ravi"),
        ("07:55", "First customer report through support: a hair salon says its 09:00 clients usually have their "
                  "reminder by 07:45 and none has arrived.", "Support"),
        ("08:02", "Incident declared (SEV-2). Aiko takes incident commander and pages Tom, because the queue workers "
                  "are his area.", "Aiko"),
        ("08:09", "Tom joins. He confirms on status.twilio.com that twilio is healthy and that messages sent by "
                  "workers 1 and 3 are being delivered normally.", "Tom"),
        ("08:16", "Tom restarts worker 2. It takes new messages for about forty seconds, then falls back into the "
                  "same lease renewal error.", "Tom"),
        ("08:24", "Tom finds the cause: a config change on 2023-03-13 cut the queue lease time from 60 s to 6 s. "
                  "Worker 2 runs on the node whose clock is furthest off, so it loses every lease before it can renew "
                  "it.", "Tom"),
        ("08:31", "The lease time is set back to 60 s and all three workers are restarted. Queue depth starts to fall "
                  "by about 300 messages a minute.", "Tom"),
        ("08:47", "Queue depth is back under 200 and the morning batch is fully sent. The last reminder left 77 "
                  "minutes late.", "Ravi"),
        ("08:55", "Aiko gives support the list of 41 appointments that started before their reminder arrived, so the "
                  "businesses can be told.", "Aiko"),
        ("09:20", "Incident closed. Aiko posts the summary in #inc-live and books the postmortem for the Thursday "
                  "review.", "Aiko"),
    ],
    "well": ["The log line said \"lease renewal failed\" in plain words, so the stuck worker was found within eight "
             "minutes of the page.",
             "twilio was ruled out quickly, because two workers were still delivering."],
    "badly": ["The queue depth alert fired 8 minutes after the batch started; an alert on the age of the oldest "
              "message would have said the same thing with more urgency.",
              "The lease time change on 2023-03-13 was reviewed as a tuning change and was not tested against a node "
              "with clock drift."],
    "actions": [
        ("Alert on the age of the oldest message on the notifier queue, not only on queue depth.", "Tom",
         "2023-03-24", "Done"),
        ("Enforce a minimum lease time of 30 s in code, so a config change cannot set it lower.", "Tom",
         "2023-03-31", "Done"),
        ("Add per-worker send rate to the \"Sorrel / notifier\" board, so one silent worker shows at a glance.",
         "Ravi", "2023-04-07", "Done"),
        ("Check clock sync on every notifier node in the weekly node health report.", "Ravi", "2023-04-14", "Open"),
    ],
    "facts": ["2023-03-14", "SEV-2", "Final, reviewed 2023-03-16", "4,212 SMS reminders", "77 minutes late",
              "41 appointments", "17 customer reports", "from 60 s to 6 s", "lease renewal failed",
              "300 messages a minute", "2023-04-14"],
}

DOCS["postmortem-api-index-migration"] = {
    "kind": "postmortem",
    "title": "Postmortem: api date search slow after a migration dropped an index",
    "crumb": "Sorrel Engineering / Postmortems / 2024",
    "meta": [("Incident date", "2024-07-09 (Tuesday, afternoon JST)"), ("Severity", "SEV-2"), ("Service", "api"),
             ("Incident commander", "Mei"), ("Author", "Ravi"), ("Status", "Final, reviewed 2024-07-11")],
    "summary": "api deploy d-4471 carried migration 0193, which dropped the old index on bookings (business_id, "
               "starts_at) before its replacement had finished building. Every date search on a booking page then "
               "read the bookings table without an index, the primary database ran hot, and date search was slow for "
               "69 minutes. Rolling back the code did not help, because a rollback does not bring back a dropped "
               "index. Date search recovered when the new index finished building at 15:19.",
    "impact": ["Customers: date search on booking pages took 2 to 6 seconds between 14:12 and 15:21 JST, and some "
               "searches timed out. Support received 212 tickets.",
               "Bookings made in that window were about 35 % lower than in the same hour the week before.",
               "Money and data: no payments affected, nothing lost or exposed."],
    "timeline": [
        ("14:05", "api deploy d-4471 goes out. It carries migration 0193, which drops the old index on bookings "
                  "(business_id, starts_at) and starts building a new composite index in the background.", "Ravi"),
        ("14:09", "The background index build starts on the primary database in ap-northeast-1. The old index is "
                  "already gone, so date searches now read the whole bookings table.", "deploy tool"),
        ("14:12", "api p95 latency for the availability endpoint rises from 180 ms to 1.9 s. CPU on the primary "
                  "database reaches 92 %.", "metrics tool"),
        ("14:16", "Alert fires: api p95 above 1.5 s for 3 minutes. The paging tool pages the on-call engineer.",
         "paging tool"),
        ("14:18", "Page acknowledged by Tom, the primary on-call engineer that week.", "Tom"),
        ("14:23", "Tom notes the last api deploy is 18 minutes old, and the slow queries in the api logs all read "
                  "bookings by business and start time.", "Tom"),
        ("14:27", "Incident declared (SEV-2). Mei takes incident commander. Support reports customers saying the "
                  "booking page spins when they pick a date.", "Mei"),
        ("14:31", "Tom rolls api back to the previous deploy, d-4466. The code goes back, but the dropped index does "
                  "not come back with it.", "Tom"),
        ("14:38", "Latency has not recovered seven minutes after the rollback. Tom pages Ravi, because the database "
                  "now needs the owner's decision.", "Tom"),
        ("14:44", "Ravi joins and finds the background index build at 41 %, with about 35 minutes left at its current "
                  "speed.", "Ravi"),
        ("14:52", "Ravi decides not to recreate the old index by hand, because two index builds would compete for "
                  "the same disk. The team waits for the build.", "Ravi"),
        ("15:06", "Support has 190 tickets so far. Mei posts a notice on status.sorrel.app that date search is slow "
                  "and that bookings still go through.", "Mei"),
        ("15:19", "The new index finishes building. p95 for the availability endpoint falls to 240 ms within two "
                  "minutes.", "Ravi"),
        ("15:24", "Ravi deploys d-4471 again, so the code matches the new index.", "Ravi"),
        ("15:40", "Mei closes the incident after 15 minutes of normal latency and updates the status page.", "Mei"),
    ],
    "well": ["Tom connected the slow queries to the 18-minute-old deploy within seven minutes of the page.",
             "Ravi's call not to build a second index by hand kept the disk from becoming the next problem."],
    "badly": ["The migration dropped the old index before the new one existed. Rolling back the code could not undo "
              "that, and nobody on the incident knew it until the rollback had failed.",
              "The api-wide p95 alert hid how slow the availability endpoint alone had become."],
    "actions": [
        ("Never drop an index in the same deploy that builds its replacement: drop the old one in a later deploy, "
         "after the new one is ready.", "Ravi", "2024-07-19", "Done"),
        ("Run index builds on tables over 10 million rows outside 09:00 to 21:00 JST.", "Ravi", "2024-07-26", "Done"),
        ("Give the availability endpoint its own p95 alert, separate from the api-wide one.", "Tom", "2024-08-02",
         "Open"),
        ("Add a line to the api runbook: a rollback does not undo a migration.", "Ravi", "2024-07-31", "Done"),
    ],
    "facts": ["2024-07-09", "SEV-2", "Final, reviewed 2024-07-11", "d-4471", "migration 0193", "d-4466",
              "69 minutes", "212 tickets", "about 35 %", "92 %", "41 %", "240 ms"],
}

DOCS["postmortem-payments-duplicate-refunds"] = {
    "kind": "postmortem",
    "title": "Postmortem: refunds sent twice after the refund job restarted",
    "crumb": "Sorrel Engineering / Postmortems / 2023",
    "meta": [("Incident date", "2023-10-24 (Tuesday, morning JST)"), ("Severity", "SEV-1"), ("Service", "payments"),
             ("Incident commander", "Ravi"), ("Author", "Mei"), ("Status", "Final, reviewed 2023-10-26")],
    "summary": "The daily refund job lost its database connection partway through its 10:00 run. The scheduler "
               "started it again from the beginning, and because the job built each refund's idempotency key from "
               "the time the run started, stripe treated the repeated requests as new refunds. 400 refunds went out "
               "twice, worth ¥2,836,400 in total. The extra refunds were written off; no customer was charged again.",
    "impact": ["Money: 400 refunds sent twice, ¥2,836,400 in total, written off by decision of Mei and finance on "
               "2023-10-24.",
               "Customers: none charged. 400 customers received an extra refund, and all 1,318 refunds in the run "
               "arrived at least once.",
               "Businesses: 9 businesses wrote to support about refund lines they did not expect.",
               "Data: none exposed or lost."],
    "timeline": [
        ("10:00", "The daily refund job starts. It sends the 1,318 refunds approved the day before to stripe in "
                  "batches of 50.", "refund job"),
        ("10:07", "The job's connection to the payments database drops during batch 9. The job exits, and the "
                  "scheduler starts it again from the beginning.", "scheduler"),
        ("10:08", "The second run sends batches 1 to 8 again. stripe accepts them as new refunds, because the "
                  "idempotency keys are built from the run's start time.", "refund job"),
        ("10:19", "The second run finishes all 27 batches. 400 refunds have now gone out twice.", "refund job"),
        ("10:26", "Support receives the first message from a business: a customer was refunded twice for the same "
                  "cancelled lesson.", "Support"),
        ("10:31", "Tom, on call, sees the support message in #inc-live and opens the refund job's logs, which show "
                  "two runs starting at 10:00 and 10:07.", "Tom"),
        ("10:36", "Money has already moved, so Tom pages Mei as the payments owner and changes nothing himself.",
         "Tom"),
        ("10:41", "Mei acknowledges and pauses the refund job in the scheduler, so no third run can start.", "Mei"),
        ("10:49", "Incident declared (SEV-1). Ravi takes incident commander.", "Ravi"),
        ("11:05", "Mei counts the duplicates from the stripe dashboard export: 400 refunds sent twice, ¥2,836,400 in "
                  "total.", "Mei"),
        ("11:12", "Ravi updates status.sorrel.app: refunds are paused while a payments problem is fixed; charges at "
                  "checkout work normally.", "Ravi"),
        ("12:15", "Mei and finance decide the extra refunds stay with the customers and are written off. No customer "
                  "will be charged again.", "Mei"),
        ("13:40", "Mei changes the idempotency key to use the refund id instead of the run's start time. Ravi reviews "
                  "the change and it is deployed.", "Mei"),
        ("14:10", "The fixed job is run against a copy of the day's list in the stripe test account. No refund is "
                  "sent twice.", "Mei"),
        ("14:35", "Incident closed. Refunds resume with the next daily run, on 2023-10-25 at 10:00.", "Ravi"),
    ],
    "well": ["Tom did not try to reverse anything himself; money had moved, so he paged Mei, as the handbook says.",
             "The stripe dashboard export made the duplicates countable within half an hour."],
    "badly": ["The scheduler restarted a job that moves money from the beginning, with no check of what the first "
              "run had already sent.",
              "Nothing on our side noticed; a business told support 19 minutes after the second run began."],
    "actions": [
        ("Build the refund idempotency key from the refund id, never from the run's start time.", "Mei",
         "2023-10-24", "Done"),
        ("Make the scheduler alert instead of restarting a job that moves money.", "Mei", "2023-11-03", "Done"),
        ("Add a daily check that no refund id was sent to stripe twice.", "Ravi", "2023-11-10", "Done"),
        ("Write down in the payments runbook how to pause a job that moves money.", "Mei", "2023-11-17", "Open"),
    ],
    "facts": ["2023-10-24", "SEV-1", "Final, reviewed 2023-10-26", "1,318 refunds", "batches of 50", "batch 9",
              "400 refunds", "¥2,836,400", "27 batches", "9 businesses", "2023-10-25 at 10:00"],
}

DOCS["postmortem-web-firewall-challenge"] = {
    "kind": "postmortem",
    "title": "Postmortem: booking pages behind a firewall challenge",
    "crumb": "Sorrel Engineering / Postmortems / 2025",
    "meta": [("Incident date", "2025-05-20 (Tuesday, afternoon JST)"), ("Severity", "SEV-2"), ("Service", "web"),
             ("Incident commander", "Mei"), ("Author", "Aiko"), ("Status", "Final, reviewed 2025-05-22")],
    "summary": "A firewall rule Aiko added on cloudflare at 16:02 to slow down a scraper also challenged first-time "
               "visitors on booking pages, because they arrive without a session cookie. Most of them left at the "
               "challenge page. No alert fired, since errors and latency stayed normal; support tickets and the "
               "booking-start panel showed it. Aiko switched the rule to log only at 16:58. About 2,300 booking "
               "starts were lost.",
    "impact": ["Customers: first-time visitors to booking pages saw a challenge page between 16:02 and 16:58 JST. "
               "Returning customers with a session were not affected.",
               "Booking starts from new visitors fell by 62 % against the same hour the week before; about 2,300 "
               "booking starts were lost.",
               "Support counted 26 reports, most from businesses whose new customers could not book.",
               "Money and data: none affected."],
    "timeline": [
        ("16:02", "Aiko turns on a new cloudflare firewall rule to slow a scraper: requests to /book/* without a "
                  "session cookie get a challenge page.", "Aiko"),
        ("16:05", "First-time visitors arriving from search results start getting the challenge page instead of the "
                  "booking page. Most of them leave.", "cloudflare"),
        ("16:21", "First customer report through support: a physiotherapy clinic says new patients cannot open its "
                  "booking page.", "Support"),
        ("16:28", "After a second report, Tom, on call, checks the \"Sorrel / web\" board: booking starts from new "
                  "visitors are 62 % below the same hour last week. No alert has fired, because errors and latency "
                  "are normal.", "Tom"),
        ("16:34", "Incident declared (SEV-2). Mei takes incident commander.", "Mei"),
        ("16:39", "Tom checks the deploy tool. The last web deploy is 2 days old, so a rollback would not help.",
         "Tom"),
        ("16:44", "Tom finds 14,950 challenges on /book/* in the cloudflare firewall events since 16:02, against "
                  "about 300 on a normal afternoon.", "Tom"),
        ("16:47", "Firewall rules are never changed without Aiko, so Tom pages her with the firewall events and the "
                  "booking-start panel.", "Tom"),
        ("16:58", "Aiko acknowledges, recognises her rule from 16:02, and switches it to log only.", "Aiko"),
        ("17:01", "Challenges on /book/* fall back to normal. Booking starts from new visitors recover within ten "
                  "minutes.", "Tom"),
        ("17:15", "Mei posts on status.sorrel.app that some new visitors could not open booking pages between 16:02 "
                  "and 16:58.", "Mei"),
        ("17:40", "Aiko rewrites the rule to match only the scraper's user agent and address range, and leaves it in "
                  "log-only mode for a day.", "Aiko"),
        ("18:30", "Incident closed. About 2,300 booking starts were lost in the 56 minutes the rule was active.",
         "Mei"),
    ],
    "well": ["Tom ruled out a bad deploy in one look at the deploy tool and went to the firewall events next.",
             "Nobody changed the firewall rule but Aiko, as the handbook asks."],
    "badly": ["No alert fired. Errors and latency were normal, so only support tickets showed that customers were "
              "being turned away.",
              "The rule went straight to challenge mode, with no log-only period to show who it would catch."],
    "actions": [
        ("Alert when booking starts from new visitors fall more than 40 % below the same hour last week.", "Aiko",
         "2025-05-30", "Open"),
        ("Run every new firewall rule in log-only mode for 24 hours before it blocks or challenges anything.",
         "Aiko", "2025-05-23", "Done"),
        ("Add the firewall events panel to the \"Sorrel / web\" board.", "Tom", "2025-06-06", "Done"),
        ("Ask the scraper's operator to use the partner API instead.", "Ravi", "2025-06-13", "Open"),
    ],
    "facts": ["2025-05-20", "SEV-2", "Final, reviewed 2025-05-22", "14,950 challenges", "62 %", "2,300 booking starts",
              "56 minutes", "26 reports", "2 days old", "/book/*"],
}

# F: revision 2 of the firewall postmortem. ONE timeline time corrected, ONE action item marked done. Nothing else.
REV2 = {"base": "postmortem-web-firewall-challenge", "slug": "postmortem-web-firewall-challenge.rev2",
        "time_fix": ("17:01", "17:03"), "action_done": 0}

DOCS["provider-cloudflare-japan-edge"] = {
    "kind": "provider",
    "title": "Incident report: elevated errors at edge locations in Japan",
    "byline": "cloudflare · Customer incident report · Published 2024-09-20",
    "meta": [("Incident", "2024-0917-A"), ("Date", "2024-09-17"), ("Status", "Resolved"),
             ("Products", "CDN, proxy"), ("Prepared for", "Sorrel")],
    "left": [("Summary", "Between 05:42 and 06:40 UTC on 2024-09-17, customers whose visitors were served from our "
                         "Tokyo and Osaka edge locations saw elevated HTTP 502 and 504 errors and higher latency. At "
                         "the worst point, 7.4 % of proxied requests in Tokyo failed. Part of the traffic was "
                         "rerouted to Seoul, which kept most requests working but added latency for visitors in "
                         "Japan."),
             ("Customer impact", "Errors began at 05:42 UTC. Tokyo was affected for 37 minutes and Osaka for 27 "
                                 "minutes. Cache purge requests for zones served from Tokyo were delayed by up to 9 "
                                 "minutes until 07:03 UTC. No customer data was lost or exposed, and no configuration "
                                 "on customer accounts was changed.")],
    "right": [("Root cause", "At 05:38 UTC an automated change to the load balancing on a backbone link between "
                             "Tokyo and Osaka was released to production. The change set a weight of zero for one of "
                             "the two link groups, which sent all traffic between the two sites over a single group "
                             "and saturated it. Health checks then marked healthy servers as unreachable, which "
                             "caused the 502 and 504 errors."),
              ("Remediation", "Our network team identified the change at 06:09 UTC and reverted it at 06:14 UTC. "
                              "Errors in Tokyo were back to normal levels by 06:19 UTC. We are adding a validation "
                              "step that rejects zero weights on backbone links, and changes to backbone load "
                              "balancing will be released to one site at a time. Both changes will be complete by "
                              "2024-10-31.")],
    "table_title": "Affected windows (all times UTC, 2024-09-17)",
    "windows": [
        ("05:42", "06:19", "Tokyo (NRT)", "HTTP 502 and 504 errors on proxied requests, up to 7.4 % of requests"),
        ("05:44", "06:11", "Osaka (KIX)", "HTTP 502 errors on proxied requests, up to 3.1 % of requests"),
        ("05:51", "06:05", "Fukuoka (FUK)", "Higher latency, p95 up to 1.8 s; error rate normal"),
        ("06:02", "06:40", "Seoul (ICN)", "Traffic rerouted from Tokyo; higher latency for visitors in Japan"),
        ("06:21", "07:03", "Tokyo (NRT)", "Cache purge requests delayed by up to 9 minutes"),
    ],
    "closing": "Questions about this report: contact your account team and quote incident 2024-0917-A.",
    "facts": ["2024-0917-A", "05:42 UTC", "37 minutes", "27 minutes", "7.4 %", "05:38 UTC", "06:09 UTC", "06:14 UTC",
              "06:19 UTC", "2024-10-31", "3.1 %", "1.8 s"],
}

DOCS["scan-dr-drill-2023"] = {
    "kind": "scan",
    "title": "Backup restore drill report: api database",
    "byline": "Sorrel platform team · Drill DR-2023-02",
    "meta": [("Drill", "DR-2023-02"), ("Date", "2023-06-13 (Tuesday)"),
             ("Scope", "Restore the api primary database from the nightly backup into the restore account in "
                       "eu-west-1"),
             ("Recovery point", "Nightly backup of 2023-06-13 01:00 JST"), ("Drill lead", "Ravi"),
             ("Observer", "Mei")],
    "table_title": "Results",
    "table_head": ("Step", "Target", "Actual", "Result"),
    "rows": [
        ("1. Find the latest nightly backup in object storage", "10 min", "6 min", "Pass"),
        ("2. Copy the backup to the restore account in eu-west-1", "45 min", "38 min", "Pass"),
        ("3. Restore the database from the backup", "90 min", "2 h 04 min", "Fail"),
        ("4. Check row counts against the production snapshot", "20 min", "17 min", "Pass"),
        ("5. Start api against the restored database and make a test booking", "30 min", "22 min", "Pass"),
        ("Total time to a working api", "4 h", "3 h 27 min", "Pass"),
    ],
    "notes": ["Step 3 was slow because the restore used the default instance size. The bookings table came back with "
              "41,880,112 rows, matching the production snapshot exactly.",
              "Follow-up: restore to a larger instance size and repeat the drill in December."],
    "signatures": [("Drill lead", "Ravi", "2023-06-15"), ("Reviewed", "Mei", "2023-06-16")],
    "facts": ["DR-2023-02", "2023-06-13", "eu-west-1", "2 h 04 min", "3 h 27 min", "41,880,112 rows", "2023-06-15",
              "2023-06-16"],
}

DOCS["scan-twilio-maintenance-2025"] = {
    "kind": "scan",
    "title": "Scheduled maintenance: Messaging API, Tokyo region",
    "byline": "twilio · Maintenance notice · Sent 2025-02-04",
    "meta": [("Reference", "MNT-58213"), ("Window (JST)", "2025-02-18 02:00 to 04:00 JST"),
             ("Window (UTC)", "2025-02-17 17:00 to 19:00 UTC"), ("Action required", "None")],
    "paras": ["We will carry out planned maintenance on the Messaging API in our Tokyo region. During the window, SMS "
              "sends may be delayed by up to 10 minutes. Messages will be queued, not dropped. Delivery receipts may "
              "arrive up to 30 minutes late.",
              "If you have questions about this maintenance, reply to this notice and quote reference MNT-58213."],
    "table_title": "Affected products",
    "table_head": ("Product", "Expected impact"),
    "rows": [
        ("Messaging API: SMS to Japanese numbers", "Sends delayed by up to 10 minutes"),
        ("Delivery receipts (status callbacks)", "Up to 30 minutes late"),
        ("One-time sign-in codes sent as SMS", "Delayed by up to 10 minutes"),
        ("Voice", "Not affected"),
    ],
    "handnote": "notifier deploy freeze booked for this window. Tom 2/5",
    "facts": ["MNT-58213", "2025-02-18 02:00 to 04:00 JST", "2025-02-17 17:00 to 19:00 UTC", "up to 10 minutes",
              "up to 30 minutes", "2025-02-04"],
}

DOCS["scan-escalation-sheet"] = {
    "kind": "scan",
    "title": "On-call escalation sheet",
    "byline": "Printed 2024-04-01 · keep next to the desk phone · replace when the owners change",
    "table_title": "",
    "table_head": ("Role", "Name", "Extension", "Call for"),
    "rows": [
        ("web owner", "Aiko", "ext. 4411", "Front-end releases, CDN and firewall, admin tool, account deletions and "
                                           "restores"),
        ("api owner", "Ravi", "ext. 4417", "Booking logic, the database, partner integrations, the audit log"),
        ("payments owner", "Mei", "ext. 4423", "Charges, refunds, payouts, payment provider settings"),
        ("notifier owner", "Tom", "ext. 4429", "Email and SMS sending, templates, vendor sending limits"),
        ("Incident commander desk", "the IC on the rotation", "ext. 4400",
         "Any P1 open for 15 minutes; an owner who has not answered in 10 minutes"),
        ("Platform team desk", "whoever is on the desk", "ext. 4450",
         "Deploy tool, paging tool, metrics and log search access (weekdays 10:00 to 18:00 JST)"),
        ("Support lead", "the support lead on shift", "ext. 4460", "Customer and business messages during an incident"),
    ],
    "paras": ["If the paging tool itself is down: call the owner's extension first, then the incident commander desk "
              "on ext. 4400. Write every call in the incident thread.",
              "Sheet owner: Ravi. Next review: 2024-10-01."],
    "facts": ["2024-04-01", "ext. 4417", "ext. 4400", "ext. 4429", "ext. 4450", "ext. 4460", "2024-10-01",
              "15 minutes", "10 minutes"],
}

SCAN_PARAMS = {   # recorded in PROVENANCE.json; office-scanner degradation, one setting per sheet
    "scan-dr-drill-2023": {"dpi": 200, "rotate_deg": 0.7, "blur_radius": 0.6, "noise_sigma": 6.0, "paper": 236,
                           "jpeg_quality": 74, "seed": 11},
    "scan-twilio-maintenance-2025": {"dpi": 200, "rotate_deg": -0.5, "blur_radius": 0.5, "noise_sigma": 5.0,
                                     "paper": 240, "jpeg_quality": 78, "seed": 12},
    "scan-escalation-sheet": {"dpi": 200, "rotate_deg": 1.1, "blur_radius": 0.7, "noise_sigma": 7.0, "paper": 232,
                              "jpeg_quality": 71, "seed": 13},
}

# Which page each table row and key fact sits on. Read BY EYE from 55-80 dpi renders of the frozen PDFs
# (library/pdf/build/preview-*), before any text extractor ran. Rows not listed sit on page 1.
PAGE_MAP = {
    "postmortem-notifier-reminder-backlog": {"pages": 2, "timeline_p1": 6, "facts_p2": ["300 messages a minute", "2023-04-14"]},
    "postmortem-api-index-migration": {"pages": 2, "timeline_p1": 6, "facts_p2": ["d-4466", "41 %", "240 ms"]},
    "postmortem-payments-duplicate-refunds": {"pages": 2, "timeline_p1": 7, "facts_p2": ["2023-10-25 at 10:00"]},
    "postmortem-web-firewall-challenge": {"pages": 2, "timeline_p1": 7, "facts_p2": ["56 minutes"]},
    "postmortem-web-firewall-challenge.rev2": {"pages": 2, "timeline_p1": 7, "facts_p2": ["56 minutes"]},
    "provider-cloudflare-japan-edge": {"pages": 1},
    "scan-dr-drill-2023": {"pages": 1},
    "scan-twilio-maintenance-2025": {"pages": 1},
    "scan-escalation-sheet": {"pages": 1},
}


def cmd_pages():
    """write the page of every row and fact into each truth file (truth only; PDFs untouched)"""
    for slug, m in PAGE_MAP.items():
        path = os.path.join(OUT, slug + ".truth.json")
        t = json.load(open(path))
        t["pages"] = m["pages"]
        for tab in t["tables"]:
            n = len(tab["rows"])
            if tab["name"] == "timeline":
                tab["page_of_row"] = [1 if i < m["timeline_p1"] else 2 for i in range(n)]
            elif tab["name"] == "actions":
                tab["page_of_row"] = [2] * n
            else:
                tab["page_of_row"] = [1] * n
        for f in t["facts"]:
            f["page"] = 2 if f["text"] in m.get("facts_p2", []) else 1
        t["page_map_how"] = "by eye from low-resolution renders of the frozen PDF, before any extractor ran"
        json.dump(t, open(path, "w"), indent=1, ensure_ascii=False)
        print("pages", slug, m["pages"])


# ------------------------------------------------------------------ HTML

CSS = """
@page { size: A4; margin: 20mm 18mm 20mm 18mm; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 10.5pt; line-height: 1.38; color: #202124; margin: 0; }
.crumb { font-size: 8.5pt; color: #5f6368; margin-bottom: 6pt; }
h1 { font-size: 19pt; font-weight: normal; margin: 0 0 10pt 0; color: #111; }
h2 { font-size: 13pt; font-weight: bold; margin: 16pt 0 5pt 0; color: #111; }
p { margin: 0 0 7pt 0; }
ul { margin: 0 0 7pt 0; padding-left: 20pt; }
li { margin-bottom: 3pt; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; line-height: 1.32; }
th, td { border: 1px solid #b7b7b7; padding: 4pt 6pt; text-align: left; vertical-align: top; }
th { background: #efefef; font-weight: bold; }
tr { break-inside: avoid; }
table.meta { width: 72%; margin-bottom: 4pt; }
table.meta td.k { background: #f3f3f3; font-weight: bold; width: 34%; }
col.time { width: 11%; } col.what { width: 69%; } col.who { width: 20%; }
col.item { width: 62%; } col.owner { width: 12%; } col.due { width: 14%; } col.status { width: 12%; }
"""

CSS_PROVIDER = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 9.5pt; line-height: 1.4; color: #1d1d1d; margin: 0; }
.byline { font-size: 8.5pt; color: #6b6b6b; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4pt; }
h1 { font-size: 18pt; margin: 0 0 8pt 0; font-weight: bold; }
h2 { font-size: 11pt; margin: 10pt 0 4pt 0; }
p { margin: 0 0 7pt 0; text-align: justify; }
.cols { column-count: 2; column-gap: 9mm; margin-top: 8pt; }
.cols h2:first-child { margin-top: 0; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; }
th, td { border-bottom: 1px solid #c8c8c8; padding: 4pt 5pt; text-align: left; vertical-align: top; }
th { border-bottom: 1.5px solid #333; }
tr { break-inside: avoid; }
table.meta { width: 60%; margin: 6pt 0 0 0; }
table.meta td { border: none; padding: 1pt 4pt 1pt 0; }
table.meta td.k { color: #6b6b6b; width: 30%; }
.closing { margin-top: 10pt; font-size: 8.5pt; color: #444; }
"""

CSS_SCAN = """
@page { size: A4; margin: 22mm 20mm 22mm 20mm; }
body { font-family: "Times New Roman", Times, serif; font-size: 11pt; line-height: 1.35; color: #000; margin: 0; }
.byline { font-size: 9.5pt; margin-bottom: 8pt; }
h1 { font-size: 17pt; margin: 0 0 6pt 0; }
h2 { font-size: 12.5pt; margin: 14pt 0 5pt 0; }
p { margin: 0 0 7pt 0; }
table { border-collapse: collapse; width: 100%; font-size: 10.5pt; }
th, td { border: 1px solid #000; padding: 4pt 6pt; text-align: left; vertical-align: top; }
tr { break-inside: avoid; }
table.meta td.k { font-weight: bold; width: 28%; }
.sig { margin-top: 26pt; display: flex; gap: 18mm; }
.sig div { flex: 1; border-top: 1px solid #000; padding-top: 3pt; font-size: 10pt; position: relative; }
.hand { font-family: "Bradley Hand", "Brush Script MT", cursive; font-size: 20pt; position: absolute; top: -30pt;
        left: 6pt; color: #1a2a6c; }
.handnote { font-family: "Bradley Hand", cursive; font-size: 15pt; color: #1a2a6c; margin-top: 18pt;
            transform: rotate(-3deg); }
"""

e = html.escape


def rows_html(rows, head, cols=None):
    colgroup = "<colgroup>" + "".join(f'<col class="{c}">' for c in cols) + "</colgroup>" if cols else ""
    thead = "<thead><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr></thead>"
    body = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table>{colgroup}{thead}<tbody>{body}</tbody></table>"


def meta_html(meta):
    return '<table class="meta"><tbody>' + "".join(
        f'<tr><td class="k">{e(k)}</td><td>{e(v)}</td></tr>' for k, v in meta) + "</tbody></table>"


def page(title, css, body):
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>{e(title)}</title>'
            f"<style>{css}</style></head><body>\n{body}\n</body></html>\n")


def postmortem_html(d):
    b = [f'<div class="crumb">{e(d["crumb"])}</div>', f"<h1>{e(d['title'])}</h1>", meta_html(d["meta"]),
         "<h2>Summary</h2>", f"<p>{e(d['summary'])}</p>",
         "<h2>Impact</h2>", "<ul>" + "".join(f"<li>{e(x)}</li>" for x in d["impact"]) + "</ul>",
         "<h2>Timeline (JST)</h2>", rows_html(d["timeline"], ("Time", "What happened", "Who"), ("time", "what", "who")),
         "<h2>What went well</h2>", "<ul>" + "".join(f"<li>{e(x)}</li>" for x in d["well"]) + "</ul>",
         "<h2>What went badly</h2>", "<ul>" + "".join(f"<li>{e(x)}</li>" for x in d["badly"]) + "</ul>",
         "<h2>Action items</h2>",
         rows_html(d["actions"], ("Action", "Owner", "Due", "Status"), ("item", "owner", "due", "status"))]
    return page(d["title"], CSS, "\n".join(b))


def provider_html(d):
    cols = "".join(f"<h2>{e(h)}</h2><p>{e(t)}</p>" for h, t in d["left"] + d["right"])
    b = [f'<div class="byline">{e(d["byline"])}</div>', f"<h1>{e(d['title'])}</h1>", meta_html(d["meta"]),
         f'<div class="cols">{cols}</div>', f"<h2>{e(d['table_title'])}</h2>",
         rows_html(d["windows"], ("Start", "End", "Location", "Impact")),
         f'<p class="closing">{e(d["closing"])}</p>']
    return page(d["title"], CSS_PROVIDER, "\n".join(b))


def scan_html(d):
    b = [f"<h1>{e(d['title'])}</h1>", f'<div class="byline">{e(d["byline"])}</div>']
    if d.get("meta"):
        b.append(meta_html(d["meta"]))
    if d.get("paras") and d["title"].startswith("Scheduled"):
        b.append(f"<p style='margin-top:10pt'>{e(d['paras'][0])}</p>")
    if d.get("table_title"):
        b.append(f"<h2>{e(d['table_title'])}</h2>")
    else:
        b.append("<div style='height:8pt'></div>")
    b.append(rows_html(d["rows"], d["table_head"]))
    for n in d.get("notes", []):
        b.append(f"<p style='margin-top:8pt'>{e(n)}</p>")
    paras = d.get("paras", [])
    for ptxt in (paras[1:] if d["title"].startswith("Scheduled") else paras):
        b.append(f"<p style='margin-top:8pt'>{e(ptxt)}</p>")
    if d.get("signatures"):
        b.append('<div class="sig">' + "".join(
            f'<div><span class="hand">{e(name)}</span>{e(role)}: {e(name)} &nbsp; Date: {e(date)}</div>'
            for role, name, date in d["signatures"]) + "</div>")
    if d.get("handnote"):
        b.append(f'<div class="handnote">{e(d["handnote"])}</div>')
    return page(d["title"], CSS_SCAN, "\n".join(b))


def rev2(d):
    d = json.loads(json.dumps(d))
    old, new = REV2["time_fix"]
    d["timeline"] = [[new if t == old else t, w, p] for t, w, p in d["timeline"]]
    a = d["actions"][REV2["action_done"]]
    d["actions"][REV2["action_done"]] = [a[0], a[1], a[2], "Done"]
    return d


def render(slug, d):
    return {"postmortem": postmortem_html, "provider": provider_html, "scan": scan_html}[d["kind"]](d)


# ------------------------------------------------------------------ truth


def visible_text(h):
    """the HTML's visible text, whitespace collapsed: what a perfect extractor would give"""
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S)
    h = re.sub(r"<title>.*?</title>", " ", h, flags=re.S)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


def tables(d):
    """every table in the document, every row as its cells, in document order"""
    if d["kind"] == "postmortem":
        return [{"name": "meta", "rows": [list(r) for r in d["meta"]]},
                {"name": "timeline", "rows": [list(r) for r in d["timeline"]]},
                {"name": "actions", "rows": [list(r) for r in d["actions"]]}]
    if d["kind"] == "provider":
        return [{"name": "meta", "rows": [list(r) for r in d["meta"]]},
                {"name": "windows", "rows": [list(r) for r in d["windows"]]}]
    out = []
    if d.get("meta"):
        out.append({"name": "meta", "rows": [list(r) for r in d["meta"]]})
    out.append({"name": "main", "rows": [list(r) for r in d["rows"]]})
    return out


def truth(slug, d, pages_of=None):
    text = visible_text(render(slug, d))
    for f in d["facts"]:
        assert f in text, (slug, f)
    for t in tables(d):
        for r in t["rows"]:
            for c in r:
                assert c in text, (slug, c)
    return {"slug": slug, "title": d["title"], "kind": d["kind"],
            "written": "from the HTML's source data, before any extractor ran",
            "pages": None, "tables": tables(d), "facts": [{"text": f, "page": None} for f in d["facts"]],
            "source_text": text}


def cmd_html():
    os.makedirs(OUT, exist_ok=True)
    for slug, d in DOCS.items():
        open(os.path.join(OUT, slug + ".html"), "w").write(render(slug, d))
        json.dump(truth(slug, d), open(os.path.join(OUT, slug + ".truth.json"), "w"), indent=1, ensure_ascii=False)
        print("html + truth", slug)
    d2 = rev2(DOCS[REV2["base"]])
    open(os.path.join(OUT, REV2["slug"] + ".html"), "w").write(render(REV2["slug"], d2))
    json.dump(truth(REV2["slug"], d2), open(os.path.join(OUT, REV2["slug"] + ".truth.json"), "w"), indent=1,
              ensure_ascii=False)
    print("html + truth", REV2["slug"])


# ------------------------------------------------------------------ PDF


def chrome_print(html_path, pdf_path):
    """Headless Chrome with its own fresh profile. On this Mac it writes the PDF in about a second and then never
    exits, so once its own log says the bytes are written and the file ends in %%EOF, only THIS instance (matched by
    its unique temp profile path) is stopped. The user's running Chrome is never touched."""
    with tempfile.TemporaryDirectory(prefix="ep11-chrome-") as prof:
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={prof}",
               "--use-mock-keychain", "--password-store=basic",
               "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", "file://" + html_path]
        t0 = time.time()
        log_path = os.path.join(prof, "chrome.log")
        with open(log_path, "w") as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=log)
            written = False
            while time.time() - t0 < 60:
                time.sleep(0.5)
                txt = open(log_path, errors="replace").read()
                if ("bytes written to file" in txt and os.path.exists(pdf_path)
                        and open(pdf_path, "rb").read()[-8:].strip().endswith(b"%%EOF")):
                    written = True
                    break
                if proc.poll() is not None:
                    break
            line = next((l for l in open(log_path, errors="replace") if "bytes written" in l), "").strip()
            exited_alone = proc.poll() is not None
            if not exited_alone:
                subprocess.run(["pkill", "-TERM", "-f", f"user-data-dir={prof}"])
                proc.wait(timeout=20)
    return {"cmd": [c if not c.startswith("--user-data-dir=") else "--user-data-dir=<fresh temp dir>" for c in cmd],
            "written": written, "chrome_says": line, "secs_to_pdf": round(time.time() - t0, 1),
            "exited_on_its_own": exited_alone}


def cmd_pdf(only=None):
    log = {}
    for slug, d in list(DOCS.items()) + [(REV2["slug"], None)]:
        if only and slug not in only:
            continue
        if d is not None and d["kind"] == "scan":
            continue
        pdf = os.path.join(OUT, slug + ".pdf")
        if os.path.exists(pdf):
            print("exists, not overwritten:", slug)
            continue
        log[slug] = chrome_print(os.path.join(OUT, slug + ".html"), pdf)
        print(slug, log[slug]["written"], log[slug]["secs_to_pdf"], os.path.getsize(pdf))
    json.dump(log, open(os.path.join(BUILD if os.path.isdir(BUILD) else OUT, "chrome-log.json"), "w"), indent=1)


def cmd_scan():
    import numpy as np
    from PIL import Image, ImageFilter
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    os.makedirs(BUILD, exist_ok=True)
    steps = {}
    for slug, p in SCAN_PARAMS.items():
        out_pdf = os.path.join(OUT, slug + ".pdf")
        if os.path.exists(out_pdf):
            print("exists, not overwritten:", slug)
            continue
        printed = os.path.join(BUILD, slug + ".printed.pdf")
        steps[slug] = {"1_print": chrome_print(os.path.join(OUT, slug + ".html"), printed)}
        prefix = os.path.join(BUILD, slug + ".raster")
        cmd = ["pdftoppm", "-r", str(p["dpi"]), "-gray", "-png", printed, prefix]
        subprocess.run(cmd, check=True)
        steps[slug]["2_rasterise"] = " ".join(cmd)
        rasters = sorted(f for f in os.listdir(BUILD) if f.startswith(slug + ".raster") and f.endswith(".png"))
        rng = np.random.default_rng(p["seed"])
        jpgs = []
        for i, f in enumerate(rasters):
            im = Image.open(os.path.join(BUILD, f)).convert("L")
            im = im.rotate(p["rotate_deg"], resample=Image.BICUBIC, expand=False, fillcolor=255)
            im = im.filter(ImageFilter.GaussianBlur(p["blur_radius"]))
            a = np.asarray(im).astype(np.float32)
            a = a * (p["paper"] / 255.0)                                      # off-white paper
            a = a + rng.normal(0, p["noise_sigma"], a.shape)                  # sensor noise
            im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L")
            jpg = os.path.join(BUILD, f"{slug}.scan-{i + 1}.jpg")
            im.save(jpg, "JPEG", quality=p["jpeg_quality"])
            jpgs.append(jpg)
        c = canvas.Canvas(out_pdf, pagesize=A4)
        for jpg in jpgs:
            c.drawImage(jpg, 0, 0, width=A4[0], height=A4[1])
            c.showPage()
        c.save()
        steps[slug]["3_degrade"] = {k: v for k, v in p.items() if k != "dpi"}
        steps[slug]["3_degrade"]["order"] = ("rotate (bicubic, white fill) -> GaussianBlur -> multiply by paper/255 "
                                             "-> add N(0, noise_sigma) -> JPEG at jpeg_quality")
        steps[slug]["4_wrap"] = "reportlab canvas.drawImage of each JPEG, full A4 page, no text layer"
        steps[slug]["pages"] = len(jpgs)
        print(slug, len(jpgs), "page(s)")
    json.dump(steps, open(os.path.join(BUILD, "scan-steps.json"), "w"), indent=1)


def md5f(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def cmd_freeze():
    from pypdf import PdfReader      # page count only; no text is read here
    prov_path = os.path.join(OUT, "PROVENANCE.json")
    prov = json.load(open(prov_path)) if os.path.exists(prov_path) else {"files": {}}
    for f in sorted(os.listdir(OUT)):
        if not f.endswith(".pdf"):
            continue
        slug = f[:-4]
        if slug in prov["files"]:
            assert prov["files"][slug]["md5"] == md5f(os.path.join(OUT, f)), f"{f} CHANGED after freeze"
            continue
        kind = "scan" if slug.startswith("scan-") else "rev2" if slug.endswith(".rev2") else "chrome"
        entry = {"file": f"library/pdf/{f}", "md5": md5f(os.path.join(OUT, f)),
                 "pages": len(PdfReader(os.path.join(OUT, f)).pages), "bytes": os.path.getsize(os.path.join(OUT, f)),
                 "html": f"library/pdf/{slug}.html", "html_md5": md5f(os.path.join(OUT, slug + ".html")),
                 "frozen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if kind == "scan":
            entry["generator"] = ("HTML -> headless Chrome --print-to-pdf (fresh --user-data-dir) -> pdftoppm -r 200 "
                                  "-gray -> degrade (PIL + numpy) -> reportlab drawImage, image only")
            entry["scan_params"] = SCAN_PARAMS[slug]
        else:
            entry["generator"] = ("HTML -> headless Chrome --headless=new --disable-gpu --no-first-run "
                                  "--user-data-dir=<fresh temp dir> --no-pdf-header-footer --print-to-pdf")
        prov["files"][slug] = entry
        print("frozen", slug, entry["md5"], entry["pages"], "page(s)")
    prov["chrome"] = subprocess.run([CHROME, "--version"], capture_output=True, text=True).stdout.strip()
    json.dump(prov, open(prov_path, "w"), indent=1)


if __name__ == "__main__":
    {"html": cmd_html, "pdf": lambda: cmd_pdf(sys.argv[2:]), "scan": cmd_scan, "freeze": cmd_freeze,
     "pages": cmd_pages}[sys.argv[1]]()
