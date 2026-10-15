"""Build the deploy history: deploys/deploys.csv, deploys/deploys.db (the same rows), deploys/CANON.json.

    .venv/bin/python deploys/make_deploys.py          # write all three; re-running writes the same bytes
    .venv/bin/python deploys/make_deploys.py --check  # rebuild in memory, compare md5s, write nothing

One row per deploy that started. Columns: id, service, started, finished, author, state, note.
Times are JST, ISO to the minute, no offset ("2026-10-06T14:10"). Span 2024-03-25 .. 2026-10-11.
The pages are canon: every row a page names is pinned below with the page and line it comes from, and every
sentence that dates, counts or rules out a deploy is a check. The script fails if any check fails.
Measurement data for EP14, not episode code. Stdlib only.
"""
import csv, datetime as dt, hashlib, io, json, os, random, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 14
FIRST, LAST = dt.date(2024, 3, 25), dt.date(2026, 10, 11)
SHIPYARD = dt.datetime(2026, 9, 28, 0, 0)
SERVICES = ["web", "api", "payments", "notifier"]
AUTHORS = {"web": [("Priya", 45), ("Aiko", 35), ("Emi", 20)],
           "api": [("Daniel", 45), ("Ravi", 35), ("Jun", 20)],
           "payments": [("Mei", 45), ("Leo", 35), ("Ren", 20)],
           "notifier": [("Yuki", 50), ("Tom", 35), ("Kai", 15)]}
MINUTES = {"web": (8, 14), "api": (10, 18), "payments": (6, 12), "notifier": (5, 9)}
NOTES = {"web": ["booking page fixes", "admin tool update", "asset bundle refresh", "calendar view tweak",
                 "sign-in page copy", "dependency bumps", "business page layout", "checkout form styling"],
         "api": ["availability query change", "partner API limits", "booking validation", "search index tuning",
                 "dependency bumps", "audit log batching", "staff roster endpoint", "calendar endpoint paging"],
         "payments": ["checkout form fixes", "refund batch tweak", "webhook handler update", "payout job change",
                      "dependency bumps", "receipt email fields"],
         "notifier": ["reminder template update", "SMS sender change", "queue worker tuning", "email template fix",
                      "dependency bumps", "scheduler batch size"]}
# every deploy id that appears on any page, examples included: no generated row may take one
RESERVED = {"d-0842", "d-0890", "d-0891", "d-1039", "d-1042", "d-1044", "d-1047", "d-1048", "d-1234", "d-1482",
            "d-3798", "d-3810", "d-3841", "d-3917", "d-3920", "d-4466", "d-4471", "d-4812", "d-4819", "d-4821",
            "d-4986", "d-5117", "d-5120", "d-5121", "d-8912"}


def T(s):
    return dt.datetime.fromisoformat(s)


def row(id, service, started, mins, author, note, state=None):
    s = T(started)
    return {"id": id, "service": service, "started": s, "finished": s + dt.timedelta(minutes=mins),
            "author": author, "state": state, "note": note}


