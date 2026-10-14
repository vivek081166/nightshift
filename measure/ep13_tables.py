"""EP13: per-question answer grades and the per-kind tables (no model calls). Code grade as EP12 (truth groups,
case-insensitive substring); for C1/C2 the answer text is every claim plus the not_in_pages lines. Hand overrides
(read by me, each with why) are in HAND below."""
import json, os, sys, statistics
from collections import Counter
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "measure")); os.chdir(ROOT)
NOT_SAY = json.load(open("runs/ep13/not_say.json")) if os.path.exists("runs/ep13/not_say.json") else None
import importlib.util
spec = importlib.util.spec_from_file_location("ep12", "measure/ep12.py")
ep12_src = open("measure/ep12.py").read()
NOT_SAY = eval(ep12_src.split("NOT_SAY = ", 1)[1].split("\n\n", 1)[0])       # EP12's list, exactly

QS = {q["id"]: q for q in json.load(open("tickets/questions-ep13.json"))["questions"]}
KINDS = ["code", "other words", "hidden", "plain", "not in pages", "steps", "half"]


def code_grade(q, text, says_not):
    a = text.lower()
    says_not = says_not or any(w in a for w in NOT_SAY)
    if q["truth"] == ["NOT_IN_PAGES"]:
        return "said-not" if says_not else "needs-hand"
    hits = [any(alt.lower() in a for alt in g) for g in q["truth"]]
    wrong = [w for w in q["wrong"] if w.lower() in a]
    if q["kind"] == "half":
        return "right" if all(hits) and says_not and not wrong else ("said-not" if says_not and not any(hits) else "check")
    if all(hits) and not wrong:
        return "right"
    return "said-not" if says_not and not any(hits) else "check"


def answer_text(rec):
    if isinstance(rec.get("answer"), str):
        return rec["answer"], False
    a = rec.get("answer") or {}
    return " ".join(c["claim"] for c in a.get("claims", [])) + " " + " ".join(a.get("not_in_pages", [])), bool(a.get("not_in_pages"))


HAND = {  # (run, id): (grade, why)
    ("ep12-e1", "ow-kicked-out"): ("said-not", "EP12 hand grade"),
    ("c1", "ow-kicked-out"): ("said-not", "claims describe the 2024 SMS-code incident (on its page) and not_in_pages says no mass logout; no claim off the page"),
    ("c2", "ow-kicked-out"): ("said-not", "as C1"),
    ("c1", "hid-dst-2025"): ("said-not", "answer page (handover-2025-11-03) not in the call; describes the 2024 incident and says the pages do not cover 2025"),
    ("c2", "hid-dst-2025"): ("said-not", "as C1"),
    ("p", "half-cert-credits"): ("right", "'**3** integration partners' plus 'the pages do not say' the credit: the bold marks split the truth string"),
}


def grade_run(run, recs):
    out = {}
    for r in recs:
        q = QS[r["id"]]
        text, says = answer_text(r)
        g = code_grade(q, text, says)
        out[r["id"]] = HAND.get((run, r["id"]), (g, None))[0] if (run, r["id"]) in HAND or g != "check" else "CHECK"
        if q["truth"] == ["NOT_IN_PAGES"] and out[r["id"]] == "said-not":
            out[r["id"]] = "right"
    return out


def load(name):
    return json.load(open(f"runs/ep13/2026-10-12-{name}.json"))["questions"]


def per_kind(rows):
    out = {}
    for k in KINDS + ["all"]:
        sel = [r for r in rows if k == "all" or r["kind"] == k]
        if sel:
            out[k] = {"n": len(sel), **{x: sum(r[x] for r in sel) if isinstance(sel[0][x], (int, bool)) else None
                                         for x in sel[0] if x not in ("id", "kind", "grade", "wall_s", "prompt_tokens", "cost_usd")},
                      "right": sum(r["grade"] == "right" for r in sel), "said_not": sum(r["grade"] == "said-not" for r in sel),
                      "wrong": sum(r["grade"] == "wrong" for r in sel), "partial": sum(r["grade"] == "partial" for r in sel),
                      "prompt_tokens_per_q": round(sum(r["prompt_tokens"] for r in sel) / len(sel)),
                      "cost_usd_per_q": round(sum(r["cost_usd"] for r in sel) / len(sel), 5),
                      "median_wall_s": round(statistics.median(r["wall_s"] for r in sel), 2)}
    return out


