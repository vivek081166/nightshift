"""EP10's screens from the saved runs (calls no model).

    python3 measure/ep10_screen.py trap        the trap question, looked up, as lookup.py prints it (a saved run)
    python3 measure/ep10_screen.py sizes       text sent with one question: carry 5 pages, carry every page, look it up
    python3 measure/ep10_screen.py questions   twenty questions, looked up, one row each
    python3 measure/ep10_screen.py tally SHAPE carry-50 | fix-dates | fix-notice | fix-archived: ten runs, one row
    python3 measure/ep10_screen.py gate        lookup.py against the measured runs: pages, list, carry text, notice

Every number comes from runs/ep10/2026-10-07-*.json; the right/wrong verdicts are the hand grades
(m4-hand-grades.json, m2-hand-grades.json), not the code grades.
"""
import hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import lookup                                       # noqa: E402  (reads library/INDEX.json from ROOT)

RUNS = os.path.join(ROOT, "runs", "ep10")
RETIRED, SHIPYARD = "payments-rollback-runbook", "deploying-with-shipyard"
QUESTION = "sy-trap-how"
WORDS = {10: "ten"}


def load(name):
    return json.load(open(os.path.join(RUNS, f"2026-10-07-{name}.json")))


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()


def first_item(shape, qid=QUESTION, run=1):
    return next(i for i in load(f"m4-{shape}")["items"] if i["qid"] == qid and i["run"] == run)


def trap():
    item = first_item("model-50")
    print("a saved run\n")
    for page_id in item["reads"]:
        print("opened ", page_id)
    lookup.show(item["text"])


def sizes():
    rows = [("carry the handbook + 4 pages", first_item("carry-5")), ("carry every page", first_item("carry-50")),
            ("look it up", first_item("model-50"))]
    print("text sent with one question (tokens) · saved runs\n")
    for label, item in rows:
        print(f"{label:30} {item['totals']['prompt_tokens']:>8,}")


def questions():
    asked = {q["id"]: q["question"] for q in json.load(open("tickets/questions.json"))["questions"]}
    verdict = {"right": "right", "right (said not in pages)": "right", "wrong": "wrong",
               "said-not-in-pages": "half answered"}
    print("twenty questions · looking it up · a saved run\n")
    for row in load("m2-hand-grades")["model-50"]["rows"]:
        words = asked[row["id"]].split()
        head = " ".join(words[:7]) + (" ..." if len(words) > 7 else "")
        print(f"{head[:56]:58} {verdict[row['hand']]}")


def tally(shape):
    grades = load("m4-hand-grades")["shapes"][shape]["items"]
    reads = {(i["qid"], i["run"]): i.get("reads") or [] for i in load(f"m4-{shape}")["items"]}
    n = len(grades)
    right = sum(g["hand"] == "right" for g in grades)
    head = {"carry-50": "carry every page", "fix-dates": "dates in the list", "fix-notice": "the retired line",
            "fix-archived": "moved out"}[shape]
    row = f"{head} · {WORDS[n]} runs, both wordings: right {right}"
    r = [reads[(g["qid"], g["run"])] for g in grades]
    if shape == "fix-dates":
        row += (f" · wrong {n - right} · old runbook opened first {sum(x[:1] == [RETIRED] for x in r)}"
                f" · then Shipyard {sum(x[:1] == [RETIRED] and SHIPYARD in x[1:] for x in r)}")
    elif shape == "fix-notice":
        row += f" · old runbook, then Shipyard {sum(x[:2] == [RETIRED, SHIPYARD] for x in r)}"
    elif shape == "fix-archived":
        row += f" · Shipyard first {sum(x[:1] == [SHIPYARD] for x in r)}"
    print(row)


