"""EP11's screens from the saved runs (calls no model), the stage for the cold open, and the gate.

    python3 measure/ep11_screen.py pages       pages/ as my code made them before the check: the text taken out of
                                               every PDF in pdf/, no Source line (the scan's page is 0 bytes)
    python3 measure/ep11_screen.py cold        the cold question, looked up, as lookup.py prints it (a saved run)
    python3 measure/ep11_screen.py questions   my questions, looked up: text taken out vs count first, one row each
    python3 measure/ep11_screen.py tally write | stale | fresh    the saved runs behind a take, one row
    python3 measure/ep11_screen.py gate        topage.py and lookup.py against the measured runs (run `pages` first)

Every number comes from runs/ep11/2026-10-08-*.json. The two not-in-pages rows are graded by hand (both answers say
the pages do not say: HAND below), never by the code's keyword grades. "no words added": the scorer flags words and
numbers missing from the HTML the PDF was printed from; a flag counts as added only if the PDF's own text lacks it
(the Cloudflare byline is printed in capitals, the EP08 list numbers its items).
"""
import base64, hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import lookup, topage                               # noqa: E402  (lookup reads library/INDEX.json from ROOT)

RUNS = os.path.join(ROOT, "runs", "ep11")
COLD = "scan-esc-api-ext"
FRESH = "f-challenges-normal"
HAND = {"none-drill-2024": "says the pages do not say what the 2024 restore time was",
        "none-sendgrid-ext": "says no extension for a SendGrid account manager is given (4429 is Tom's, named as his)"}
WORDS = {3: "three"}


def load(name):
    return json.load(open(os.path.join(RUNS, f"2026-10-08-{name}.json")))


def md5(s):
    return hashlib.md5(s.encode() if isinstance(s, str) else s).hexdigest()


def pages():
    topage.PAGES.mkdir(exist_ok=True)
    for pdf in sorted(Path("pdf").glob("*.pdf")):
        (topage.PAGES / (pdf.stem + ".md")).write_text(topage.text_out(pdf))
        print(f"{os.path.getsize(topage.PAGES / (pdf.stem + '.md')):>6}  pages/{pdf.stem}.md")


def cold():
    item = next(q for q in load("l-P1")["questions"] if q["id"] == COLD)
    print("a saved run\n")
    for page_id in item["opened"]:
        print("opened ", page_id)
    lookup.show(item["answer"])


def verdict(q):
    if q["kind"] == "not-in-pages":
        assert q["id"] in HAND, q["id"]
        return "right · not in the pages"
    if q["code_right"] and not q["wrong_terms"]:
        return "right"
    if q["says_not_in_pages"]:
        return "the pages don't have it"
    return "wrong"


def questions():
    left, right = load("l-P1")["questions"], load("l-mix")["questions"]
    print("my questions · looking it up · saved runs\n")
    print(f"{'':38} {'text taken out':25} count first")
    for a, b in zip(left, right):
        assert a["id"] == b["id"]
        head = ""
        for word in a["question"].split():
            if len(head) + len(word) > 32:
                head += " ..."
                break
            head = (head + " " + word).strip()
        print(f"{head:38} {verdict(a):25} {verdict(b)}")


def in_pdf(slug, flag):
    pdf = "postmortems/payments-timeout.pdf" if slug == "ep08-payments-timeout" else f"library/pdf/{slug}.pdf"
    return re.search(rf"(?<![\w.,]){re.escape(flag)}(?![\w,]|\.\d)", topage.text_out(pdf)) is not None


def tally(which):
    if which == "write":
        scores = load("p-scores")
        runs = [f"P6-run{n}" for n in (1, 2, 3)]
        right = all(g["pages_correct"] == g["pages"] for r in runs for g in scores["per_method"][r].values())
        added = [(r, slug, flag) for r in runs for slug, d in scores["detail"][r].items()
                 for flag in d["invented"]["numbers"] + d["invented"]["words"] if not in_pdf(slug, flag)]
        print(f"saved runs · each PDF written out {WORDS[len(runs)]} times: "
              f"{'every PDF right' if right else 'NOT every PDF right'} · {'no words added' if not added else f'ADDED {added}'}")
        return
    asks = [a for a in load(f"f-{which}")["asks"] if a["id"] == FRESH]
    key, label = ("has_rev1", "the old page: old time") if which == "stale" else ("has_rev2", "made again: new time")
    print(f"saved runs · pages the model wrote · {label} {sum(a[key] for a in asks)} of {len(asks)}")


def lookup_drift(old, new):
    """top-level nodes of lookup.py that differ from tag ep10, beyond fitting the output to the screen (show, cost_line,
    SCREEN and the shutil import that reads it). Bytes on disk, never git diff: lookup.py is assume-unchanged during takes."""
    import ast
    FIT = {"show", "cost_line", "SCREEN"}

    def nodes(src):
        out = []
        for n in ast.parse(src).body:
            name = getattr(n, "name", None) or (n.targets[0].id if isinstance(n, ast.Assign) and
                                                isinstance(n.targets[0], ast.Name) else None)
            if name in FIT:
                continue
            if isinstance(n, ast.Import):
                n = ast.Import(names=[a for a in n.names if a.name != "shutil"])
            out.append((name, ast.dump(n)))
        return out

    a, b = nodes(old), nodes(new)
    return [f"{i}:{x[0] or y[0]}" for i, (x, y) in enumerate(zip(a, b)) if x != y] + (["node count"] if len(a) != len(b) else [])


