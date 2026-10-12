"""EP12 harness, not episode code: the spec for the new pages and the 40 questions, written from ONE source.

    python3 measure/ep12_spec.py     # writes library/SPEC-ep12.json and tickets/questions-ep12.json

The planted facts (error codes, team-word facts, hidden facts) live here next to the question that asks about each,
so the question set is written before any page is drafted and before any measured call.
"""
import hashlib, json, os
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRITTEN = "2026-10-11, before any page was drafted and before any measured call"

EXISTING = {"2025-11-24", "2026-04-06", "2026-09-21", "2026-10-05"}
PEOPLE = {"Priya": "Priya (web)", "Leo": "Leo (payments)", "Yuki": "Yuki (notifier)", "Daniel": "Daniel (api)",
          "Sara": "Sara (platform)", "Noor": "Noor (SRE)"}

# ---------------------------------------------------------------- planted facts, by the note (page) that holds them
# Each planted fact names the page it lives in. A code appears in ONE or TWO notes only, in passing.

PLANTED = {
    # error codes
    "2025-10-13": ["NTF-3302 on 96 booking confirmation emails on Wednesday: sendgrid rejected them because the "
                   "template's first-name variable was empty for customers who booked as guests. Yuki changed the "
                   "templates to fall back to the business name when the first name is empty; shipped Friday."],
    "2025-10-20": ["PAY-4031 came back on Tuesday evening: the acquirer timed out on the 3-D Secure challenge and 41 "
                   "checkouts failed in about 25 minutes. The checkout waits 10 s for the 3-D Secure answer. Leo "
                   "opened a ticket; no change yet."],
    "2025-10-27": ["WEB-5106 on business logo uploads over 10 MB: working as designed (the limit is 10 MB). Support "
                   "already has a help article; nothing to do."],
    "2025-11-03": ["The PAY-4031 follow-up from two weeks ago is done: on Thursday Leo raised the 3-D Secure wait "
                   "from 10 s to 25 s. PAY-4031 has not come back since.",
                   "The US clock change on Sunday 2025-11-02 went clean this year. Daniel checked 212 bookings at "
                   "us-east businesses for the days around the change and every one showed the right time. No "
                   "customer reports."],
    "2025-11-10": ["Pool starvation on api in ap-northeast every night from about 02:50 to 03:30 JST: the nightly "
                   "analytics export held most of the connection pool on the primary database, so booking pages "
                   "slowed for those 40 minutes (api-pool did not fire; it stayed under 90 %). On Thursday Daniel "
                   "moved the export to read from the replica instead of the primary; Friday night was clean."],
    "2025-12-15": ["API-2210 rejections for one partner all week: they sent bookings for slots outside the "
                   "business's opening hours. That is the check doing its job; Ravi told the partner."],
    "2025-12-22": ["On Tuesday 2025-12-16 Tom raised the sendgrid daily quota on the marketing stream to 600,000 for "
                   "the year-end campaign; it goes back down on 2026-01-05. The transactional stream is unchanged."],
    "2025-12-29": ["The year-end payout on Sunday 2025-12-28 took 2 h 05 min instead of the usual 38 min, because of "
                   "year-end volume. It started at 23:00 JST and finished at 01:05 JST; Mei's team watched it. "
                   "Nothing failed."],
    "2026-01-12": ["PAY-4107 on three refunds on Thursday: the card provider refuses refunds on charges older than 180 "
                   "days. Mei's team paid those three customers back by bank transfer instead."],
    "2026-01-26": ["notifier.sms_batch_size went from 500 to 200 on Wednesday: twilio answered 429 (too many "
                   "requests) during the nightly reminder batch when we sent 500 at a time. Tom approved; the batch "
                   "now takes about 6 minutes longer and no 429s since."],
    "2026-02-02": ["N+1 queries on the week-view calendar endpoint: for businesses with 40 or more staff, api "
                   "fetched each staff member's bookings one query at a time, and the endpoint's p95 reached 6 s. "
                   "Daniel batched the staff lookups into one query on Thursday; p95 is now about 700 ms."],
    "2026-02-09": ["API-2387 errors in eu-west on Wednesday after a node replacement: search requests that landed on "
                   "the new node failed with a missing search shard. Daniel rebuilt the shard on that node (40 min). "
                   "Cause not known yet."],
    "2026-02-16": ["Cause of last week's API-2387: the replacement node came up from an old machine image that did "
                   "not mount the search shard volume. Sara fixed the image on Tuesday."],
    "2026-02-23": ["Game day on Thursday 2026-02-19: we moved api traffic out of eu-west (a region evacuation) and "
                   "back. Sara ran it; the evacuation took 41 minutes end to end, against a target of 30. Follow-up "
                   "tickets are with Ravi."],
    "2026-03-02": ["NTF-3318 from twilio on 58 reminders: the numbers were landlines, which cannot take SMS. Priya "
                   "is looking at the sign-up form."],
    "2026-03-09": ["Webhook replay storm on Tuesday: after stripe's incident cleared, stripe re-sent about 48,000 old "
                   "events in 20 minutes. payments-webhook-retry fired; the events are deduplicated by event id, so "
                   "we let it drain (about 35 minutes). No action needed beyond the log line."],
    "2026-03-16": ["Priya's sign-up form change shipped on Thursday: the form now checks that a phone number can take "
                   "SMS before it is saved. NTF-3318 is down to near zero."],
    "2026-03-23": ["The old v1 partner API endpoints were switched off on Wednesday 2026-03-18, after the last "
                   "partner moved to v2. About 3 calls a day still arrive on v1 from a test script at Hanabi "
                   "Booking; they get 410 and Ravi has told them."],
    "2026-04-20": ["Noor shadowed Sara all week: her first shadow shift.",
                   "Orphaned holds: when a customer leaves checkout, the slot should be released after 10 minutes, but "
                   "the hold reaper job had been paused since the api deploy on 2026-04-14, so abandoned slots stayed "
                   "held until the 30-minute safety timeout and showed as taken. Ravi restarted the reaper on Friday."],
    "2026-04-27": ["Noor shadowed Priya all week: her second shadow shift.",
                   "The new weekly restore test for the payments database started on Wednesday 2026-04-22: the "
                   "latest backup is restored into a scratch instance and checked. The first restore took 52 minutes. "
                   "Leo owns it."],
    "2026-05-04": ["Golden Week: booking volume peaked on Saturday 2026-05-02 at 1,960 bookings per minute on api, at "
                   "about 11:00 JST. No alerts."],
    "2026-05-11": ["Noor takes her first primary on-call shift on her own today, 2026-05-11, after her two shadow "
                   "shifts in April. Secondary this week: Sara."],
    "2026-05-18": ["PAY-4415 on one payout on Sunday night: the business's bank account had been closed. The payout "
                   "is held; Hana's team asked the business for new bank details."],
    "2026-05-25": ["A cloudflare firewall rule added on Tuesday for bot traffic also blocked Hanabi Booking's partner "
                   "sync, which runs from their Osaka servers, for about 2 hours. Aiko added Hanabi's IP range to the "
                   "rule's allow list."],
    "2026-06-01": ["WEB-5013 when Hana's team exported a business's full booking history from the admin tool: exports "
                   "over 50,000 rows timed out. Aiko's team changed large exports to run in the background and show "
                   "up in the admin tool's downloads list when ready; shipped Thursday."],
    "2026-06-08": ["A2P filtering by US carriers: twilio showed our reminders as delivered to the carrier, but about "
                   "11 % of SMS to US numbers never reached the phone. Tom approved registering our 10DLC campaign "
                   "with twilio; registration went through on Friday and delivery is back to normal."],
    "2026-06-22": ["web.session_idle_minutes went from 30 to 60 on Tuesday 2026-06-16, after support asked: "
                   "businesses were being signed out of the booking screen in the middle of the day. Aiko approved."],
    "2026-07-06": ["API-2502 for one partner's calendar sync on Monday: their sync token expired after they changed "
                   "the password on their side. They reconnected; nothing for us to do."],
    "2026-07-20": ["Token refresh stampede on Wednesday at 09:00 JST: every web session issued before the signing key "
                   "rotation expired at the same moment, so everyone had to sign in again at once and sign-in p95 "
                   "went to 9 s for 14 minutes. Priya added jitter so session expiry is spread out from now on."],
    "2026-08-10": ["A few NTF-3460 log lines on Tuesday: reminders dropped as duplicates by the dedupe key after a "
                   "worker retried. Expected; no customer missed a reminder."],
    "2026-08-17": ["The cloudflare edge cache hit ratio fell from 92 % to 61 % on Wednesday: image resize URLs started "
                   "carrying a timestamp query string, so every image looked new to the edge. Aiko set the cache key "
                   "to ignore that parameter; the ratio was back above 90 % by Thursday."],
    "2026-08-24": ["Stale locale in the template cache: after Tuesday's notifier template deploy, 1,140 reminders went "
                   "out in en for ja accounts over about 25 minutes, because the cache key did not include the "
                   "locale. Yuki added the locale to the cache key the same day."],
    "2026-08-31": ["WEB-5241 in the browser error panel: the content security policy blocked the support chat widget "
                   "after its script moved to a new domain. Priya added the new domain to the CSP allow list on "
                   "Thursday."],
    "2026-09-28": ["api and payments move to Shipyard, the new deploy pipeline, today (2026-09-28); the platform team "
                   "posts the Shipyard page today. Nothing else changes for on-call this week."],
}