def gate():
    """lookup.py must send what the measured runs sent, byte for byte. Prints one line per check; exits 1 on a FAIL."""
    fails, checks = [], 0

    def check(ok, what):
        nonlocal checks
        checks += 1
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    pages = lookup.pages()
    frozen = {r["id"]: r for r in load("a-freeze")["pages"]}
    check(len(pages) == len(frozen) == 67, f"page count {len(pages)} == frozen {len(frozen)} == 67")
    bad = [p["id"] for p in pages if md5(p["text"]) != frozen[p["id"]]["md5"]]
    check(not bad, f"every page md5 == a-freeze ({len(pages) - len(bad)}/{len(pages)} match{'; bad ' + ', '.join(bad) if bad else ''})")
    check([p["id"] for p in pages] == list(frozen), "page order == a-freeze order (INDEX order)")

    head = ("\nThe team's pages are listed below, one per line as id: title. To read a page, call read_page with "
            "its id. You may read up to 4 pages.\n\n")
    for shape, dates, keep in [("model-50", False, pages), ("fix-dates", True, pages),
                               ("fix-archived", False, [p for p in pages if p["id"] != RETIRED])]:
        sent = first_item(shape)["calls"][0]["request"]["systemInstruction"]["parts"][0]["text"]
        mine = lookup.SYSTEM + head + lookup.contents_list(keep, dates)
        check(sent == mine, f"{shape}: look-up systemInstruction byte-match ({len(mine)} chars, "
                            f"{len(lookup.contents_list(keep, dates).splitlines())} list lines)")
    req = first_item("model-50")["calls"][0]["request"]
    check(req["contents"][0]["parts"][0]["text"] == lookup.ASK.format(q=next(
        q["question"] for q in json.load(open("tickets/questions.json"))["questions"] if q["id"] == QUESTION)),
        "user turn == the measured question + ask")
    check(req["tools"] == [{"functionDeclarations": [lookup.READ_PAGE]}], "read_page declaration == measured")
    result = first_item("model-50")["calls"][0]["tool_results"][0]["result"]
    check(sorted(result) == ["id", "text", "title"], f"page sent back with keys {sorted(result)}")

    hb_text = open("runbooks/handbook.md").read()
    hb_label = next(d for d in load("a-freeze")["documents"] if d["source"] == "runbooks/handbook.md")
    labels = {hb_text: f"<omitted handbook.md: md5 {md5(hb_text)}, {hb_label['tokens']} tokens by countTokens>"}
    labels.update({p["text"]: f"<omitted {p['id']}: md5 {md5(p['text'])}, {frozen[p['id']]['tokens']} tokens by countTokens>"
                   for p in pages if not p["id"].startswith("handbook-")})
    carried = (hb_text + "\n\nThe team's other pages follow.\n" + "".join(
        f"\n----- page: {p['title']} -----\n\n{p['text']}" for p in pages if not p["id"].startswith("handbook-")))
    redacted = json.dumps(carried, ensure_ascii=False)
    for text, label in sorted(labels.items(), key=lambda kv: -len(kv[0])):
        redacted = redacted.replace(json.dumps(text, ensure_ascii=False)[1:-1], label)
    sent = load("m4-carry-50")["cache"]["create"]["request"]["systemInstruction"]["parts"][0]["text"]
    check(json.loads(redacted) == sent, "carry: every page whole, byte-match with the measured cache body (md5 + token labels)")

    notice = ('> RETIRED 2026-09-28: payments no longer deploys or rolls back with dtool. '
              'See the page "Deploying with Shipyard".\n')
    old = open(f"library/{RETIRED}.md").read()
    check(old.startswith("# "), "library page is the measured one (no notice on line 1)")
    label = first_item("fix-notice")["calls"][0]["tool_results"][0]["result"]["text"]
    check(md5(notice + old) in label, f"take E: notice + original md5 {md5(notice + old)[:8]} in the measured page ({label[9:60]})")

    found = []
    for shape in ["model-50", "carry-50", "fix-dates", "fix-notice", "fix-archived"]:
        for item in load(f"m4-{shape}")["items"]:
            text = item["text"] or ""
            key = "shipyard rollback" if "shipyard rollback" in text else "dtool revert"
            found.append(next((i for i, line in enumerate(render(text)) if key in line), None))
    check(None not in found, f"the marked command is printed in {len(found) - found.count(None)} of {len(found)} "
                             f"measured answers (latest at printed line {max(f for f in found if f is not None) + 1})")

    print(f"\n{checks} checks, {len(fails)} failed")
    sys.exit(1 if fails else 0)


def render(text):
    """what lookup.show() prints, captured line by line"""
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        lookup.show(text)
    return buf.getvalue().split("\n")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "tally":
        tally(sys.argv[2])
    elif mode in ("trap", "sizes", "questions", "gate"):
        globals()[mode]()
    else:
        print(__doc__)