def gate():
    """the pages topage.py makes and the list lookup.py sends must be the measured ones, byte for byte"""
    fails, checks = [], 0

    def check(ok, what):
        nonlocal checks
        checks += 1
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    l1, mix = load("l-P1"), load("l-mix")
    slugs = list(l1["new_pages"])
    pdfs = {p.stem: p for p in Path("pdf").glob("*.pdf")}
    check(sorted(pdfs) == sorted(slugs), f"pdf/ holds the {len(slugs)} measured PDFs ({len(pdfs)} found)")
    same = [s for s in slugs if s in pdfs and md5(pdfs[s].read_bytes()) == md5(Path(f"library/pdf/{s}.pdf").read_bytes())]
    check(len(same) == len(slugs), f"pdf/ bytes == library/pdf (rev 1) {len(same)}/{len(slugs)}")
    check(topage.tag(pdfs["postmortem-web-firewall-challenge"]) == "aec8edf7", "firewall postmortem tag aec8edf7 (rev 1)")

    texts = {s: topage.text_out(pdfs[s]) for s in slugs if s in pdfs}
    bad = [s for s in slugs if md5(texts.get(s, "")) != l1["new_pages"][s]["text_md5"]]
    check(not bad, f"topage text_out md5 == l-P1 new_pages {len(slugs) - len(bad)}/{len(slugs)}" + (f" BAD {bad}" if bad else ""))
    counts = {s: len(t.strip()) for s, t in texts.items()}
    print("     counts", counts)
    bad = [s for s in slugs if counts.get(s) != l1["new_pages"][s]["chars"]]
    check(not bad, f"--count == l-P1 new_pages chars {len(slugs) - len(bad)}/{len(slugs)}" + (f" BAD {bad}" if bad else ""))
    route = {s: ("P6-run1" if counts[s] == 0 else "P1") for s in counts}
    bad = [s for s in slugs if route.get(s) != mix["routes"][s]["route"]]
    check(not bad, f"count-first route == l-mix routes {len(slugs) - len(bad)}/{len(slugs)} "
                   f"(to the model: {sorted(s for s in route if route[s] != 'P1')})")

    on_disk = {s: (topage.PAGES / f"{s}.md") for s in slugs}
    bad = [s for s in slugs if not on_disk[s].exists() or on_disk[s].read_text() != texts.get(s)]
    check(not bad, f"pages/ == the text taken out, no Source line {len(slugs) - len(bad)}/{len(slugs)} (run `pages`)")
    check(on_disk["scan-escalation-sheet"].exists() and os.path.getsize(on_disk["scan-escalation-sheet"]) == 0,
          "pages/scan-escalation-sheet.md is 0 bytes (take W prints 0)")
    listed = lookup.pages()
    check(len(listed) == l1["pages"] == 75, f"lookup.pages() {len(listed)} == l-P1 {l1['pages']} == 75")
    check(md5(lookup.contents_list(listed)) == l1["contents_list_md5"], "lookup.py --list md5 == l-P1 contents_list_md5")
    item = next(q for q in l1["questions"] if q["id"] == COLD)
    sent = item["calls"][0]["request"]
    head = ("\nThe team's pages are listed below, one per line as id: title. To read a page, call read_page with "
            "its id. You may read up to 4 pages.\n\n")
    check(sent["systemInstruction"]["parts"][0]["text"] == lookup.SYSTEM + head + lookup.contents_list(listed),
          "take A: systemInstruction byte-match with l-P1 scan-esc-api-ext")
    check(sent["contents"][0]["parts"][0]["text"] == lookup.ASK.format(q=item["question"]), "take A: the ask == measured")
    at_ep10 = lambda f: subprocess.run(["git", "show", f"ep10:{f}"], capture_output=True, check=True).stdout
    check(at_ep10("rules.py") == Path("rules.py").read_bytes(), "rules.py unchanged since tag ep10 (bytes)")
    drift = lookup_drift(at_ep10("lookup.py").decode(), Path("lookup.py").read_text())
    check(not drift, "lookup.py == tag ep10 outside show(), cost_line(), SCREEN, import shutil (AST)"
                     + (f" DRIFT {drift}" if drift else ""))

    p6 = load("p6-scan-escalation-sheet-run1")["request"]
    parts = p6["contents"][0]["parts"]
    check(parts[1]["text"] == topage.WRITE, "topage WRITE == the measured P6 instruction")
    check(parts[0]["inline_data"]["mime_type"] == "application/pdf" and
          md5(base64.b64encode(pdfs["scan-escalation-sheet"].read_bytes()).decode()) in parts[0]["inline_data"]["data"],
          "take M: the PDF part == the measured P6 bytes (base64 md5)")

    print(f"\n{checks} checks, {len(fails)} failed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"pages": pages, "cold": cold, "questions": questions, "gate": gate}.get(cmd, lambda: tally(sys.argv[2]))()