# ---------------------------------------------------------------- new short team pages (each holds one team-word fact)

TEAM = [
    {"file": "library/team-payments-notes.md", "title": "payments: notes for on-call", "kind": "team page",
     "date": "2026-02-02", "owner": "Mei (payments)",
     "facts": ["Duplicate capture on 63 bookings on 2026-01-14: the capture call to stripe was retried after a "
               "timeout and both captures went through. Leo added an idempotency key to the capture call on "
               "2026-01-15. Mei's team refunded the second charge the same day.",
               "The weekly payout job runs on Sunday at 23:00 JST and usually takes about 38 minutes.",
               "Refund batches run daily at 23:30 JST.",
               "Webhooks from the card provider can arrive late, out of order, or more than once; payments is "
               "built to handle all three, so a few retries are not an incident."]},
    {"file": "library/team-notifier-notes.md", "title": "notifier: things we learned the hard way", "kind": "team page",
     "date": "2026-03-09", "owner": "Tom (notifier)",
     "facts": ["After the sending-domain switch on 2026-02-24, sendgrid's suppression list picked up 2,312 addresses "
               "from soft bounces during the switch, and sendgrid stopped sending to them. Yuki checked they were "
               "valid and removed them from the suppression list on 2026-02-26.",
               "The nightly reminder batch (02:00 to 04:00 JST) regularly pushes queue depth past 1,000; check "
               "delivered per minute before treating it as a stall.",
               "Email confirmations and SMS reminders use separate queues.",
               "Every reminder carries a dedupe key, reminder:<booking id>:<date>; notifier drops a message whose "
               "key it has seen in the last 24 hours."]},
    {"file": "library/team-web-notes.md", "title": "web: odd things we keep seeing", "kind": "team page",
     "date": "2026-07-13", "owner": "Aiko (web)",
     "facts": ["Tofu on the booking page in June 2026: customer names with rare kanji (for example 髙 or 﨑) "
               "rendered as empty boxes, because the subset web font left out those glyphs. Priya added a fallback "
               "to the full Noto Sans JP font on 2026-06-11.",
               "Search-engine crawler bursts on public business pages trip web-traffic a few times a month; they "
               "are harmless when 5xx and page load stay flat.",
               "Safari keeps the old service worker longer than other browsers; after a release, support can ask a "
               "customer to reload twice.",
               "The cloudflare edge serves most static files; a purge normally finishes in about a minute."]},
]

