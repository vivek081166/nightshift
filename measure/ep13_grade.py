"""EP13 grading helper, not episode code. No model calls.

    python3 measure/ep13_grade.py split p        # P answers cut into claims (one per list item / sentence), with the
                                                 # closest lines from the pages in the call, for hand grading
    python3 measure/ep13_grade.py near c1        # each C1 claim with the closest lines of the page it cites
    python3 measure/ep13_grade.py verify <file>  # every hand-grade quote is on the page it names, word for word
The closest lines are only a finder for the grader (word overlap); every grade is a reading of the page.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import lookup
from rules import SYSTEM

PAGES = {p["id"]: p for p in lookup.pages()}
PAGES["rules.SYSTEM"] = {"id": "rules.SYSTEM", "text": SYSTEM}
STOP = set("the a an and or of to in on for is are be it this that with as at by from your you if when not do does "
           "what how i we our was were has have can will should into than then them they their its any all".split())


def toks(s):
    return {w for w in re.findall(r"[a-z0-9][a-z0-9_.%-]*", s.lower()) if w not in STOP and len(w) > 1}


def nearest(claim, ids, k=2):
    c = toks(claim)
    scored = []
    for pid in ids:
        for i, line in enumerate(PAGES[pid]["text"].split("\n"), 1):
            t = toks(line)
            if t and c:
                scored.append((len(c & t) / len(c), pid, i, line.strip()))
    return sorted(scored, key=lambda s: -s[0])[:k]


def split(answer):
    """list items and sentences; markdown headings and empty lines dropped"""
    out = []
    for line in answer.split("\n"):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("```") or set(s) <= set("-*_ "):
            continue
        s = re.sub(r"^([*-]|\d+\.)\s+", "", s)
        if len(s) > 4:
            out.append(s)
    return out


def main():
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "split":
        d = json.load(open(f"runs/ep13/2026-10-12-{'p-plain' if arg == 'p' else arg}.json"))
        for q in d["questions"]:
            ids = q["pages_in_call"] + ["rules.SYSTEM"]
            print(f"===== {q['id']}  in call: {q['answer_page_in_call']}")
            for n, c in enumerate(split(q["answer"]), 1):
                print(f"[{n}] {c}")
                for score, pid, i, line in nearest(c, ids):
                    print(f"      {score:.2f} {pid}:{i}  {line[:230]}")
    elif cmd == "near":
        d = json.load(open(f"runs/ep13/2026-10-12-{'c1-pages' if arg == 'c1' else 'c2-quotes'}.json"))
        only = sys.argv[3].split(",") if len(sys.argv) > 3 else None
        for q in d["questions"]:
            if only and q["id"] not in only:
                continue
            print(f"===== {q['id']} [{q['kind']}] {q['question']}")
            print(f"      in call: {q['pages_in_call']}")
            for n, c in enumerate((q.get("answer") or {}).get("claims", []), 1):
                print(f"[{n}] ({c['page']}) {c['claim']}")
                if "quote" in c:
                    print(f"      QUOTE: {c['quote'][:300]!r}")
                for score, pid, i, line in nearest(c["claim"], [c["page"]] if c["page"] in PAGES else [], 2):
                    print(f"      {score:.2f} {pid}:{i}  {line[:230]}")
            for x in (q.get("answer") or {}).get("not_in_pages", []):
                print(f"   NOT_IN_PAGES: {x}")
    elif cmd == "verify":
        g = json.load(open(arg))
        bad = 0
        for qid, claims in g["grades"].items():
            for c in claims:
                for ref in c.get("refs", []):
                    if ref["quote"] not in PAGES[ref["page"]]["text"]:
                        bad += 1
                        print("NOT ON PAGE:", qid, ref["page"], ref["quote"][:90])
        print("quotes checked:", sum(len(c.get("refs", [])) for cl in g["grades"].values() for c in cl), "bad:", bad)


if __name__ == "__main__":
    main()