def tables(runs, allg):
    import check
    from ep13_grade import PAGES
    ph = json.load(open("runs/ep13/2026-10-12-p-plain-hand-grades.json"))["grades"]
    c1h = json.load(open("runs/ep13/2026-10-12-c1-pages-hand-grades.json"))["grades"]
    c2h = json.load(open("runs/ep13/2026-10-12-c2-quotes-hand-grades.json"))["grades"]
    res = {}
    # P = EP12 E1 for the 40 + p-plain for the 30
    rows = []
    for r in runs["ep12-e1"]:
        q = QS[r["id"]]
        rows.append({"id": r["id"], "kind": q["kind"], "grade": allg["ep12-e1"][r["id"]],
                     "answer_page_in_call": bool(r.get("opened_answer_page")), "answerable": q["page"] is not None,
                     "claims": 0, "not_on_page": 0, "ambiguous": 0,
                     "prompt_tokens": r["prompt_tokens"], "cost_usd": r["cost_usd"], "wall_s": r["wall_s"]})
    for r in runs["p"]:
        q = QS[r["id"]]; g = ph[r["id"]]
        cl = [c for c in g if c["grade"] != "frame"]
        rows.append({"id": r["id"], "kind": q["kind"], "grade": allg["p"][r["id"]],
                     "answer_page_in_call": bool(r["answer_page_in_call"]), "answerable": True,
                     "claims": len(cl), "not_on_page": sum(c["grade"] in ("not-on-page", "wrong") for c in cl),
                     "ambiguous": sum(c["grade"] == "ambiguous" for c in cl),
                     "prompt_tokens": r["prompt_tokens"], "cost_usd": r["cost_usd"], "wall_s": r["wall_s"]})
    for r in rows:
        r["retrieval_miss"] = r["answerable"] and not r["answer_page_in_call"]
        r["generation_miss"] = r["answer_page_in_call"] and (r["grade"] in ("wrong", "partial") or r["not_on_page"] > 0)
    res["P"] = {"by_kind": per_kind(rows), "questions": rows}
    # C1
    rows = []
    for r in runs["c1"]:
        q = QS[r["id"]]; g = c1h[r["id"]]
        rows.append({"id": r["id"], "kind": q["kind"], "grade": allg["c1"][r["id"]], "answer_page_in_call": bool(r["answer_page_in_call"]),
                     "answerable": q["page"] is not None, "claims": len(g), "page_id_in_call": sum(r["page_id_check"]),
                     "cited_page_says_it": sum(c["grade"] == "supported" for c in g),
                     "cited_page_does_not_say": sum(c["grade"] == "cited-page-does-not-say" for c in g),
                     "ambiguous": sum(c["grade"] == "ambiguous" for c in g),
                     "not_on_any_page": sum(c["grade"] in ("not-on-page", "wrong") for c in g),
                     "not_in_pages_lines": len(r["answer"]["not_in_pages"]),
                     "prompt_tokens": r["prompt_tokens"], "cost_usd": r["cost_usd"], "wall_s": r["wall_s"]})
    res["C1"] = {"by_kind": per_kind(rows), "questions": rows}
    # C2
    rows = []
    for r in runs["c2"]:
        q = QS[r["id"]]; g = c2h[r["id"]]
        lv = Counter()
        for c in r["answer"]["claims"]:
            t = PAGES[c["page"]]["text"]
            lv[1 if c["quote"] in t else 2 if check.squash(c["quote"]) in check.squash(t)
               else 3 if check.squash(check.plain(c["quote"])) in check.squash(check.plain(t)) else 4] += 1
        rows.append({"id": r["id"], "kind": q["kind"], "grade": allg["c2"][r["id"]], "answer_page_in_call": bool(r["answer_page_in_call"]),
                     "answerable": q["page"] is not None, "claims": len(g),
                     "found_exact": lv[1], "found_after_case_space": lv[2], "found_only_after_marks": lv[3], "not_found": lv[4],
                     "found_camera": sum(c["found"] for c in g),
                     "false_alarms": sum(c.get("grade") == "reworded" for c in g),
                     "true_catches": sum(c.get("grade") == "not-on-page" for c in g),
                     "sampled_found": sum(bool(c.get("sample")) for c in g),
                     "sampled_found_stapled": sum(c.get("grade") == "quote-stapled" for c in g if c.get("sample")),
                     "sampled_found_part": sum(c.get("grade") == "quote-carries-part" for c in g if c.get("sample")),
                     "not_in_pages_lines": len(r["answer"]["not_in_pages"]),
                     "prompt_tokens": r["prompt_tokens"], "cost_usd": r["cost_usd"], "wall_s": r["wall_s"]})
    res["C2"] = {"by_kind": per_kind(rows), "questions": rows}
    json.dump(res, open("runs/ep13/2026-10-12-tables.json", "w"), indent=1)
    for k, v in res.items():
        print(k)
        for kind, t in v["by_kind"].items():
            print(f"  {kind:13}", {x: y for x, y in t.items() if y is not None})


if __name__ == "__main__":
    e1 = json.load(open("runs/ep12/2026-10-11-e1-code.json"))["questions"]
    runs = {"ep12-e1": e1, "p": load("p-plain"), "c1": load("c1-pages"), "c2": load("c2-quotes")}
    allg = {k: grade_run(k, v) for k, v in runs.items()}
    for k, g in allg.items():
        print(k, Counter(g.values()), [i for i, x in g.items() if x == "CHECK"])
    json.dump({"grades": allg, "hand_overrides": {f"{a}:{b}": {"grade": g, "why": w} for (a, b), (g, w) in HAND.items()}},
              open("runs/ep13/2026-10-12-answer-grades.json", "w"), indent=1)
    tables(runs, allg)