# ---------------------------------------------------------------- routine filler (no codes, no planted words)

ROUTINE = [
    "notifier-queue-depth fired at {d} 03:{m} JST during the nightly reminder batch in ap-northeast (peak {q} "
    "messages); delivered per minute stayed normal and the queue drained before 05:00. First move: no action.",
    "web-traffic fired on {d} at 14:{m} JST: a search-engine crawler on public business pages, about 3.{k}x the same "
    "hour last week, all 2xx. First move: no action; ticket for Aiko about crawler limits.",
    "payments-webhook-retry reached 1{k} % on Sunday night before the weekly payout; the retries succeeded and the "
    "payout started on time at 23:00 JST. First move: no action (P3).",
    "notifier-email-fail touched 2{k} % for 6 minutes on {d}; the sendgrid status page showed delayed processing. "
    "First move: check provider. It cleared with nothing changed on our side.",
    "api-latency on the search endpoint group in eu-west reached 2.{k} s p95 for 11 minutes on {d} during the Europe "
    "morning peak; logs showed one slow query and Daniel opened a ticket. First move: read logs.",
    "web-4xx at 1.{k} % for 12 minutes on {d}: an old marketing link pointing at a removed page. First move: read "
    "logs; no customer reports; ticket filed.",
    "payments-provider-timeout fired on {d} at 20:{m} JST; the stripe status page reported degraded API performance; "
    "cleared in {n} minutes. First move: check provider.",
    "notifier-sms-fail fired for 7 minutes on {d}; the twilio status page listed a carrier incident in Japan; "
    "delivery recovered on its own. First move: check provider.",
    "api-pool reached 9{k} % on one ap-northeast node for 10 minutes on {d}; the load balancer took the node out and "
    "it was replaced. First move: read logs.",
    "web-disk passed 80 % on one web node on {d} because of old log files; Priya cleared the rotated logs in working "
    "hours. First move: read logs.",
    "web-node-restart fired on {d} for one us-east web node (two restarts in 30 minutes, out of memory); the node "
    "was replaced. First move: read logs.",
    "api-partner-reject fired for one partner on {d} at 10:{m} JST: the partner ran a full re-sync and hit its "
    "contracted limit. Ravi confirmed the limit stays as it is. First move: read logs.",
    "web-cdn-edge reached 2.{k} % for 6 minutes on {d}; the cloudflare status page showed an incident at one edge "
    "location. First move: check provider.",
    "api-5xx at 1.{k} % for 4 minutes on {d} during an aws network event in us-east listed on the aws health "
    "dashboard. First move: check provider.",
]

