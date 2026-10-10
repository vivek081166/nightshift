"""EP11 hand-check helper, written AFTER reading extractor output (post hoc, not the scorer).

For every row the frozen scorer marks not intact, it sorts the failure into one kind, so a person can eye each kind:
  artefact     the row passes once a line-end hyphen is rejoined ("on-\\ncall") and ligatures are expanded (ﬁ -> fi)
  own-lines    every word of the row sits in the row's own lines, but a wrapped cell is split by the next column's
               words on the same line (layout text): nothing from another row is mixed in
  columns      the row's first cell stands alone and the next line is another row's first cell: the table came out
               one column after another, so a time is no longer next to its event
  missing      some of the row's words are not on the page at all (OCR misread, dropped cell, empty page)
  mixed        the row's words are there but another row's cell sits inside its lines
    python3 measure/ep11_handcheck.py      # writes runs/ep11/2026-10-08-p-handcheck.json
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "measure"))
from ep11_score import norm, row_intact_strict   # noqa: E402

S = json.load(open(os.path.join(ROOT, "runs", "ep11", "2026-10-08-p-scores.json")))
PDFDIR = os.path.join(ROOT, "library", "pdf")


def fix(s):
    s = s.replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"-\n\s*", "-", s)


def lead(line):
    return norm(re.sub(r"^[\s|*#>-]+", "", line))


def kind_of(raw, row, others):
    if row_intact_strict(norm(fix(raw)), row, others):
        return "artefact"
    lines = [l for l in raw.replace("\f", "\n").split("\n")]
    first = norm(row[0])[:14]
    other_firsts = [norm(r[0])[:14] for r in others if norm(r[0])[:14] != first]
    words = set(re.findall(r"\S+", norm(" ".join(row))))
    page_words = set(re.findall(r"\S+", norm(raw)))
    if not words <= page_words:
        return "missing"
    for k, line in enumerate(lines):
        if not lead(line).startswith(first):
            continue
        nxt = next((lead(l) for l in lines[k + 1:] if l.strip()), "")
        if lead(line) == norm(row[0]) and any(nxt.startswith(o) for o in other_firsts):
            return "columns"
        span = [line]
        for l2 in lines[k + 1:]:
            if any(lead(l2).startswith(o) for o in other_firsts):
                break
            span.append(l2)
            if sum(map(len, span)) > 1500:
                break
        got = set(re.findall(r"\S+", norm(" ".join(span))))
        if words <= got:
            own = norm(" ".join(row))
            foreign = {norm(c) for r in others for c in r if len(norm(c)) > 3 and norm(c) not in own}
            if any(f in norm(" ".join(span)) for f in foreign):
                return "mixed"
            return "own-lines"
    return "mixed"


out = {"how": __doc__.strip().split("\n")[0], "per_method": {}}
for m, docs in S["detail"].items():
    res = {"kinds": {}, "rows": []}
    for slug, e in docs.items():
        truth = json.load(open(os.path.join(PDFDIR, slug + ".truth.json")))
        raw_all = open(os.path.join(ROOT, "runs", "ep11", "parsed", m, slug + ".txt")).read()
        pages = [raw_all] * truth["pages"] if m.startswith("P6") else raw_all.split("\f")
        for p in e["pages"]:
            raw = pages[p["page"] - 1] if p["page"] - 1 < len(pages) else ""
            for b in p["bad_rows"]:
                tab = next(t for t in truth["tables"] if t["name"] == b["table"])
                others = [r for r in tab["rows"] if r != b["row"]]
                k = "missing" if not raw.strip() else kind_of(raw, b["row"], others)
                res["kinds"][k] = res["kinds"].get(k, 0) + 1
                res["rows"].append({"slug": slug, "page": p["page"], "table": b["table"], "first_cell": b["row"][0],
                                    "kind": k})
    out["per_method"][m] = res
    print(m, res["kinds"])
json.dump(out, open(os.path.join(ROOT, "runs", "ep11", "2026-10-08-p-handcheck.json"), "w"), indent=1,
          ensure_ascii=False)
