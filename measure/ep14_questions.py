"""EP14 measurement harness, not episode code: the 20 questions, their truth, and the free retrieval check.

    .venv/bin/python measure/ep14_questions.py     # writes tickets/questions-ep14.json (no model call)

Truth is plain Python over deploys/deploys.csv rows, no SQL: each question is a filter (a count) or "the newest
row before a time" (latest). Every question carries the row ids it counted, the definition used, the pages that
hold any part of it (from deploys/CANON.json: a page fact whose row was counted, or a week count inside the span),
and keyword search's top 5 for the question exactly as lookup.py --search sends it.
"""
import csv, datetime as dt, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

TODAY = "Today is Monday 2026-10-12 (JST). Last week means Monday 2026-10-05 to Sunday 2026-10-11."
EVERY_ROW = "every row that started in the span counts: a rolled-back deploy still went out, a failed one still started"


def rows():
    out = []
    for r in csv.DictReader(open("deploys/deploys.csv")):
        r["at"] = dt.datetime.fromisoformat(r["started"])
        out.append(r)
    return out


def day(s):
    return dt.date.fromisoformat(s)


def between(a, b):
    a, b = day(a), day(b)
    return lambda r: a <= r["at"].date() <= b


def label(r):
    """d-4471 and r-200 appear twice in the table, so a counted row is named by id and start"""
    return f"{r['id']} {r['service']} {r['started']}"


# kind, question (typed as on-call types it), first day, last day, service (None = all), extra test, definition
ANY = None
COUNT = [
    ("week", "how many deploys went out last week?", "2026-10-05", "2026-10-11", ANY, None,
     "last week = Mon 2026-10-05 .. Sun 2026-10-11 JST; " + EVERY_ROW),
    ("week", "how many deploys went out between 2026-07-27 and 2026-08-02?", "2026-07-27", "2026-08-02", ANY, None,
     "both days included; " + EVERY_ROW),
    ("week", "how many api deploys last week?", "2026-10-05", "2026-10-11", "api", None,
     "last week as above; api rows only; " + EVERY_ROW),
    ("week", "how many deploys did we do the week of feb 9 2026?", "2026-02-09", "2026-02-15", ANY, None,
     "the week of = Mon 2026-02-09 .. Sun 2026-02-15; " + EVERY_ROW),
    ("week", "how many web deploys the week of 2025-07-21?", "2025-07-21", "2025-07-27", "web", None,
     "Mon 2025-07-21 .. Sun 2025-07-27; web rows only; " + EVERY_ROW),
    ("span", "how many deploys went out in september?", "2026-09-01", "2026-09-30", ANY, None,
     "september = 2026-09-01 .. 2026-09-30 (the last one before today); " + EVERY_ROW),
    ("span", "how many payments deploys in august?", "2026-08-01", "2026-08-31", "payments", None,
     "august = 2026-08; payments rows only; " + EVERY_ROW),
    ("span", "how many deploys did we do in Q3 2026?", "2026-07-01", "2026-09-30", ANY, None,
     "Q3 = 2026-07-01 .. 2026-09-30; " + EVERY_ROW),
    ("span", "how many api deploys in 2025?", "2025-01-01", "2025-12-31", "api", None,
     "calendar 2025; api rows only; " + EVERY_ROW),
    ("span", "how many web deploys since api and payments moved to shipyard?", "2026-09-28", "2026-10-11", "web", None,
     "the move was 2026-09-28 (that day included) .. today; web rows only; " + EVERY_ROW),
    ("span", "how many deploys in the last 30 days?", "2026-09-12", "2026-10-11", ANY, None,
     "the 30 days before today: 2026-09-12 .. 2026-10-11; " + EVERY_ROW),
    ("filter", "how many deploys got rolled back since the start of 2025?", "2025-01-01", "2026-10-11", ANY,
     lambda r: r["state"] == "rolled back", "rows with state 'rolled back' that started 2025-01-01 or later"),
    ("filter", "how many deploys failed in 2024?", "2024-01-01", "2024-12-31", ANY,
     lambda r: r["state"] == "failed", "rows with state 'failed' that started in 2024"),
    ("filter", "how many deploys went out between 22:00 and 07:00 JST since 2025?", "2025-01-01", "2026-10-11", ANY,
     lambda r: r["at"].hour >= 22 or r["at"].hour < 7,
     "started at 22:00 or later or before 07:00 JST, 2025-01-01 or later; P1 fixes and the rolled-back one count"),
    ("filter", "how many deploys did Daniel do in 2026?", "2026-01-01", "2026-12-31", ANY,
     lambda r: r["author"] == "Daniel", "rows with author Daniel that started in 2026; " + EVERY_ROW),
    ("filter", "how many payments releases has shipyard done?", "2024-01-01", "2026-10-11", "payments",
     lambda r: r["id"].startswith("r-"),
     "payments rows with an r- id (Shipyard's release list): r-200, the first one cut on the day of the move, and the "
     "rolled-back r-209 both count"),
]


def keeps(lo, hi, svc, extra):
    lo, hi = day(lo), day(hi)
    return lambda r: lo <= r["at"].date() <= hi and (svc is None or r["service"] == svc) and (extra is None or extra(r))