MISC = [
    "The Sunday payout job ran at 23:00 JST and finished in {p} minutes.",
    "Deploys this week: web {a}, api {b}, payments 1, notifier 1; all in the Tuesday and Thursday afternoon windows.",
    "Change calendar for the coming week: no game days or load tests scheduled.",
    "Reminder for incoming: no deploys after 16:00 JST on Friday or between 22:00 and 07:00 JST, except rollbacks and "
    "fixes for open P1s.",
    "The incoming on-call confirmed access to the paging tool, the metrics tool, log search and the deploy tool "
    "before taking the shift.",
    "Support (Hana) had a quiet week: no escalations to on-call.",
    "Quirk: the log search tool's default time window is the last 15 minutes; widen it before deciding there are no "
    "errors.",
    "Quirk: the queue depth panel on the 'Sorrel / notifier' board lags the delivered-per-minute panel by about 2 "
    "minutes; read both before deciding.",
]

# ---------------------------------------------------------------- the rotation: who held the pager, week by week

FIXED_DUTY = {"2025-11-24": "Sara", "2025-12-01": "Priya", "2026-03-30": "Leo", "2026-04-06": "Daniel",
              "2026-05-11": "Noor", "2026-09-14": "Noor", "2026-09-21": "Leo", "2026-09-28": "Leo",
              "2026-10-05": "Noor"}


def mondays(first, last):
    d = date.fromisoformat(first)
    while d <= date.fromisoformat(last):
        yield d
        d += timedelta(days=7)


def duty_table():
    """Who holds the pager for the week that starts on each Monday (a fixed list, then a plain cycle)."""
    cycle = ["Priya", "Leo", "Yuki", "Daniel", "Sara"]
    duty, i = {}, 0
    for d in mondays("2025-09-29", "2026-10-05"):
        k = d.isoformat()
        if k in FIXED_DUTY:
            duty[k] = FIXED_DUTY[k]
            continue
        pool = cycle + (["Noor"] if k >= "2026-05-18" else [])
        nxt = (d + timedelta(days=7)).isoformat()
        while True:
            who = pool[i % len(pool)]
            i += 1
            prev = duty.get((d - timedelta(days=7)).isoformat())
            if who != prev and who != FIXED_DUTY.get(nxt):
                break
        duty[k] = who
    return duty


def h(s, n):
    return int(hashlib.md5(s.encode()).hexdigest(), 16) % n


