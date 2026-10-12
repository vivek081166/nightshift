"""EP12 harness: check the drafted pages against the spec and the questions (no model calls)."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
spec = json.load(open("library/SPEC-ep12.json"))
qs = json.load(open("tickets/questions-ep12.json"))["questions"]
new = {os.path.basename(p["file"])[:-3]: open(p["file"]).read() for p in spec["pages"]}
old = {}
for f in sorted(os.listdir("library")):
    if f.endswith(".md") and f[:-3] not in new:
        old[f[:-3]] = open("library/" + f).read()
old["handbook"] = open("runbooks/handbook.md").read()
for f in os.listdir("runs/ep11/camera/pages-after-k2"):
    old["pages/" + f[:-3]] = open("pages/" + f).read() or open("runs/ep11/camera/pages-after-k2/" + f).read()
allp = {**old, **new}
bad = 0
for p in spec["pages"]:
    pid = os.path.basename(p["file"])[:-3]; t = new[pid]
    if not t.startswith("# " + p["title"] + "\n"):
        print("TITLE", pid, t.split("\n")[0]); bad += 1
    for w in ["dtool", "allowance", "http://", "https://", "@", "drain-checkouts", "shipyard rollback"]:
        if w.lower() in t.lower():
            print("FORBIDDEN", pid, w); bad += 1
    if "shipyard" in t.lower() and pid != "handover-2026-09-28":
        print("SHIPYARD", pid); bad += 1
    if re.search(r"\broll(ed)? ?back\b", t, re.I):
        for m in re.finditer(r"[^\n]*\broll(ed|ing)? ?back[^\n]*", t, re.I):
            print("ROLLBACK-MENTION", pid, "|", m.group(0).strip()[:160])
# codes
codes = spec["error_codes"]
for c in codes:
    where = [k for k, v in allp.items() if c in v]
    planted = [p["date"] for p in spec["pages"] if any(c in f for f in p["facts"])]
    want = ["handover-" + d for d in planted]
    if sorted(where) != sorted(want):
        print("CODE", c, "in", where, "want", want); bad += 1
    for k in where:
        for line in allp[k].split("\n"):
            if c in line and line.lstrip().startswith("#"):
                print("CODE-IN-HEADING", c, k); bad += 1
# truth
for q in qs:
    if q["page"] is None:
        continue
    pages = q["page"] if isinstance(q["page"], list) else [q["page"]]
    text = " ".join(allp.get(p) or allp.get("pages/" + p) or "" for p in pages)
    if not text:
        from importlib import import_module
    for g in q["truth"]:
        if not any(a.lower() in text.lower() for a in g):
            if q["page"] and q["page"].__class__ is str and q["page"].startswith("handbook"):
                continue
            print("TRUTH-MISSING", q["id"], g, pages); bad += 1
print("problems:", bad, "| pages checked", len(new), "| codes", len(codes), "| questions", len(qs))
