"""EP13: writes runs/ep13/2026-10-12-p-plain-hand-grades.json from my reading of every P answer (steps + half).
Each answer is cut into claims by ep13_grade.split; 'frame' = a lead-in or heading that claims nothing.
Default for a claim = supported by the closest line, which I read and accepted; every other case is listed below."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "measure")); os.chdir(ROOT)
from ep13_grade import split, nearest, PAGES

FRAME = {"st-cdn-purge": [1], "st-web-rollback": [1], "st-web-blank": [1], "st-admin-deletions": [4],
         "st-replica-lag": [1, 11, 23], "st-reindex": [1, 4, 11, 14], "st-load-test": [1, 6, 10, 12],
         "st-api-rollback": [1, 3, 9], "st-audit-actions": [1], "st-trace-refund": [1, 7, 11, 13, 19, 20, 22, 24],
         "st-two-sent": [2], "st-stripe-key": [1], "st-webhook-secret-actions": [1, 2, 5, 8], "st-payout-alert": [1],
         "st-stuck-workers": [2], "st-night-batch": [1, 5, 6, 9, 11, 14], "st-sendgrid-quota": [1],
         "st-template-actions": [1], "st-duplicates": [1], "st-crawler": [], "st-stripe-key2": []}
for h in ["half-pay-4107", "half-10dlc-cost", "half-hanabi-v1", "half-payout-total", "half-tofu-count",
          "half-capture-total", "half-suppression-tickets", "half-golden-week-2025", "half-restore-size", "half-cert-credits"]:
    FRAME[h] = [1]
FRAME["half-hanabi-v1"] = [1, 2, 4]          # the two bold lead-ins carry no claim of their own

R = lambda page, quote: {"page": page, "quote": quote}
REFS = {   # where the closest line was not the line that carries the claim
    ("st-cdn-purge", 2): [R("howto-cdn-purge-by-hand", "Before touching the CDN dashboard, open the metrics tool and check:")],
    ("st-cdn-purge", 11): [R("howto-cdn-purge-by-hand", "Supply the exact URL prefixes requiring eviction.")],
    ("st-cdn-purge", 13): [R("howto-cdn-purge-by-hand", "A normal purge completes within a minute; check its status on the CDN dashboard's purge panel."),
                           R("howto-cdn-purge-by-hand", "A healthy purge transition should take between 15 and 45 seconds")],
    ("st-cdn-purge", 16): [R("howto-cdn-purge-by-hand", "watch the metrics tool for at least ten minutes"),
                           R("howto-cdn-purge-by-hand", "Verify CPU remains under 65% across all active nodes.")],
    ("st-web-rollback", 6): [R("handbook-5", "Write the rollback in the incident thread with both deploy ids."),
                             R("web-runbook-2024", "Post an update in the `#inc-live` incident thread containing both deploy IDs")],
    ("st-crawler", 2): [R("handover-2026-06-15", "Because traffic was legitimate, errors remained flat, and nothing failed for users, the first move was no action"),
                        R("rules.SYSTEM", "no action: write it down and move on")],
    ("st-admin-deletions", 1): [R("web-runbook-2024", "Immediately page Aiko.")],
    ("st-admin-deletions", 3): [R("rules.SYSTEM", "accounts deleted"),
                                R("handbook-7", "is not something on-call can decide."),
                                R("handbook-7", "Restores come from backups and are done by the owner.")],
    ("st-replica-lag", 2): [R("howto-api-replica-lag", "Open the folder **Sorrel / Services**."),
                            R("howto-api-replica-lag", "Open the **Sorrel / api** board and check the **Database** row.")],
    ("st-replica-lag", 18): [R("howto-api-replica-lag", "Check adjacent panels: **Connections in use per pool**, **Query time**, and **Slow queries**.")],
    ("st-replica-lag", 22): [R("howto-api-replica-lag", "You must never attempt to execute a database failover, promote a read replica to primary, detach replication streams"),
                             R("howto-api-replica-lag", "You must not alter connection pool limits, change database configurations, or kill long-running database processes on production clusters without owner approval.")],
    ("st-replica-lag", 26): [R("howto-api-replica-lag", "**Primary hardware failure**"), R("howto-api-replica-lag", "**Unresolvable deadlocks**")],
    ("st-reindex", 2): [R("howto-api-search-index-rebuild", "Rebuilding the search index is a working-hours job, never a night move for on-call."),
                        R("howto-api-search-index-rebuild", "(between 09:00 and 18:00 JST)"),
                        R("howto-api-search-index-rebuild", "Tuesday and Thursday afternoons between 14:00 and 16:00 JST are the preferred operating windows.")],
    ("st-reindex", 6): [R("howto-api-search-index-rebuild", "connection pool usage must be below 70 % across all active nodes"),
                        R("howto-api-search-index-rebuild", "read replica lag must be steady and under 100 ms.")],
    ("st-reindex", 8): [R("howto-api-search-index-rebuild", "Drop a brief note in `#team-api`:")],
    ("st-reindex", 12): [R("howto-api-search-index-rebuild", "- Service: `api`")],
    ("st-reindex", 21): [R("howto-api-search-index-rebuild", "Keep the following metrics open throughout the run:"),
                         R("howto-api-search-index-rebuild", "If pool utilization climbs near 90 %")],
    ("st-reindex", 23): [R("howto-api-search-index-rebuild", "**Confirm the pointer swap:**"),
                         R("howto-api-search-index-rebuild", "should drop immediately to near zero (typically `< 5m`)."),
                         R("howto-api-search-index-rebuild", "**Run a manual search verification:**"),
                         R("howto-api-search-index-rebuild", "Post an update in `#team-api`:")],
    ("st-load-test", 2): [R("howto-stop-unowned-load-test", "Check the game day calendar first; if the test is on it, ask its owner before stopping it.")],
    ("st-load-test", 4): [R("howto-stop-unowned-load-test", "it is an orphaned test"),
                          R("howto-stop-unowned-load-test", "the on-call engineer has explicit operational permission to stop rogue load tests immediately.")],
    ("st-load-test", 15): [R("howto-stop-unowned-load-test", "As soon as the test is terminated, post a summary in the `#platform` chat channel:"),
                           R("howto-stop-unowned-load-test", "No entry on Game Day calendar, no owner found in metadata.")],
    ("st-load-test", 16): [R("howto-stop-unowned-load-test", "Post an update with the concrete action:"),
                           R("howto-stop-unowned-load-test", "Watch dashboards for 10 minutes to verify:")],
    ("st-api-rollback", 5): [R("deploying-with-shipyard", "(or `shipyard releases api`)")],
    ("st-api-rollback", 7): [R("handbook-5", "Run `shipyard rollback api --to <previous release>`")],
    ("st-api-rollback", 8): [R("deploying-with-shipyard", "Shipyard asks you to type the service name to confirm.")],
    ("st-api-rollback", 13): [R("deploying-with-shipyard", "Type the service name in the box to confirm.")],
    ("st-api-rollback", 16): [R("deploying-with-shipyard", "During an incident, paste the output of `shipyard releases <service>` into the incident thread."),
                              R("deploying-with-shipyard", "Copy both release names into the incident thread yourself as well.")],
    ("st-api-rollback", 17): [R("handbook-5", "Watch error rate and latency return to the level before the deploy")],
    ("st-audit-actions", 7): [R("postmortem-api-audit-disk", "Clears 14 GB of dead files."),
                              R("postmortem-api-audit-disk", "Restarts the background audit daemon on the affected nodes."),
                              R("postmortem-api-audit-disk", "All 18,320 entries were subsequently backfilled from structured application request logs by 2025-12-13.")],
    ("st-trace-refund", 5): [R("howto-trace-a-refund", "Set the index to `sorrel-prod-*`.")],
    ("st-trace-refund", 8): [R("howto-trace-a-refund", "service=payments booking_id=\"bk_5510294\"")],
    ("st-trace-refund", 10): [R("howto-trace-a-refund", "Once you have the `ref`, verify whether our nodes actually handed the transaction off to the card provider.")],
    ("st-trace-refund", 14): [R("howto-trace-a-refund", "The refund never left our cluster. Proceed to check for queue deadlocks or database connection issues in `service=payments`.")],
    ("st-trace-refund", 15): [R("howto-trace-a-refund", "**1 line**: Normal operation."), R("howto-trace-a-refund", "Check the HTTP response status logged on that line:")],
    ("st-trace-refund", 18): [R("howto-trace-a-refund", "If one reference shows two 'sent' lines, money may have moved twice: stop and page Mei."),
                              R("howto-trace-a-refund", "**Do not attempt to roll back code** as your first move")],
    ("st-trace-refund", 25): [R("howto-trace-a-refund", "If it was sent fewer than 6 hours ago, this is normal behavior."),
                              R("howto-trace-a-refund", "settled comes from the stripe webhook and can arrive hours later.")],
    ("st-stripe-key", 3): [R("team-secrets-manager", "**Never rotate a production credential yourself; rotation is the credential owner's decision.**"),
                           R("team-secrets-manager", "Do not attempt to log into the Stripe dashboard to revoke the key.")],
    ("st-stripe-key", 6): [R("team-secrets-manager", "Page **Mei** immediately through the paging tool.")],
    ("st-stripe-key", 8): [R("team-secrets-manager", "Post to `#inc-live`:"), R("team-secrets-manager", "(do not include the secret itself)")],
    ("st-stuck-workers", 1): [R("howto-notifier-queue-panels", "**Oldest message age above 30 minutes while delivered per minute is zero means the workers are stuck.**")],
    ("st-night-batch", 10): [R("howto-notifier-queue-panels", "Verify that **Oldest message age** remains controlled"),
                             R("howto-notifier-queue-panels", "Increasing linearly; > 30 minutes")],
    ("st-night-batch", 18): [R("howto-notifier-queue-panels", "If there has been no recent deploy, your first move is **read logs**."),
                             R("howto-notifier-queue-panels", "Look for worker loop errors: `service=notifier msg=\"worker stuck\"` or `service=notifier msg=\"worker idle\"`.")],
    ("st-night-batch", 19): [R("howto-notifier-queue-panels", "If the alert points directly at vendor API rejections or vendor status incidents, choose **check provider**."),
                             R("howto-notifier-queue-panels", "For SMS: Check `status.twilio.com`.")],
    ("st-sendgrid-quota", 2): [R("provider-sendgrid-quota", "Review the **Vendor quota usage** panel on the `notifier` board."),
                               R("provider-sendgrid-quota", "service=notifier msg=\"quota\"")],
    ("st-sendgrid-quota", 4): [R("provider-sendgrid-quota", "Customers booking appointments will experience delayed confirmations.")],
    ("st-sendgrid-quota", 5): [R("provider-sendgrid-quota", "Verify that workers are safely deferring jobs and not dropping messages."),
                               R("provider-sendgrid-quota", "The sendgrid daily quota resets at 09:00 JST (00:00 UTC).")],
    ("st-sendgrid-quota", 6): [R("provider-sendgrid-quota", "Raising the quota is a purchasing decision for Tom, not an on-call action."),
                               R("provider-sendgrid-quota", "On-call engineers do not have administrative access, contractual authorization, or purchasing permission")],
    ("st-template-actions", 3): [R("postmortem-notifier-template-crash", "the broker shunts the envelope directly to `sorrel-notifier-parked-[region]`, emits alert `notifier-message-parked`")],
    ("st-duplicates", 4): [R("notifier-runbook-2024", "service=notifier level=ERROR msg=\"failed to ack\"")],
    ("half-pay-4107", 3): [R("handover-2026-01-12", "the card provider refuses refunds on charges older than 180 days.")],
    ("half-10dlc-cost", 3): [], ("half-hanabi-v1", 5): [R("handover-2026-03-23", "About 3 calls a day still arrive on v1 from a test script at Hanabi Booking; they get 410 and Ravi has told them.")],
    ("half-payout-total", 2): [R("handover-2025-12-29", "It started at 23:00 JST and finished at 01:05 JST")],
    ("half-payout-total", 3): [], ("half-tofu-count", 3): [], ("half-suppression-tickets", 3): [],
    ("half-golden-week-2025", 3): [], ("half-restore-size", 3): [],
    ("half-capture-total", 3): [R("team-payments-notes", "Mei's team refunded the second charge the same day")],
    ("half-cert-credits", 3): [R("postmortem-api-partner-certificate", "No direct transaction financial loss was recorded")],
}
SAYS_NOT = {("half-pay-4107", 3), ("half-10dlc-cost", 3), ("half-hanabi-v1", 5), ("half-payout-total", 3),
            ("half-tofu-count", 3), ("half-capture-total", 3), ("half-suppression-tickets", 3),
            ("half-golden-week-2025", 3), ("half-restore-size", 3), ("half-cert-credits", 3)}
SPECIAL = {
    ("st-webhook-secret-actions", n): {"grade": "ambiguous", "refs": [R("postmortem-payments-webhook-secret", q)],
        "note": "the item is on the page as an action item with a target date and no status; the answer says it was done "
                "(only ACT-01 is marked Completed). Content right, completion not on the page."}
    for n, q in [(9, "| **ACT-02** | Update rotation script"), (10, "| **ACT-04** | Add an automated check in the deployment tool"),
                 (11, "| **ACT-05** | Update Section 6.1"), (12, "| **ACT-06** | Create standard support canned responses")]}
SPECIAL[("half-10dlc-cost", 2)] = {"grade": "supported", "refs": [R("handover-2026-06-08", "Tom approved registering our 10DLC campaign with twilio; registration went through on Friday and delivery is back to normal.")],
    "note": "the date 'June 5, 2026' is the model's own inference (the Friday before the week of 2026-06-08); the page says only 'Friday'. Harmless, not word for word."}

d = json.load(open("runs/ep13/2026-10-12-p-plain.json"))
grades = {}
for q in d["questions"]:
    ids = q["pages_in_call"] + ["rules.SYSTEM"]
    out = []
    for n, c in enumerate(split(q["answer"]), 1):
        key = (q["id"], n)
        if n in FRAME.get(q["id"], []):
            out.append({"n": n, "claim": c, "grade": "frame"}); continue
        if key in SPECIAL:
            out.append({"n": n, "claim": c, **SPECIAL[key]}); continue
        if key in SAYS_NOT:
            out.append({"n": n, "claim": c, "grade": "says-not-in-pages", "refs": REFS.get(key, []),
                        "note": "the missing part; grep proof in runs/ep13/2026-10-12-q-build.json"}); continue
        refs = REFS.get(key)
        if refs is None:
            score, pid, i, line = nearest(c, ids, 1)[0]
            refs = [R(pid, line)]
        out.append({"n": n, "claim": c, "grade": "supported", "refs": refs})
    grades[q["id"]] = out
json.dump({"what": "P hand grades: every claim of every steps/half answer, read against the pages in the call "
                   "(rules.SYSTEM counts: it is in the call). grades: supported (refs = the page line), "
                   "not-on-page, wrong, ambiguous (said why), says-not-in-pages (the half question's missing part), "
                   "frame (a lead-in or heading, no claim).",
           "run": "runs/ep13/2026-10-12-p-plain.json", "grades": grades},
          open("runs/ep13/2026-10-12-p-plain-hand-grades.json", "w"), indent=1, ensure_ascii=False)
from collections import Counter
print(Counter(c["grade"] for g in grades.values() for c in g))