def week_items(monday):
    """2 routine alerts (fewer when the week already carries 2 planted facts) + 1 misc line, dated in the shift."""
    k = monday.isoformat()
    planted = PLANTED.get(k, [])
    n_routine = 2 if len(planted) < 2 else 1
    days = [(monday - timedelta(days=7 - j)) for j in range(7)]        # the shift: last Monday to Sunday
    items = []
    for j in range(n_routine):
        t = ROUTINE[(h(k, 997) + 5 * j) % len(ROUTINE)]
        d = days[(h(k + str(j), 89) % 5) + 1]                             # Tuesday..Saturday
        items.append(t.format(d=d.strftime("%A %Y-%m-%d"), m=10 + h(k + "m" + str(j), 49), k=h(k + "k" + str(j), 9) + 1,
                              q=1050 + 10 * h(k + "q", 30), n=12 + h(k + "n", 20)))
    m = MISC[h(k + "misc", 991) % len(MISC)]
    items.append(m.format(p=34 + h(k + "p", 9), a=1 + h(k + "a", 3), b=1 + h(k + "b", 3)))
    return planted + items


def handover_specs():
    duty = duty_table()
    specs = []
    for d in mondays("2025-10-06", "2026-10-05"):
        k = d.isoformat()
        if k in EXISTING:
            continue
        prev = (d - timedelta(days=7)).isoformat()
        spec = {"file": f"library/handover-{k}.md", "title": f"On-call handover, week of {k}", "kind": "handover",
                "date": k, "author": PEOPLE[duty[prev]], "incoming": PEOPLE[duty[k]], "facts": week_items(d)}
        if k == "2025-12-01":                      # Sara's note dated 2025-11-24 already covers 11-24 to 12-01
            spec["author"], spec["incoming"] = PEOPLE["Priya"], PEOPLE["Priya"]
            spec["note"] = ("Start-of-shift note by the incoming on-call: Sara's note (week of 2025-11-24) covers the "
                            "week that just ended. Say so in one line and do not describe that week again.")
            spec["facts"] = ["Priya took the pager from Sara at 10:00 JST today and wrote 'taken' in #inc-live.",
                             "Start-of-shift checks done: paging tool test page, metrics boards, log search, deploy "
                             "tool access.",
                             "Watching this week: the tail of the November partner sync traffic on api, expected to "
                             "taper off by Wednesday."]
        if k == "2026-09-28":
            spec["incoming"] = PEOPLE["Leo"] + ", second week in a row (swapped with Daniel)"
        specs.append(spec)
    return specs


# ---------------------------------------------------------------- the 40 questions

def Q(id, kind, question, truth, page, wrong=()):
    return {"id": id, "kind": kind, "question": question, "truth": truth, "wrong": list(wrong), "page": page}


HO = lambda d: f"handover-{d}"