# ------------------------------------------------------------------ pinned rows: a page names them
# (row, [(page, line, the words on the page)])
PINNED = [
    (row("d-1039", "web", "2024-04-05T11:30", 12, "Priya", "booking page copy update"),
     [("library/postmortem-notifier-sms-codes-japan.md", 41, "`web` was deployed on Friday (`d-1039` by Priya)")]),
    (row("d-1044", "notifier", "2024-04-06T07:40", 8, "Yuki", "SMS sender config"),
     [("library/postmortem-notifier-sms-codes-japan.md", 41,
       "`notifier` was last deployed two days prior (`d-1044` by Yuki)")]),
    (row("d-4466", "api", "2024-07-04T15:10", 14, "Ravi", "availability query change"),
     [("pages/postmortem-api-index-migration.md", 46, "Tom rolls api back to the previous deploy, d-4466.")]),
    (row("d-4471", "api", "2024-07-09T14:05", 4, "Ravi", "migration 0193; rolled back to d-4466 at 14:31",
         "rolled back"),
     [("pages/postmortem-api-index-migration.md", 23, "14:05 api deploy d-4471 goes out."),
      ("pages/postmortem-api-index-migration.md", 46, "14:31 Tom rolls api back to the previous deploy, d-4466.")]),
    (row("d-4471", "api", "2024-07-09T15:24", 7, "Ravi", "same build deployed again after the new index finished"),
     [("pages/postmortem-api-index-migration.md", 64, "15:24 Ravi deploys d-4471 again")]),
    (row(None, "notifier", "2024-08-12T13:50", 7, "Tom", "sender pool config"),
     [("library/handover-2024-08-19.md", 42, "notifier deploy was three days old")]),
    (row("d-0842", "notifier", "2024-08-27T15:00", 7, "Yuki", "scheduler batch change"),
     [("library/postmortem-notifier-duplicate-reminders.md", 47, "the running deploy (`d-0842`) is five days old")]),
    (row(None, "notifier", "2024-09-05T14:40", 8, "Yuki", "reminder dedupe key"),
     [("library/postmortem-notifier-duplicate-reminders.md", 116,
       "**Deploy Date:** 2024-09-05 via normal deploy process in the deploy tool.")]),
    (row("d-3798", "api", "2024-10-22T15:00", 15, "Daniel", "base image refresh"),
     [("library/postmortem-api-dst-us-east.md", 105, "`api-useast-03` | `d-3798` | 2022g")]),
    (row("d-3810", "api", "2024-10-31T14:40", 16, "Daniel", "tzdata 2024a image"),
     [("library/postmortem-api-dst-us-east.md", 103, "`api-useast-01` | `d-3810` | 2024a")]),
    (row("d-3841", "api", "2024-11-04T14:15", 11, "Daniel", "tzdata pin fix for us-east"),
     [("library/postmortem-api-dst-us-east.md", 58, "**14:15**: Deploy `d-3841` for `api` is reviewed by Ravi and "
                                                    "kicked off"),
      ("library/postmortem-api-dst-us-east.md", 59, "**14:26**: Deploy `d-3841` finishes")]),
    (row(None, "api", "2025-01-07T14:10", 15, "Daniel", "booking validation"),
     [("library/handover-2025-01-06.md", 92, "Tuesday (2025-01-07) afternoon: Deploys planned for `api` "
                                             "(Daniel / Ravi) and `web` (Aiko / Priya).")]),
    (row(None, "web", "2025-01-07T15:05", 11, "Aiko", "business page layout"),
     [("library/handover-2025-01-06.md", 92, "Tuesday (2025-01-07) afternoon: Deploys planned for `api` "
                                             "(Daniel / Ravi) and `web` (Aiko / Priya).")]),
    (row("d-1482", "web", "2025-02-12T15:10", 10, "Aiko", "admin idle timeout 2 h"),
     [("library/postmortem-web-admin-session.md", 154,
       "released under deploy `d-1482` on Wednesday afternoon (2025-02-12)")]),
    (row("d-4819", "web", "2025-05-12T13:40", 12, "Priya", "asset bundle refresh"),
     [("library/howto-cdn-purge-by-hand.md", 202, "2025-05-12 14:22 JST | web | P2 | read logs | Detected asset "
                                                  "hash 404s after deploy d-4819")]),
    (row(None, "web", "2025-05-18T13:30", 9, "Aiko", "weekend hotfix"),
     [("pages/postmortem-web-firewall-challenge.md", 37, "16:39 Tom checks the deploy tool. The last web deploy is "
                                                         "2 days old")]),
    (row(None, "api", "2025-06-24T15:00", 14, "Ravi", "pool config"),
     [("library/handover-2025-06-30.md", 73, "the last `api` deploy was `d-3841`, pushed two days prior on "
                                              "Tuesday afternoon")]),
    (row(None, "web", "2025-07-01T14:20", 10, "Priya", "dependency bumps"),
     [("library/handover-2025-06-30.md", 133, "Planned service deploys for `web` and `api` are scheduled for "
                                               "Tuesday (2025-07-01) and Thursday (2025-07-03) between 14:00 and "
                                               "16:00 JST.")]),
    (row(None, "api", "2025-07-01T15:00", 14, "Ravi", "pool config follow-up"),
     [("library/handover-2025-06-30.md", 133, "Tuesday (2025-07-01) and Thursday (2025-07-03)")]),
    (row(None, "web", "2025-07-03T14:15", 11, "Aiko", "calendar view tweak"),
     [("library/handover-2025-06-30.md", 133, "Tuesday (2025-07-01) and Thursday (2025-07-03)")]),
    (row(None, "api", "2025-07-03T15:05", 13, "Daniel", "availability query change"),
     [("library/handover-2025-06-30.md", 133, "Tuesday (2025-07-01) and Thursday (2025-07-03)")]),
    (row("d-0890", "web", "2025-07-17T14:30", 11, "Aiko", "campaign prep"),
     [("library/postmortem-web-cdn-purge-stuck.md", 33, "whether to execute a rollback to `d-0890`")]),
    (row("d-0891", "web", "2025-07-22T14:10", 5, "Priya", "summer campaign release"),
     [("library/postmortem-web-cdn-purge-stuck.md", 26, "| 14:10 | Priya initiates deploy `d-0891` for web"),
      ("library/postmortem-web-cdn-purge-stuck.md", 9, "On Tuesday, 2025-07-22, at 14:15 JST, the web team deployed "
                                                       "release `d-0891`")]),
    (row(None, "payments", "2025-11-13T15:00", 9, "Mei", "v2.30"),
     [("library/postmortem-payments-pool-timeout.md", 33, "| 02:58 | Rollback to v2.30 started. | Mei |")]),
    (row(None, "payments", "2025-11-18T02:14", 6, "Mei", "v2.31 pool 50 to 20; rolled back to v2.30 at 02:58",
         "rolled back"),
     [("library/postmortem-payments-pool-timeout.md", 24, "| 02:14 | payments v2.31 deployed."),
      ("library/postmortem-payments-pool-timeout.md", 33, "| 02:58 | Rollback to v2.30 started. | Mei |")]),
    (row(None, "api", "2025-11-27T14:30", 15, "Daniel", "query index cleanup"),
     [("library/handover-2025-11-24.md", 63, "the query index cleanup deployed by Daniel on Thursday")]),
    (row(None, "api", "2025-12-02T14:30", 14, "Daniel", "slot conflict check speedup"),
     [("library/handover-2025-11-24.md", 85, "Daniel has an optimization PR slated for `api` booking slot conflict "
                                             "checks on Tuesday afternoon (around 14:30 JST)")]),
    (row("d-4812", "api", "2025-12-09T23:30", 11, "Daniel", "booking slot query fix"),
     [("library/postmortem-api-audit-disk.md", 57, "Last deploy was `d-4812` released 38 hours prior (2025-12-09 "
                                                   "23:30 JST) by Daniel.")]),
    (row(None, "api", "2026-01-29T15:00", 14, "Daniel", "week-view calendar query batching"),
     [("library/handover-2026-02-02.md", 28, "The week-view calendar endpoint has been quiet since Thursday's "
                                             "deploy")]),
    (row(None, "web", "2026-03-12T14:35", 10, "Priya", "sign-up phone number check"),
     [("library/handover-2026-03-16.md", 15, "Priya's sign-up form change shipped on Thursday")]),
    (row(None, "api", "2026-04-14T14:40", 15, "Daniel", "booking hold changes"),
     [("library/handover-2026-04-20.md", 15, "the hold reaper job had been paused since the api deploy on "
                                             "2026-04-14")]),
    (row(None, "api", "2026-04-17T10:50", 13, "Ravi", "hold reaper back on"),
     [("library/postmortem-api-aws-dns-apne1.md", 49, "Deploy history shows `api` last deployed 4 days ago")]),
    (row(None, "web", "2026-05-28T14:25", 12, "Aiko", "admin export as a background job"),
     [("library/handover-2026-06-01.md", 30, "The background job pattern for admin tool downloads shipped by "
                                             "Aiko's team on Thursday")]),
    (row(None, "web", "2026-07-16T14:30", 10, "Priya", "session expiry jitter"),
     [("library/handover-2026-07-20.md", 31, "the jitter fix deployed after Wednesday's stampede")]),
    (row("d-8912", "notifier", "2026-07-24T10:40", 7, "Tom", "queue worker tuning"),
     [("library/postmortem-notifier-template-crash.md", 49, "last deploy age 4 days (`d-8912`)")]),
    (row(None, "notifier", "2026-07-28T16:20", 8, "Yuki", "park messages that crash a worker twice (P1 fix)"),
     [("library/postmortem-notifier-template-crash.md", 134, "As of 2026-07-28 evening, Yuki deployed the automated "
                                                            "parking fix to `notifier`")]),
    (row(None, "notifier", "2026-08-18T14:20", 7, "Tom", "template cache change"),
     [("library/handover-2026-08-24.md", 15, "after Tuesday's notifier template deploy")]),
    (row(None, "notifier", "2026-08-18T16:05", 6, "Yuki", "locale in template cache key"),
     [("library/handover-2026-08-24.md", 15, "Yuki added the locale to the cache key the same day.")]),
    (row("d-5117", "api", "2026-08-18T15:00", 14, "Ravi", "partner API limits"),
     [("library/postmortem-api-rollback-queue.md", 30, "Sara presses \"Roll back to this\" for api, back to d-5117.")]),
    (row("d-5120", "api", "2026-08-20T14:02", 3, "Daniel", "opening hours validation; rolled back to d-5117 at 14:47",
         "rolled back"),
     [("library/postmortem-api-rollback-queue.md", 25, "| 14:02 | api d-5120 starts going out. | Ravi's team "
                                                       "(author: Daniel) |"),
      ("library/postmortem-api-rollback-queue.md", 35, "d-5121 is cancelled, and the api rollback starts.")]),
    (row("d-5121", "web", "2026-08-20T14:05", 42, "Priya", "cancelled during asset upload", "failed"),
     [("library/postmortem-api-rollback-queue.md", 27, "| 14:05 | web deploy d-5121 starts in the deploy tool "
                                                       "(unrelated front-end change). | Aiko's team |"),
      ("library/postmortem-api-rollback-queue.md", 35, "| 14:47 | The upload step finishes, d-5121 is cancelled")]),
    (row("r-200", "api", "2026-09-28T10:00", 0, "Kenji Sato", "first Shipyard release; same code as before"),
     [("library/deploying-with-shipyard.md", 30, "The first Shipyard releases were api r-200 and payments r-200, "
                                                 "both cut from whatever was running on 2026-09-28")]),
    (row("r-200", "payments", "2026-09-28T10:00", 0, "Kenji Sato", "first Shipyard release; same code as before"),
     [("library/deploying-with-shipyard.md", 30, "The first Shipyard releases were api r-200 and payments r-200")]),
    (row("r-201", "api", "2026-09-29T14:30", 18, "Daniel", "staff roster endpoint"), []),
    (row("r-208", "payments", "2026-09-29T15:10", 14, "Ren", "receipt email fields"),
     [("library/handover-2026-10-05.md", 32, "payments release r-209 was rolled back to r-208")]),
    (row("r-202", "api", "2026-10-01T14:40", 17, "Jun", "partner API limits"), []),
    (row("r-209", "payments", "2026-10-02T13:58", 8, "Ren", "postal code validation; rolled back to r-208 at 14:18",
         "rolled back"),
     [("library/handover-2026-10-05.md", 24, "| 2026-10-02 14:18 | `payments` | P2 | roll back | Validation errors "
                                             "spiked above 1 % following deploy"),
      ("library/handover-2026-10-05.md", 32, "On 2026-10-02 payments release r-209 was rolled back to r-208")]),
    (row(None, "web", "2026-10-06T14:10", 12, "Priya", "front-end asset optimization"),
     [("library/handover-2026-10-05.md", 79, "| 2026-10-06 14:00-16:00 | `web` | Aiko / Priya | Scheduled front-end "
                                             "asset optimization release.")]),
    (row("r-203", "api", "2026-10-06T14:45", 16, "Daniel", "booking validation"), []),
    (row("r-204", "api", "2026-10-08T14:20", 19, "Ravi", "search index tuning"), []),
    (row("r-210", "payments", "2026-10-08T15:00", 13, "Ren", "postal code validation, fixed"), []),
    (row("r-205", "api", "2026-10-08T16:10", 15, "Jun", "calendar endpoint paging"), []),
]

