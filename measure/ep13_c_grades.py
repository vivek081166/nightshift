"""EP13: writes the C1 and C2 hand-grade files from my reading of every claim against the page it cites.
C1: every claim (does the CITED page say it?). C2: every claim whose quote is not found, the 20-claim sample of
found claims (seed 13, runs/ep13/2026-10-12-c2-found-sample-ids.json), and the full screen of the other found claims."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "measure")); os.chdir(ROOT)
from ep13_grade import nearest, PAGES
import check

R = lambda page, quote: {"page": page, "quote": quote}
# ---------------------------------------------------------------- C1
C1_SPECIAL = {
    ("pg-log-access", 3): {"grade": "cited-page-does-not-say",
        "refs": [R("team-access-requests", "File the ticket at least one full working day prior to when you are scheduled to begin shadowing."),
                 R("team-oncall-onboarding", "Get log search and dashboard access at least a week before the first shadow shift")],
        "note": "the claim's 'at least a week before your first shadow shift' is on team-oncall-onboarding (also in the call), "
                "not on the cited team-access-requests, which says one full working day. Page id real, in the call, "
                "and that page does not say it. The fact itself is true (another page in the call)."},
    ("st-api-rollback", 2): {"grade": "ambiguous",
        "refs": [R("deploying-with-shipyard", "shipyard rollback payments --to r-211"),
                 R("deploying-with-shipyard", "Use the release just below the `live` one in the list. Shipyard asks you to type the service name to confirm."),
                 R("handbook-5", "Run `shipyard rollback api --to <previous release>`")],
        "note": "the cited page gives the command for payments (r-211); the api form is on handbook-5 (also in the call). "
                "Same procedure with the service name swapped: true, but not word for word on the cited page."},
    ("hid-cache-ratio", 2): {"grade": "ambiguous",
        "refs": [R("handover-2026-08-17", "The cloudflare edge cache hit ratio fell from 92 % to 61 % on Wednesday")],
        "note": "the page says only 'on Wednesday'; the claim pins it to 'the week of 2026-08-17' (the note's title). "
                "A handover describes the week before, so the date is the model's inference and probably a week late."},
}
C1_REFS = {
    ("st-two-sent", 6): [R("howto-trace-a-refund", "Never modify or retry a transaction directly against Stripe's production API."),
                         R("howto-trace-a-refund", "Never manually adjust merchant balances or fee subtractions."),
                         R("howto-trace-a-refund", "Never issue manual compensating refunds through the Stripe dashboard."),
                         R("howto-trace-a-refund", "manual reversal disputes")],
    ("hid-dst-2025", 2): [R("handover-2025-11-24", "The shift covering the week of 2025-11-24 was generally stable, dominated primarily by seasonal November partner traffic")],
    ("st-crawler", 4): [R("handover-2026-04-06", "The status class breakdown showed a spike concentrated purely in `2xx` and `304` responses."),
                        R("handover-2026-04-06", "Server-side p95 page load remained steady at 240 ms")],
    ("ow-kicked-out", 2): [R("postmortem-notifier-sms-codes-japan", "Customers already logged in to browser sessions or native mobile applications were unaffected.")],
    ("code-pay-4031", 2): [R("handover-2025-11-03", "on Thursday Leo raised the 3-D Secure wait from 10 s to 25 s"),
                           R("handover-2025-11-03", "PAY-4031 has not come back since.")],
    ("code-ntf-3318", 2): [R("handover-2026-03-02", "Priya is looking at the sign-up form to address input validation so clients cannot submit voice-only landline numbers for text alerts.")],
    ("pg-log-access", 2): [R("team-access-requests", "Post the ticket link in `#access` in chat.")],
    ("st-admin-deletions", 3): [R("handbook-5", "**Owner.** Aiko.")],
    ("st-api-rollback", 6): [R("handbook-5", "Rolling back two or more releases needs Ravi.")],
}
d = json.load(open("runs/ep13/2026-10-12-c1-pages.json"))
g1 = {}
for q in d["questions"]:
    out = []
    for n, c in enumerate(q["answer"]["claims"], 1):
        key = (q["id"], n)
        if key in C1_SPECIAL:
            out.append({"n": n, "page": c["page"], "claim": c["claim"], **C1_SPECIAL[key]}); continue
        refs = C1_REFS.get(key) or [R(c["page"], nearest(c["claim"], [c["page"]], 1)[0][3])]
        out.append({"n": n, "page": c["page"], "claim": c["claim"], "grade": "supported", "refs": refs})
    g1[q["id"]] = out
json.dump({"what": "C1 hand grades: every claim read against the page it CITES. supported (refs = the cited page's "
                   "line), cited-page-does-not-say (the miss a page id alone cannot see), ambiguous (said why), "
                   "not-on-page (no page in the call says it), wrong (contradicts a page).",
           "run": "runs/ep13/2026-10-12-c1-pages.json", "grades": g1},
          open("runs/ep13/2026-10-12-c1-pages-hand-grades.json", "w"), indent=1, ensure_ascii=False)

# ---------------------------------------------------------------- C2
NOT_FOUND = {
    ("st-crawler", 2): ("reworded", R("handover-2026-09-28", "Logged a ticket for Aiko about crawler limits to decide if we want stricter rate limiting on public profiles."),
                        "the page says 'Logged a ticket', the quote 'Log a ticket'; one word changed"),
    ("st-admin-deletions", 2): ("reworded", R("web-runbook-2024", "- **Suspicious bulk activity:** If an alert flags abnormal account modifications or deletions from a single admin session (e.g., alert rule `web-admin-bulk`), do not attempt to mitigate by restarting nodes. Immediately page Aiko."),
                        "two bullets joined into one quote, the bold label '**Irreversible actions:**' dropped; every word otherwise on the page"),
    ("st-trace-refund", 2): ("reworded", R("howto-trace-a-refund", "2. Restrict the time picker to 2 hours before and after the alleged cancellation."),
                        "numbered steps quoted across a ```text code fence the quote leaves out"),
    ("st-trace-refund", 4): ("reworded", R("howto-trace-a-refund", "2. If the line exists, the cycle is complete."),
                        "quoted across a ```text code fence the quote leaves out"),
    ("st-template-actions", 2): ("reworded", R("postmortem-notifier-template-crash", "an execution attempt count of $\\ge 2$"),
                        "the page writes '$\\ge 2$' (LaTeX), the quote '≥ 2'"),
}
SAMPLE_NOTES = {("st-template-actions", 4): "partly: the quote carries the visibility-timeout item; the claim's second item "
                "(the status page drill) is not in the quote but is on the same page (the drill row of the table)"}
SCREEN = {  # found claims, outside the sample, whose quote carries only part (the rest is on the same page)
    ("st-template-actions", 3): "the claim also states the api input-validation item; the quote carries only the template item; both on the page",
    ("ow-taken-time", 1): "the claim adds 'twice a year (around March, October, and November)'; that is on the same page (7.14), not in the quote",
}
d = json.load(open("runs/ep13/2026-10-12-c2-quotes.json"))
sample = {tuple(x) for x in json.load(open("runs/ep13/2026-10-12-c2-found-sample-ids.json"))}
g2 = {}
for q in d["questions"]:
    out = []
    for n, c in enumerate(q["answer"]["claims"], 1):
        key = (q["id"], n)
        ok = check.found(c["quote"], PAGES[c["page"]]["text"])
        rec = {"n": n, "page": c["page"], "claim": c["claim"], "found": ok}
        if not ok:
            grade, ref, why = NOT_FOUND[key]
            rec.update({"grade": grade, "refs": [ref], "note": why})
        elif key in sample:
            rec.update({"sample": True, "grade": "quote-carries-claim" if key not in SAMPLE_NOTES else "quote-carries-part",
                        **({"note": SAMPLE_NOTES[key]} if key in SAMPLE_NOTES else {})})
        elif key in SCREEN:
            rec.update({"grade": "quote-carries-part", "note": SCREEN[key]})
        out.append(rec)
    g2[q["id"]] = out
json.dump({"what": "C2 hand grades. found = check.found (find box; again without markdown marks). Every NOT found claim "
                   "graded: reworded (the page says it; a false alarm) or not-on-page (a true catch). Sample: 20 found "
                   "claims (seed 13): quote-carries-claim / quote-carries-part / quote-stapled (the claim is not on the "
                   "page). Beyond the sample, every found claim was screened (claim words and numbers not in its quote) "
                   "and the flagged ones read; none was off the page; two carried only part.",
           "run": "runs/ep13/2026-10-12-c2-quotes.json", "check_py_md5_now": __import__("hashlib").md5(open("check.py", "rb").read()).hexdigest(),
           "grades": g2}, open("runs/ep13/2026-10-12-c2-quotes-hand-grades.json", "w"), indent=1, ensure_ascii=False)
from collections import Counter
print("C1", Counter(c["grade"] for v in g1.values() for c in v))
print("C2", Counter(c.get("grade", "found-unsampled") for v in g2.values() for c in v))