QUESTIONS = [
    # code: an exact string that sits verbatim in the answer page(s)
    Q("code-pay-4031", "code", "What does PAY-4031 mean and what fixed it?",
      [["3-D Secure", "3DS", "3D Secure"], ["25 s", "25s", "25 seconds", "25-second"]], [HO("2025-10-20"), HO("2025-11-03")]),
    Q("code-pay-4107", "code", "Refunds are failing with PAY-4107. What does that code mean and what did we do last time?",
      [["180"], ["bank transfer"]], HO("2026-01-12")),
    Q("code-api-2210", "code", "A partner keeps getting API-2210 back from us. What does it mean?",
      [["opening hours", "business hours", "outside"]], HO("2025-12-15")),
    Q("code-api-2387", "code", "What does API-2387 mean, and what caused it?",
      [["shard"], ["image"]], [HO("2026-02-09"), HO("2026-02-16")]),
    Q("code-ntf-3302", "code", "NTF-3302 is showing up on confirmation emails. What is it and what did we change?",
      [["first name", "first-name"], ["business name"]], HO("2025-10-13")),
    Q("code-ntf-3318", "code", "What is NTF-3318 and what did we do about it?",
      [["landline"], ["sign-up", "signup", "sign up"]], [HO("2026-03-02"), HO("2026-03-16")]),
    Q("code-web-5013", "code", "Support hit WEB-5013 in the admin tool. What does it mean and what changed?",
      [["50,000", "50000"], ["background"]], HO("2026-06-01")),
    Q("code-web-5241", "code", "We're seeing WEB-5241 in the browser errors. What is it?",
      [["chat"], ["allow"]], HO("2026-08-31")),
    Q("code-sms-batch", "code", "What is notifier.sms_batch_size set to now, and why was it lowered?",
      [["200"], ["429", "throttl", "rate limit", "too many requests"]], HO("2026-01-26")),
    Q("code-idle-minutes", "code", "What did we set web.session_idle_minutes to, and when?",
      [["60"], ["2026-06", "June"]], HO("2026-06-22")),
    # other words: the page holds it in team words the question does not use
    Q("ow-charged-twice", "other words", "Some people paid two times for one visit back in January. How many were hit, "
      "and what did we change so it can't happen again?", [["63"], ["idempotency"]], "team-payments-notes"),
    Q("ow-old-events-flood", "other words", "Right after stripe came back from their outage we got flooded with tens "
      "of thousands of old notifications from them. Do I need to stop that?", [["48,000", "48000"]], HO("2026-03-09")),
    Q("ow-3am-slow", "other words", "Around 3 every morning the site where people make appointments crawls for "
      "half an hour. Is that known?", [["export"], ["replica"]], HO("2025-11-10")),
    Q("ow-mail-stopped", "other words", "A bunch of customers say they no longer get anything from us in their inbox, "
      "though nothing's wrong on their end. What happened last time?", [["2,312", "2312"], ["suppress"]],
      "team-notifier-notes"),
    Q("ow-taken-time", "other words", "A customer says the 3 pm time is greyed out but nobody actually booked it. "
      "What's going on?", [["reaper"]], HO("2026-04-20")),
    Q("ow-kicked-out", "other words", "This morning all our users got bounced out of their accounts together, and "
      "getting back in was really slow. Seen that before?", [["jitter", "stagger"]], HO("2026-07-20")),
    Q("ow-us-texts", "other words", "Texts to American customers show as sent but people aren't getting them. Why?",
      [["10DLC"]], HO("2026-06-08")),
    Q("ow-wrong-language", "other words", "Some Japanese customers got their reminder in English yesterday. Has that "
      "happened before, and what fixed it?", [["locale"], ["cache"]], HO("2026-08-24")),
    Q("ow-big-salon-slow", "other words", "Big salons say their schedule screen takes forever to open, but small "
      "shops are fine. Is that known?", [["N+1", "batch"]], HO("2026-02-02")),
    Q("ow-empty-rectangles", "other words", "A few people's surnames come out as empty rectangles when they book. "
      "What's that?", [["font"], ["Noto", "fallback"]], "team-web-notes"),
    # hidden: the title does not say it, the question's words are in the page
    Q("hid-evacuation", "hidden", "How long did the eu-west evacuation game day in February take, and who ran it?",
      [["41"], ["Sara"]], HO("2026-02-23")),
    Q("hid-restore-test", "hidden", "When did the weekly restore test for the payments database start, and how long "
      "did the first restore take?", [["2026-04-22", "April 22", "22 April"], ["52"]], HO("2026-04-27")),
    Q("hid-sendgrid-quota", "hidden", "When did we raise the sendgrid daily quota for the year-end campaign, and to "
      "what?", [["600,000", "600000"], ["2025-12-16", "December 16", "16 December", "Dec 16"]], HO("2025-12-22")),
    Q("hid-firewall-partner", "hidden", "Which partner did the cloudflare firewall rule block in May, and how was it "
      "fixed?", [["Hanabi"], ["allow"]], HO("2026-05-25")),
    Q("hid-noor-first", "hidden", "When did Noor take her first primary on-call shift on her own?",
      [["2026-05-11", "May 11", "11 May"]], HO("2026-05-11")),
    Q("hid-dst-2025", "hidden", "Did the US clock change in November 2025 cause any booking problems?",
      [["212"]], HO("2025-11-03")),
    Q("hid-golden-week", "hidden", "What was the booking peak per minute during Golden Week 2026?",
      [["1,960", "1960"]], HO("2026-05-04")),
    Q("hid-v1-off", "hidden", "When were the old v1 partner API endpoints switched off?",
      [["2026-03-18", "March 18", "18 March"]], HO("2026-03-23")),
    Q("hid-year-end-payout", "hidden", "How long did the year-end payout run take in December 2025?",
      [["2 h 05", "2h05", "2 hours 5", "2 hours and 5", "125 min", "2:05", "2 h 5"]], HO("2025-12-29")),
    Q("hid-cache-ratio", "hidden", "The cloudflare cache hit ratio dropped to 61 % in August. What caused it?",
      [["query string", "timestamp"]], HO("2026-08-17")),
    # plain: the title says it (EP10 questions, same truth)
    Q("pg-kddi-lag", "plain", "SMS delivery receipts for KDDI numbers look late tonight. How late can they normally be?",
      [["40 min"]], "provider-twilio-japan"),
    Q("pg-replayed", "plain", "How many failed payments were replayed after the November 2025 payments checkout "
      "timeout incident?", [["1,184", "1184"]], "postmortem-payments-pool-timeout"),
    Q("pg-cert-outage", "plain", "When the partner API certificate expired in April 2025, how long were partner "
      "connections failing, and how many partners were affected?",
      [["47"], ["3 partners", "three partners", "3 integration partners", "three integration partners", "three of",
                "3 of"]], "postmortem-api-partner-certificate"),
    Q("pg-dup-reminders", "plain", "How many reminders went out twice in the September 2024 notifier scheduler "
      "incident?", [["8,412", "8412"]], "postmortem-notifier-duplicate-reminders"),
    Q("pg-log-access", "plain", "How do I get log search access before my first shadow shift, and who approves it?",
      [["oncall-readers"], ["Kenji"]], "team-access-requests"),
    Q("hb-checkout-threshold", "plain", "What threshold fires the payments-checkout alert?",
      [["2 %", "2%"], ["3 min"]], "handbook-14"),
    # not in pages: the right answer says the pages do not say (graded by hand)
    Q("none-stripe-phone", "not in pages", "What is Stripe's emergency support phone number?", ["NOT_IN_PAGES"], None),
    Q("none-allowance", "not in pages", "How much is the on-call allowance for a week of primary shifts?",
      ["NOT_IN_PAGES"], None),
    Q("none-pay-4999", "not in pages", "What does error code PAY-4999 mean?", ["NOT_IN_PAGES"], None),
    Q("none-sendgrid-renewal", "not in pages", "When does our sendgrid contract come up for renewal?",
      ["NOT_IN_PAGES"], None),
]