# ------------------------------------------------------------------ checks: a page says something about a span of time
# quiet: no deploy of these services STARTED in (start, end); the pinned row at the start is the one the page means
QUIET = [
    (["notifier"], "2024-04-06T07:40", "2024-04-08T08:01", "library/postmortem-notifier-sms-codes-japan.md", 41,
     "`notifier` was last deployed two days prior (`d-1044` by Yuki)"),
    (["web"], "2024-04-05T11:30", "2024-04-08T08:01", "library/postmortem-notifier-sms-codes-japan.md", 41,
     "`web` was deployed on Friday (`d-1039` by Priya)"),
    (["api"], "2024-07-04T15:10", "2024-07-09T14:05", "pages/postmortem-api-index-migration.md", 46,
     "Tom rolls api back to the previous deploy, d-4466."),
    (["api"], "2024-07-09T14:05", "2024-07-09T14:23", "pages/postmortem-api-index-migration.md", 54,
     "Tom notes the last api deploy is 18 minutes old"),
    (["notifier"], "2024-08-12T13:50", "2024-08-15T14:18", "library/handover-2024-08-19.md", 42,
     "notifier deploy was three days old"),
    (["notifier"], "2024-08-27T15:00", "2024-09-02T03:05", "library/postmortem-notifier-duplicate-reminders.md", 47,
     "the running deploy (`d-0842`) is five days old"),
    (["api"], "2024-10-22T15:00", "2024-10-31T14:40", "library/postmortem-api-dst-us-east.md", 105,
     "three of the eight running `api` nodes in `us-east` were running an image built from an unpinned base snapshot"),
    (["api"], "2024-10-31T14:40", "2024-11-04T14:15", "library/postmortem-api-dst-us-east.md", 105,
     "three of the eight running `api` nodes in `us-east` were running an image built from an unpinned base snapshot"),
    (["web"], "2025-05-18T13:30", "2025-05-20T16:39", "pages/postmortem-web-firewall-challenge.md", 37,
     "The last web deploy is 2 days old"),
    (["api"], "2025-06-24T15:00", "2025-06-26T09:18", "library/handover-2025-06-30.md", 73,
     "the last `api` deploy was `d-3841`, pushed two days prior on Tuesday afternoon"),
    (["web"], "2025-07-17T14:30", "2025-07-22T14:10", "library/postmortem-web-cdn-purge-stuck.md", 33,
     "The team evaluates whether to execute a rollback to `d-0890`."),
    (["api", "notifier"], "2025-09-05T00:00", "2025-09-09T17:02", "library/postmortem-notifier-sendgrid-quota.md", 58,
     "No recent deploys on `notifier` or `api` (last deploy was several days prior)."),
    (["payments"], "2025-11-13T15:00", "2025-11-18T02:14", "library/postmortem-payments-pool-timeout.md", 33,
     "| 02:58 | Rollback to v2.30 started. | Mei |"),
    (["api"], "2025-12-09T23:30", "2025-12-11T14:46", "library/postmortem-api-audit-disk.md", 57,
     "Last deploy was `d-4812` released 38 hours prior"),
    (["payments"], "2026-03-01T14:26", "2026-03-03T14:26", "library/postmortem-payments-webhook-secret.md", 62,
     "no code deploys within the last 48 hours"),
    (["api"], "2026-04-17T10:50", "2026-04-21T11:21", "library/postmortem-api-aws-dns-apne1.md", 49,
     "`api` last deployed 4 days ago"),
    (["notifier"], "2026-07-24T10:40", "2026-07-28T14:27", "library/postmortem-notifier-template-crash.md", 49,
     "last deploy age 4 days (`d-8912`)"),
    (["api"], "2026-08-18T15:00", "2026-08-20T14:02", "library/postmortem-api-rollback-queue.md", 30,
     "Sara presses \"Roll back to this\" for api, back to d-5117."),
    (["payments"], "2026-09-29T15:10", "2026-10-02T13:58", "library/handover-2026-10-05.md", 32,
     "payments release r-209 was rolled back to r-208"),
]
FREEZE = [  # no deploy started on these days
    ("2024-08-13", "2024-08-18", "library/handover-2024-08-19.md", 123, "Standard deploys resume this week across "
     "Tuesday and Thursday afternoon windows."),
    ("2024-12-26", "2025-01-04", "library/handover-2025-01-06.md", 60, "deploys were frozen from 26 December through "
                                                                       "4 January"),
    ("2025-12-26", "2026-01-04", None, None, "no page: my choice, the same year-end freeze as the year before"),
]
# exact counts for the shift week that starts on this Monday; all on Tue/Thu afternoons; none rolled back or failed
COUNTS = [
    ("2025-10-06", {"web": 2, "api": 1, "payments": 1, "notifier": 1}, "library/handover-2025-10-13.md", 15),
    ("2025-11-03", {"web": 2, "api": 3, "payments": 1, "notifier": 1}, "library/handover-2025-11-10.md", 16),
    ("2026-01-05", {"web": 3, "api": 2, "payments": 1, "notifier": 1}, "library/handover-2026-01-12.md", 25),
    ("2026-02-09", {"web": 1, "api": 1, "payments": 1, "notifier": 1}, "library/handover-2026-02-16.md", 16),
    ("2026-03-02", {"web": 2, "api": 1, "payments": 1, "notifier": 1}, "library/handover-2026-03-09.md", 18),
    ("2026-03-30", {"web": 3, "api": 2, "payments": 1, "notifier": 1}, "library/handover-2026-04-06.md", 90),
    ("2026-04-20", {"web": 2, "api": 2, "payments": 1, "notifier": 1}, "library/handover-2026-04-27.md", 15),
    ("2026-05-04", {"web": 3, "api": 3, "payments": 1, "notifier": 1}, "library/handover-2026-05-11.md", 15),
    ("2026-05-11", {"web": 2, "api": 2, "payments": 1, "notifier": 1}, "library/handover-2026-05-18.md", 18),
    ("2026-07-13", {"web": 2, "api": 2, "payments": 1, "notifier": 1}, "library/handover-2026-07-20.md", 15),
    ("2026-07-27", {"web": 3, "api": 2, "payments": 1, "notifier": 1}, "library/handover-2026-08-03.md", 17),
    ("2026-10-05", {"web": 3, "api": 3, "payments": 1, "notifier": 2}, None, None),   # last week: no page, my design
]
# shift weeks whose handover says no rollbacks (Monday the shift started)
NO_ROLLBACK = [("2025-09-29", "library/handover-2025-10-06.md", 9, "without manual rollbacks"),
               ("2025-10-13", "library/handover-2025-10-20.md", 9, "No internal rollbacks were required"),
               ("2026-05-11", "library/handover-2026-05-18.md", 9, "no major service interruptions or internal "
                                                                   "rollbacks needed"),
               ("2026-08-24", "library/handover-2026-08-31.md", 9, "no major internal regressions requiring "
                                                                   "rollbacks"),
               ("2026-09-07", "library/handover-2026-09-14.md", 9, "without requiring manual service intervention "
                                                                   "or rollbacks")]