LATEST = [  # kind, question, service, before (JST), what the answer must name, definition
    ("latest", "what was the last payments deploy before the 2025-11-18 checkout timeouts?", "payments",
     "2025-11-18T02:21", "id or version", "the newest payments row that started before the first customer ticket at "
     "02:21 JST on 2025-11-18 (the page calls it v2.31)"),
    ("latest", "when did api last deploy?", "api", "2026-10-12T00:00", "date",
     "the newest api row before today"),
    ("latest", "what was the last notifier deploy before the queue stalled on 2026-07-28?", "notifier",
     "2026-07-28T14:12", "id", "the newest notifier row that started before the first worker crash at 14:12 JST"),
    ("latest", "when did payments last deploy before the stripe webhook incident on 2026-03-03?", "payments",
     "2026-03-03T14:12", "date", "the newest payments row that started before the webhooks began failing at 14:12 JST"),
]


def holding_pages(counted, span=None):
    """pages with a fact about a counted row, plus week-count lines whose week overlaps the span (lo, hi, extra):
    a count line holds part of a plain count, never of a filter it does not break down (state, hour, author, id)"""
    canon = json.load(open("deploys/CANON.json"))["facts"]
    want = {f"{r['id']} {r['service']} {r['started']}" for r in counted}
    pages = {}
    for f in canon:
        for line in f["rows"]:
            key = " ".join(line.split()[:3])
            if f["kind"] in ("row",) and key in want:
                pages.setdefault(f["page"], []).append(f["line"])
        if f["kind"] == "week count" and span and f["page"]:
            m = day(f["how"].split()[1].rstrip(":"))
            lo, hi, extra = span
            in_week = [r for r in counted if m <= r["at"].date() <= m + dt.timedelta(days=6)]
            if extra is None and in_week:
                pages.setdefault(f["page"], []).append(f["line"])
    return [{"page": p, "lines": sorted(set(x for x in ls if x))} for p, ls in sorted(pages.items())]


def merge(holds):
    out = {}
    for h in holds:
        o = out.setdefault(h["page"], {"page": h["page"], "lines": []})
        o["lines"] = sorted(set(o["lines"] + h["lines"]))
        if "part" in h:
            o["part"] = h["part"]
    return list(out.values())


def page_id(path):
    import lookup
    by_src = {p["source"]: p["id"] for p in lookup.INDEX}
    return by_src.get(path, path)


def main():
    import lookup, search
    R = rows()
    pages = lookup.pages()
    out = []
    n = 0
    for kind, q, lo, hi, svc, extra, definition in COUNT:
        n += 1
        counted = [r for r in R if keeps(lo, hi, svc, extra)(r)]
        holds = holding_pages(counted, (lo, hi, extra))
        rec = {"id": f"q{n:02d}", "kind": kind, "question": q, "truth": len(counted), "answer_type": "count",
               "definition": definition, "counted": [label(r) for r in counted]}
        rec["also"] = {"without_rolled_back_or_failed": sum(1 for r in counted if r["state"] not in
                                                            ("rolled back", "failed")),
                       "distinct_ids": len({(r["id"], r["service"]) for r in counted})}
        rec["holding_pages"] = holds
        out.append(rec)
    for kind, q, svc, before, names, definition in LATEST:
        n += 1
        b = dt.datetime.fromisoformat(before)
        mine = sorted((r for r in R if r["service"] == svc and r["at"] < b), key=lambda r: r["at"])
        last = mine[-1]
        rec = {"id": f"q{n:02d}", "kind": kind, "question": q, "answer_type": names,
               "truth": {"id": last["id"], "started": last["started"], "note": last["note"], "state": last["state"]},
               "definition": definition, "counted": [label(last)], "holding_pages": holding_pages([last])}
        canon = json.load(open("deploys/CANON.json"))["facts"]
        for f in canon:          # a page that rules a span out ("no deploys within 48 hours") holds part of it
            if f["kind"] == "nothing in between" and f"no {svc} deploy" in f["how"] and \
                    f["how"].split("before ")[-1][:10] == before[:10]:
                rec["holding_pages"].append({"page": f["page"], "lines": [f["line"]], "part": f["words"]})
        out.append(rec)
    for rec in out:
        rec["holding_pages"] = merge(rec["holding_pages"])
        top = [p["id"] for p in search.keyword_search(rec["question"], pages, 5)]
        held = [page_id(h["page"]) for h in rec["holding_pages"]]
        rec["keyword_top5"] = top
        rec["holding_page_ids"] = held
        rec["holding_page_in_top5"] = [h for h in held if h in top]
    doc = {"what": "EP14 questions: answers that are not on any page. Truth from deploys/deploys.csv by plain Python "
                   "(measure/ep14_questions.py), never SQL. Frozen before the first model call.",
           "today_line": TODAY, "csv_md5": json.load(open("deploys/CANON.json"))["csv_md5"], "questions": out}
    json.dump(doc, open("tickets/questions-ep14.json", "w"), indent=1, ensure_ascii=False)
    for rec in out:
        t = rec["truth"] if isinstance(rec["truth"], int) else f"{rec['truth']['id']} {rec['truth']['started']}"
        print(f"{rec['id']} {rec['kind']:6} {str(t):26} held:{len(rec['holding_page_ids'])} "
              f"in-top5:{len(rec['holding_page_in_top5'])}  {rec['question']}")


if __name__ == "__main__":
    main()