GRADING = ("case-insensitive substring. truth = list of groups; every group must match (any one alternative in a "
           "group). wrong = any term present marks a wrong-term hit. NOT_IN_PAGES = graded by hand. page = the page "
           "id(s) in library/INDEX-ep12.json that hold the answer; a list = the answer needs every page in it. "
           "hid-dst-2025: the right answer is 'no problems' (Daniel checked 212 bookings); a code miss there is "
           "hand-checked. The mix of kinds is designed, not sampled.")

if __name__ == "__main__":
    assert len(QUESTIONS) == 40 and len({q["id"] for q in QUESTIONS}) == 40
    specs = handover_specs() + TEAM
    for s in specs:
        for f in s["facts"]:
            assert f.count("\n") == 0
    codes = sorted({w for k, v in PLANTED.items() for f in v for w in f.replace(",", " ").replace(":", " ").split()
                    if len(w) == 8 and w[3] == "-" and w[:3].isalpha() and w[4:].isdigit()})
    spec = {"written": WRITTEN, "what": "EP12 library growth: weekly handover notes 2025-10-06..2026-10-05 that did not "
            "exist + 3 short team pages. The spec carries every fact; the model only writes the prose.",
            "error_codes": codes, "pages": specs,
            "jargon_facts": [{"question": q["id"], "page": q["page"]} for q in QUESTIONS if q["kind"] == "other words"]}
    json.dump(spec, open(os.path.join(ROOT, "library", "SPEC-ep12.json"), "w"), indent=1, ensure_ascii=False)
    json.dump({"written": WRITTEN, "grading": GRADING, "questions": QUESTIONS},
              open(os.path.join(ROOT, "tickets", "questions-ep12.json"), "w"), indent=1, ensure_ascii=False)
    print(len(specs), "pages in the spec;", len(codes), "codes:", " ".join(codes))
    for s in specs[:60]:
        print(s["date"], s.get("author", s.get("owner")), "->", s.get("incoming", ""), len(s["facts"]))