# page facts with no row of their own: written to CANON.json as they are
NOTED = [
    ("out of span", "library/postmortem-web-font-upload.md", 12, "On Tuesday, 2024-01-23 at 19:12 JST, `web` deploy "
     "`d-4821` reached production", "2024-01-23 is before the table starts (2024-03-25); no row"),
    ("conflict", "library/handover-2024-03-25.md", 54, "the last deploy was `d-3841`, pushed 28 hours prior by Priya",
     "web d-3841 on 2024-03-18 (28 h before 2024-03-19 14:22) is before the table starts; no row. The same id is api "
     "on 2024-11-04 in postmortem-api-dst-us-east, which the table keeps"),
    ("conflict", "library/handover-2025-06-30.md", 73, "the last `api` deploy was `d-3841`, pushed two days prior on "
     "Tuesday afternoon", "d-3841 is api 2024-11-04 in postmortem-api-dst-us-east (a timeline with minutes); one id "
     "cannot be two deploys 7 months apart. The table has an api deploy on Tuesday 2025-06-24 afternoon, the last "
     "before 2025-06-26 09:18, under its own id. Not resolved: the page says d-3841"),
    ("conflict resolved by reading", "library/handover-2025-10-13.md", 14, "Yuki changed the templates to fall back to "
     "the business name when the first name is empty; shipped Friday.", "the same note says 'Deploys this week: ... "
     "notifier 1; all in the Tuesday and Thursday afternoon windows'. Read as a sendgrid template change, not a deploy; "
     "the week's notifier deploy is on Tue/Thu. If it was a deploy, the page contradicts itself"),
    ("id format", "library/postmortem-payments-pool-timeout.md", 24, "| 02:14 | payments v2.31 deployed.",
     "the page names payments releases v2.30 / v2.31, not d-NNNN; the rows carry d- ids and the version in note"),
    ("example", "library/web-runbook-2024.md", 147, "Current Deploy:  d-1048 ... Target Deploy: d-1047",
     "a screen in a how-to, no date: no row, ids reserved"),
    ("example", "library/payments-rollback-runbook.md", 23, "(for example `d-3920`) ... (for example `d-3917`)",
     "example, no date: no row, ids reserved"),
    ("example", "library/team-dashboards-guide.md", 166, "labeled with its deploy id (e.g., `d-1042`)",
     "example: no row, id reserved"),
    ("example", "library/notifier-runbook-2024.md", 248, "(e.g., `d-3841`)", "example: no row"),
    ("example", "library/team-incident-commander-guide.md", 116, "following the rollback of d-4986",
     "an example thread, no date: no row, id reserved"),
    ("example", "library/team-status-page-process.md", 197, "\"Rollback of deploy d-5120 failed\"",
     "an example of what never to publish; d-5120 is the real 2026-08-20 row"),
    ("example", "library/deploying-with-shipyard.md", 21, "`r-212`, `r-213`, and so on", "example names: api reached "
     "r-205 and payments r-210 by 2026-10-11, so no row uses r-211..r-213"),
    ("example", "library/deploying-with-shipyard.md", 63, "shipyard rollback payments --to r-211", "example: no row"),
    ("gap", "library/deploying-with-shipyard.md", 37, "Shipyard builds it and gives it the next number.",
     "payments jumps r-200 -> r-208 in one day. Read as releases that were built but never started (Shipyard numbers "
     "every release it builds); a row is a deploy that started, so r-201..r-207 on payments have no row"),
    ("not a deploy", "library/postmortem-api-partner-certificate.md", 43, "Ravi begins deployment and binding of the "
     "updated certificate across the load balancer endpoints.", "a certificate change in aws, not a deploy of api; no row"),
    ("not a deploy", "library/postmortem-payments-webhook-secret.md", 56, "Automated deployment script triggers a "
     "configuration reload", "a config reload, and the same page says no code deploys within 48 hours; no row"),
    ("state", "library/handover-2026-10-05.md", 60, "**Status:** Healthy on release `r-208`.",
     "true on 2026-10-05; r-210 went out 2026-10-08, so the table's state for r-208 is superseded"),
]


# ------------------------------------------------------------------ building
def monday(d):
    return d - dt.timedelta(days=d.weekday())


def weeks():
    m = monday(FIRST)
    while m <= LAST:
        yield m
        m += dt.timedelta(days=7)


def handover_weeks():
    """the Monday each handover's shift started (2025-11-24's note covers the week it is named for)"""
    out = set()
    for f in os.listdir(os.path.join(HERE, "..", "library")):
        if f.startswith("handover-"):
            d = dt.date.fromisoformat(f[9:19])
            out.add(d - dt.timedelta(days=7))
            out.add(d)                                   # the incoming week too: invented trouble stays away from both
    return out


def lane(service, when):
    """the old deploy tool runs one job at a time for the whole project; Shipyard gives api and payments a lane each"""
    return service if service in ("api", "payments") and when >= SHIPYARD else "old tool"


def build():
    rng = random.Random(SEED)
    rows = [dict(r) for r, _ in PINNED]
    quiet = [(svcs, T(a), T(b)) for svcs, a, b, *_ in QUIET]
    frozen = [(dt.date.fromisoformat(a), dt.date.fromisoformat(b)) for a, b, *_ in FREEZE]
    counts = {dt.date.fromisoformat(m): c for m, c, *_ in COUNTS}
    calm = handover_weeks()

    def free(service, start, mins):
        end = start + dt.timedelta(minutes=mins)
        if any(a <= start.date() <= b for a, b in frozen):
            return False
        if any(service in s and a < start < b for s, a, b in quiet):
            return False
        for r in rows:
            if lane(r["service"], r["started"]) == lane(service, start) and r["started"].date() == start.date():
                if start < r["finished"] + dt.timedelta(minutes=10) and r["started"] < end + dt.timedelta(minutes=10):
                    return False
            if r["service"] == service and abs((r["started"] - start).total_seconds()) < 3600:
                return False
        return True

    def place(service, m, days, note=None, state=None, hours=(13, 30, 17, 0)):
        lo, hi = hours[0] * 60 + hours[1], hours[2] * 60 + hours[3]
        days = [d for d in days if not any(a <= m + dt.timedelta(days=d) <= b for a, b in frozen)]
        if not days:
            return None                                          # a frozen week: nothing goes out
        for _ in range(400):
            day = m + dt.timedelta(days=rng.choice(days))
            if day < FIRST or day > LAST:
                continue
            minute = rng.randrange(lo, hi + 1, 5)
            start = dt.datetime.combine(day, dt.time(minute // 60 % 24, minute % 60))
            if minute >= 24 * 60:
                start = dt.datetime.combine(day + dt.timedelta(days=1), dt.time((minute - 1440) // 60, minute % 60))
            mins = rng.randint(*MINUTES[service]) + (6 if lane(service, start) != "old tool" else 0)
            if free(service, start, mins):
                names, weights = zip(*AUTHORS[service])
                rows.append({"id": None, "service": service, "started": start,
                             "finished": start + dt.timedelta(minutes=mins), "author": rng.choices(names, weights)[0],
                             "state": state, "note": note or rng.choice(NOTES[service])})
                return rows[-1]
        return None                                              # no room that week (a quiet span): one fewer; the
                                                                 # week counts are checked after

    for m in weeks():
        pinned = {s: sum(1 for r in rows if r["service"] == s and monday(r["started"].date()) == m) for s in SERVICES}
        if m in counts:
            want = counts[m]
            for s in SERVICES:
                assert want[s] >= pinned[s], (m, s)
        else:
            want = {"web": rng.choice([1, 2, 2, 2, 3, 3]), "api": rng.choice([1, 1, 2, 2, 2, 3]),
                    "payments": rng.choice([0, 1, 1, 1, 1, 1, 2]), "notifier": rng.choice([0, 1, 1, 1, 1, 2])}
        for s in SERVICES:
            if s in ("api", "payments") and m >= SHIPYARD.date() - dt.timedelta(days=6):
                continue                                          # the Shipyard weeks are pinned row by row
            n = want[s] - pinned[s] if m in counts else max(0, want[s] - pinned[s])
            for _ in range(n):
                place(s, m, [1, 3])                               # Tuesday or Thursday afternoon

    # trouble the pages never mention: only in weeks no handover covers
    open_weeks = sorted({monday(r["started"].date()) for r in rows if r["id"] is None and r["state"] is None}
                        - calm - set(counts))
    pick = rng.sample(open_weeks, 11)
    for i, m in enumerate(pick):
        cands = [r for r in rows if r["id"] is None and r["state"] is None and monday(r["started"].date()) == m
                 and r["started"] < SHIPYARD]
        r = rng.choice(cands)
        if i < 4:
            r["state"], r["note"] = "rolled back", r["note"] + "; rolled back after an error spike"
        elif i < 8:
            r["state"], r["note"] = "failed", "rollout stopped: health check failed"
        else:
            s = rng.choice(["api", "payments"])
            place(s, m, [1, 2, 3], note="fix for an open P1", hours=(23, 0, 23, 40))

    # ids: d-NNNN from the old tool, never one a page uses; r- ids are pinned
    used = set(RESERVED) | {r["id"] for r in rows if r["id"]}
    rows.sort(key=lambda r: (r["started"], r["service"]))
    for r in rows:
        if r["id"] is None:
            while True:
                i = f"d-{rng.randint(1, 9999):04d}"
                if i not in used:
                    break
            used.add(i)
            r["id"] = i
    # state: rolled back / failed stay; of the rest, each service's newest is live, the others superseded
    for s in SERVICES:
        mine = [r for r in rows if r["service"] == s]
        good = [r for r in mine if r["state"] not in ("rolled back", "failed")]
        for r in good:
            r["state"] = "superseded"
        good[-1]["state"] = "live"
    return rows


# ------------------------------------------------------------------ checking every page fact against the rows
def locate(page, words):
    """the line the words start on, or None when any part of them (split at ' ... ') is not on the page"""
    if page is None:
        return None
    text = open(os.path.join(HERE, "..", page)).read()
    flat = " ".join(text.split())
    parts = [" ".join(p.split()) for p in words.split(" ... ")]
    if not all(p in flat for p in parts):
        return None
    head = parts[0][:30]
    for n, line in enumerate(text.split("\n"), 1):
        if head in " ".join(line.split()):
            return n
    return 0                                                     # on the page, across a line break


def check(rows):
    out, bad = [], []

    def ok(kind, page, line, words, rows_, passed, how):
        line = locate(page, words)
        if page is not None and line is None:
            passed, how = False, "THE WORDS ARE NOT ON THE PAGE: " + how
        out.append({"kind": kind, "page": page, "line": line, "words": words,
                    "rows": [f"{r['id']} {r['service']} {fmt(r['started'])} {r['state']}" for r in rows_],
                    "agrees": passed, "how": how})
        if not passed:
            bad.append(out[-1])

    for r, srcs in PINNED:
        hit = [x for x in rows if x["service"] == r["service"] and x["started"] == r["started"]]
        good = len(hit) == 1 and (r["id"] is None or hit[0]["id"] == r["id"]) and \
            (r["state"] is None or hit[0]["state"] == r["state"])
        for page, line, words in srcs:
            ok("row", page, line, words, hit, good, "same id, service, day and time; state where the page says it")
    for svcs, a, b, page, line, words in QUIET:
        a, b = T(a), T(b)
        hit = [x for x in rows if x["service"] in svcs and a < x["started"] < b]
        ok("nothing in between", page, line, words, hit, not hit,
           f"no {'/'.join(svcs)} deploy started after {fmt(a)} and before {fmt(b)}")
    for a, b, page, line, words in FREEZE:
        a, b = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        hit = [x for x in rows if a <= x["started"].date() <= b]
        ok("freeze", page, line, words, hit, not hit, f"no deploy started {a} .. {b}")
    for m, want, page, line in COUNTS:
        m = dt.date.fromisoformat(m)
        wk = [x for x in rows if monday(x["started"].date()) == m]
        got = {s: sum(1 for x in wk if x["service"] == s) for s in SERVICES}
        tt = all(x["started"].weekday() in (1, 3) and 12 <= x["started"].hour < 18 for x in wk)
        clean = all(x["state"] not in ("rolled back", "failed") for x in wk)
        words = "Deploys this week: " + ", ".join(f"{s} {want[s]}" for s in SERVICES) + \
            "; all in the Tuesday and Thursday afternoon windows"
        if page == "library/handover-2026-04-06.md":
            words = ("| web | Aiko | 3 releases ... | api | Ravi | 2 releases ... | payments | Mei | 1 release ... "
                     "| notifier | Tom | 1 release")
        ok("week count", page, line, words, wk, got == want and tt and clean,
           f"week {m}: counted {got}; all Tue/Thu 12:00-17:59: {tt}; none rolled back or failed: {clean}")
    for m, page, line, words in NO_ROLLBACK:
        m = dt.date.fromisoformat(m)
        wk = [x for x in rows if monday(x["started"].date()) == m and x["state"] in ("rolled back", "failed")]
        ok("no rollback that week", page, line, words, wk, not wk, f"no rolled back or failed deploy in the week of {m}")
    old = sorted((x for x in rows if lane(x["service"], x["started"]) == "old tool"), key=lambda x: x["started"])
    clash = [b for a, b in zip(old, old[1:]) if b["started"] < a["finished"]]
    ok("one job at a time", "library/deploying-with-shipyard.md", None, "The old tool runs one job at a time for the "
       "whole project", clash, not clash, "no two deploys in the old tool overlap (d-5121 starts the minute d-5120 ends)")
    windows = [x for x in rows if (x["started"].weekday() == 4 and x["started"].hour >= 16)]
    ok("rule", "runbooks/handbook.md", 592, "No deploys between 22:00 and 07:00 JST, on Fridays after 16:00 JST, or during announced provider "
       "maintenance, except rollbacks and fixes for open P1s.",
       windows, not windows, "no deploy starts on a Friday after 16:00 (night deploys exist: the pages name two)")
    for kind, page, line, words, how in NOTED:
        out.append({"kind": kind, "page": page, "line": line, "words": words, "rows": [], "agrees": None, "how": how})
    return out, bad


def fmt(t):
    return t.strftime("%Y-%m-%dT%H:%M")


def as_csv(rows):
    f = io.StringIO()
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["id", "service", "started", "finished", "author", "state", "note"])
    for r in rows:
        w.writerow([r["id"], r["service"], fmt(r["started"]), fmt(r["finished"]), r["author"], r["state"], r["note"]])
    return f.getvalue()


SCHEMA = ("CREATE TABLE deploys (id TEXT, service TEXT, started TEXT, finished TEXT, author TEXT, state TEXT, "
          "note TEXT)")


def write_db(text, path):
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    con.execute(SCHEMA)
    rd = csv.reader(io.StringIO(text))
    next(rd)
    con.executemany("INSERT INTO deploys VALUES (?, ?, ?, ?, ?, ?, ?)", rd)
    con.commit()
    con.close()


if __name__ == "__main__":
    rows = build()
    text = as_csv(rows)
    facts, bad = check(rows)
    if bad:
        print(json.dumps(bad, indent=1))
        raise SystemExit(f"{len(bad)} page facts disagree with the table")
    canon = {"what": "every page fact about a deploy, and the rows that agree with it",
             "csv_md5": hashlib.md5(text.encode()).hexdigest(), "rows": len(rows), "facts": facts}
    canon_text = json.dumps(canon, indent=1, ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        print("csv md5", canon["csv_md5"], "rows", len(rows), "facts", len(facts), "all agree")
        raise SystemExit
    open(os.path.join(HERE, "deploys.csv"), "w").write(text)
    open(os.path.join(HERE, "CANON.json"), "w").write(canon_text)
    write_db(text, os.path.join(HERE, "deploys.db"))
    print("deploys.csv", len(rows), "rows, md5", canon["csv_md5"])
    print("CANON.json", len(facts), "facts,", sum(1 for f in facts if f["agrees"]), "checked and agree,",
          sum(1 for f in facts if f["agrees"] is None), "noted")
