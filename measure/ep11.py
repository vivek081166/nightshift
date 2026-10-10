"""EP11 measurement harness, not episode code: turn PDFs and scans into pages the model can look up.

    python3 measure/ep11.py plocal              # P1-P5: pypdf, pypdf layout, pdftotext -layout, pdftotext, OCR (free)
    python3 measure/ep11.py p6                  # P6: the model writes each PDF as markdown, 3 runs per PDF
    python3 measure/ep11.py score               # P: pages parsed correctly per method (measure/ep11_score.py)
    python3 measure/ep11.py l VARIANT           # L: the 20 questions through lookup.py's loop: P1 | P2 | P3 | P5 | P6
    python3 measure/ep11.py l0                  # L0: each question with the ONE PDF that answers it, look.py style
    python3 measure/ep11.py c                   # C: countTokens per PDF as bytes vs as each method's text
    python3 measure/ep11.py f stale|convert|fresh
Model and call style as lookup.py / look.py: raw HTTP, gemini-3.8-flash, thinking low, PRICE_IN/PRICE_OUT from
lookup.py. Run files keep each request with long bodies replaced by md5 + token count, the full response with every
usageMetadata field, every tool call and result, and wall time. The key is read from .env and never written anywhere.
"""
import base64, contextlib, glob, hashlib, io, json, os, re, subprocess, sys, threading, time, urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)                                     # lookup.py reads library/INDEX.json relative to the repo
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "measure"))

if not os.environ.get("GEMINI_API_KEY"):           # never printed, never logged
    for line in open(os.path.join(ROOT, ".env")):
        if line.startswith("GEMINI_API_KEY="):
            os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")

import lookup, look                                # noqa: E402  (unchanged; only lookup.call is wrapped to record)
from ep11_score import score_doc, invented, norm   # noqa: E402

DAY = "2026-10-08"
RUNS = os.path.join(ROOT, "runs", "ep11")
PARSED = os.path.join(RUNS, "parsed")
PDFDIR = os.path.join(ROOT, "library", "pdf")
MODEL, BASE = lookup.MODEL, lookup.API
PRICE_IN, PRICE_OUT = lookup.PRICE_IN, lookup.PRICE_OUT
CAP = 5.70                                         # stop before the $6 cap
SPENT_FILE = os.path.join(RUNS, f"{DAY}-spend.json")
REPORT = os.path.expanduser("~/Projects/vivek-ai/content/ai-engineering-course/qc/ep11/measure/report.json")
SCORER_MD5 = hashlib.md5(open(os.path.join(ROOT, "measure", "ep11_score.py"), "rb").read()).hexdigest()
QUESTIONS = json.load(open(os.path.join(ROOT, "tickets", "questions-ep11.json")))["questions"]
LIB_PDFS = ["postmortem-notifier-reminder-backlog", "postmortem-api-index-migration",
            "postmortem-payments-duplicate-refunds", "postmortem-web-firewall-challenge",
            "provider-cloudflare-japan-edge", "scan-dr-drill-2023", "scan-twilio-maintenance-2025",
            "scan-escalation-sheet"]
P_ONLY = {"ep08-payments-timeout": os.path.join(ROOT, "postmortems", "payments-timeout.pdf")}
P6_PROMPT = ("Write this whole document out as Markdown, word for word, in reading order. Every table becomes a "
             "Markdown table with the same rows and columns. Do not summarise, do not leave anything out, and do not "
             "add anything that is not in the document.")
_lock = threading.Lock()


class Stop(Exception):
    pass


def pdf_path(slug):
    return P_ONLY.get(slug) or os.path.join(PDFDIR, slug + ".pdf")


def md5(s):
    return hashlib.md5(s.encode() if isinstance(s, str) else s).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def spent():
    try:
        return json.load(open(SPENT_FILE))["usd"]
    except FileNotFoundError:
        return 0.0


def add_spend(usd, step):
    with _lock:
        try:
            d = json.load(open(SPENT_FILE))
        except FileNotFoundError:
            d = {"usd": 0.0, "by_step": {}, "calls": 0}
        d["usd"] += usd
        d["calls"] = d.get("calls", 0) + 1
        d["by_step"][step] = d["by_step"].get(step, 0.0) + usd
        d["updated_utc"] = now()
        json.dump(d, open(SPENT_FILE, "w"), indent=1)
        return d["usd"]


def cost(u):
    out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    return (u.get("promptTokenCount", 0) * PRICE_IN + out * PRICE_OUT) / 1e6


def report_set(path, value):
    with _lock:
        try:
            r = json.load(open(REPORT))
        except FileNotFoundError:
            r = {}
        node = r
        for k in path[:-1]:
            node = node.setdefault(k, {})
        node[path[-1]] = value
        r["spend_usd_so_far"] = round(spent(), 6)
        r["spend_file"] = os.path.relpath(SPENT_FILE, ROOT)
        r["nightshift_runs"] = "~/Projects/nightshift/runs/ep11/"
        json.dump(r, open(REPORT, "w"), indent=1, ensure_ascii=False)


def http(method, path, body=None, timeout=300):
    req = urllib.request.Request(f"{BASE}/{path}", json.dumps(body).encode() if body is not None else None,
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "content-type": "application/json"},
                                 method=method)
    t0 = time.time()
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode()
        status, err, r = 200, None, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        status, err, r = e.code, e.read().decode(errors="replace"), None
    except Exception as e:
        status, err, r = 0, f"{type(e).__name__}: {e}", None
    if status == 402:
        raise Stop(f"HTTP 402 (prepay empty): {err[:300]}")
    return status, r, err, round(time.time() - t0, 3)


BODIES = {}


def register(text, n_tokens, name):
    if len(text) > 400 and text not in BODIES:
        BODIES[text] = f"<omitted {name}: md5 {md5(text)}, {n_tokens} tokens by countTokens>"


def redact(obj):
    s = json.dumps(obj, ensure_ascii=False)
    for text, label in sorted(BODIES.items(), key=lambda kv: -len(kv[0])):
        s = s.replace(json.dumps(text, ensure_ascii=False)[1:-1], label)
    s = re.sub(r'"data": "([A-Za-z0-9+/=]{400,})"', lambda m: '"data": "<omitted file bytes: base64 md5 '
               + md5(m.group(1)) + '>"', s)
    return json.loads(s)


def generate(body, step):
    """one generateContent call; retries 429/5xx/network; the record keeps the full response"""
    retries = []
    while True:
        stamp = now()
        status, r, err, secs = http("POST", f"models/{MODEL}:generateContent", body)
        if status in (0, 429, 500, 503, 504) and len(retries) < 4:
            retries.append({"why": f"HTTP {status}", "at": stamp, "body": (err or "")[:500]})
            time.sleep(20 if status == 429 else 5)
            continue
        break
    rec = {"request": redact(body), "http": status, "sent_utc": stamp, "wall_s": secs, "retries": retries,
           "error": err, "response": r}
    if r is not None:
        u = r.get("usageMetadata", {})
        cand = (r.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts", [])
        rec["text"] = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        rec["function_calls"] = [p["functionCall"] for p in parts if "functionCall" in p]
        rec["finishReason"] = cand.get("finishReason")
        rec["cost_usd"] = cost(u)
        if add_spend(rec["cost_usd"], step) > CAP:
            raise Stop(f"spend over the {CAP} working cap")
    return rec


def count_tokens(parts):
    status, r, err, _ = http("POST", f"models/{MODEL}:countTokens", {"contents": [{"role": "user", "parts": parts}]})
    if status != 200:
        raise Stop(f"countTokens HTTP {status}: {(err or '')[:300]}")
    return r


def save(name, obj):
    path = os.path.join(RUNS, f"{DAY}-{name}.json")
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return os.path.relpath(path, ROOT)


def pdf_part(slug):
    return {"inline_data": {"mime_type": "application/pdf",
                            "data": base64.b64encode(open(pdf_path(slug), "rb").read()).decode()}}


# ---------------------------------------------------------------- P1-P5 (local)

def ocr_pages(path, workdir):
    os.makedirs(workdir, exist_ok=True)
    subprocess.run(["pdftoppm", "-r", "300", "-png", path, os.path.join(workdir, "pg")], check=True)
    out = []
    for png in sorted(glob.glob(os.path.join(workdir, "pg-*.png"))):
        out.append(subprocess.run(["tesseract", png, "stdout"], capture_output=True, text=True).stdout)
    return out


def method_pages(method, slug):
    path = pdf_path(slug)
    if method in ("P1", "P2"):
        from pypdf import PdfReader
        reader = PdfReader(path)
        if method == "P1":
            return [p.extract_text() for p in reader.pages]
        return [p.extract_text(extraction_mode="layout") for p in reader.pages]
    if method in ("P3", "P4"):
        args = ["pdftotext"] + (["-layout"] if method == "P3" else []) + [path, "-"]
        txt = subprocess.run(args, capture_output=True, text=True).stdout
        pages = txt.split("\f")
        return pages[:-1] if pages and pages[-1].strip() == "" else pages
    if method == "P5":
        return ocr_pages(path, os.path.join(PARSED, "P5-png", slug))
    raise ValueError(method)


def cmd_plocal():
    rec = {"scorer_md5": SCORER_MD5, "methods": {
        "P1": "pypdf 6.14.2 page.extract_text()", "P2": "pypdf 6.14.2 page.extract_text(extraction_mode=\"layout\")",
        "P3": "pdftotext -layout (poppler)", "P4": "pdftotext (poppler, no -layout)",
        "P5": "pdftoppm -r 300 -png, then tesseract <png> stdout (eng, default page segmentation)"}, "runs": {}}
    for method in ("P1", "P2", "P3", "P4", "P5"):
        os.makedirs(os.path.join(PARSED, method), exist_ok=True)
        for slug in LIB_PDFS + list(P_ONLY):
            t0 = time.time()
            pages = method_pages(method, slug)
            secs = round(time.time() - t0, 3)
            open(os.path.join(PARSED, method, slug + ".txt"), "w").write("\f".join(pages))
            rec["runs"].setdefault(method, {})[slug] = {"wall_s": secs, "pages_out": len(pages),
                                                        "chars_per_page": [len(p.strip()) for p in pages],
                                                        "file": f"runs/ep11/parsed/{method}/{slug}.txt"}
            print(method, slug, secs, [len(p.strip()) for p in pages])
    print(save("p-local", rec))


# ---------------------------------------------------------------- P6 (the model writes the page)

def cmd_p6():
    jobs = [(slug, run) for run in (1, 2, 3) for slug in LIB_PDFS + list(P_ONLY)]
    for slug, run in jobs:
        name = f"p6-{slug}-run{run}"
        if os.path.exists(os.path.join(RUNS, f"{DAY}-{name}.json")):
            continue
        body = {"contents": [{"role": "user", "parts": [pdf_part(slug), {"text": P6_PROMPT}]}],
                "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}
        rec = generate(body, "P6")
        rec.update({"slug": slug, "run": run, "pdf": os.path.relpath(pdf_path(slug), ROOT),
                    "pdf_md5": md5(open(pdf_path(slug), "rb").read())})
        os.makedirs(os.path.join(PARSED, f"P6-run{run}"), exist_ok=True)
        open(os.path.join(PARSED, f"P6-run{run}", slug + ".txt"), "w").write(rec.get("text", ""))
        save(name, rec)
        print(name, rec["http"], rec.get("finishReason"), rec["wall_s"], f"${rec.get('cost_usd', 0):.4f}",
              f"spent ${spent():.4f}")


# ---------------------------------------------------------------- P scoring

def truth_of(slug):
    return json.load(open(os.path.join(PDFDIR, slug + ".truth.json")))


def cmd_score():
    out = {"scorer": "measure/ep11_score.py", "scorer_md5": SCORER_MD5, "per_method": {}, "detail": {}}
    methods = ["P1", "P2", "P3", "P4", "P5", "P6-run1", "P6-run2", "P6-run3"]
    for m in methods:
        tot = {"text": [0, 0, 0], "scan": [0, 0, 0], "ep08": [0, 0, 0]}   # correct, correct_loose, pages
        rows = {"text": [0, 0, 0], "scan": [0, 0, 0], "ep08": [0, 0, 0]}  # strict intact, loose intact, rows
        for slug in LIB_PDFS + list(P_ONLY):
            f = os.path.join(PARSED, m, slug + ".txt")
            if not os.path.exists(f):
                continue
            raw = open(f).read()
            t = truth_of(slug)
            res = score_doc(t, [raw], whole_doc=True) if m.startswith("P6") else score_doc(t, raw.split("\f"))
            grp = "ep08" if slug in P_ONLY else "scan" if slug.startswith("scan-") else "text"
            for p in res:
                tot[grp][0] += p["correct"]
                tot[grp][1] += p["correct_loose"]
                tot[grp][2] += 1
                rows[grp][0] += p["rows_intact"]
                rows[grp][1] += p["rows_intact_loose"]
                rows[grp][2] += p["rows"]
            entry = {"pages": res, "chars_total": len(raw.strip())}
            if m in ("P5",) or m.startswith("P6"):
                entry["invented"] = invented(raw, t["source_text"])
            out["detail"].setdefault(m, {})[slug] = entry
        out["per_method"][m] = {
            g: {"pages_correct": tot[g][0], "pages_correct_loose": tot[g][1], "pages": tot[g][2],
                "rows_intact": rows[g][0], "rows_intact_loose": rows[g][1], "rows": rows[g][2]} for g in tot}
        print(m, json.dumps(out["per_method"][m]))
    print(save("p-scores", out))


# ---------------------------------------------------------------- L: look it up

def variant_pages(variant):
    """the 67 existing pages + one page per library PDF, text = that method's output"""
    pages = lookup.pages()
    src = "P6-run1" if variant == "P6" else variant
    for slug in LIB_PDFS:
        raw = open(os.path.join(PARSED, src, slug + ".txt")).read()
        text = "\n\n".join(p.strip("\n") for p in raw.split("\f")) if src != "P6-run1" else raw
        pages.append({"id": slug, "title": truth_of(slug)["title"], "updated": None,
                      "source": os.path.relpath(pdf_path(slug), ROOT), "text": text})
    return pages


def register_pages(pages, variant):
    tokens_file = os.path.join(RUNS, f"{DAY}-page-tokens.json")
    cache = json.load(open(tokens_file)) if os.path.exists(tokens_file) else {}
    by_id = {r["id"]: r for r in lookup.INDEX}
    for p in pages:
        if p["id"] in by_id:
            register(p["text"], by_id[p["id"]]["tokens"], f"page {p['id']}")
        else:
            key = md5(p["text"])
            if key not in cache:
                cache[key] = count_tokens([{"text": p["text"]}])["totalTokens"] if p["text"].strip() else 0
            register(p["text"], cache[key], f"page {p['id']} ({variant})")
    json.dump(cache, open(tokens_file, "w"), indent=1)


def run_lookup(question, pages, step):
    """lookup.look_it_up, unchanged; lookup.call is swapped for one that sends the same body and records it"""
    calls = []

    def recording_call(body):
        body["generationConfig"] = {"thinkingConfig": {"thinkingLevel": "low"}}      # exactly as lookup.call
        rec = generate(body, step)
        calls.append(rec)
        if rec["http"] != 200:
            raise Stop(f"HTTP {rec['http']}: {(rec['error'] or '')[:300]}")
        lookup.used.append(rec["response"]["usageMetadata"])
        return rec["response"]["candidates"][0]["content"]

    lookup.call = recording_call
    buf = io.StringIO()
    t0 = time.time()
    with contextlib.redirect_stdout(buf):
        answer = lookup.look_it_up(question, pages)
    opened = [l.split()[1] for l in buf.getvalue().splitlines() if l.startswith("opened")]
    return {"answer": answer, "opened": opened, "calls": calls, "wall_s": round(time.time() - t0, 3),
            "prompt_tokens": sum(c["response"]["usageMetadata"].get("promptTokenCount", 0) for c in calls),
            "out_tokens": sum(c["response"]["usageMetadata"].get("candidatesTokenCount", 0)
                              + c["response"]["usageMetadata"].get("thoughtsTokenCount", 0) for c in calls),
            "cost_usd": sum(c["cost_usd"] for c in calls)}


def grade(q, answer):
    a = answer.lower()
    right = all(any(alt.lower() in a for alt in grp) for grp in q["truth"]) if q["truth"] else None
    wrong_hits = [w for w in q["wrong"] if w.lower() in a]
    says_not = bool(re.search(r"(do(es)? not|don't|doesn't|no) (say|mention|contain|include|state|list|have|record|"
                              r"specify|provide)|not (in|found in|listed in|mentioned in) the pages|no information|"
                              r"not available|could not find|couldn't find|cannot find|can't find|no record", a))
    return {"code_right": right, "wrong_terms": wrong_hits, "says_not_in_pages": says_not}


def cmd_l(variant):
    pages = variant_pages(variant)
    register_pages(pages, variant)
    out = {"variant": variant, "pages": len(pages), "contents_list_md5": md5(lookup.contents_list(pages)),
           "new_pages": {p["id"]: {"title": p["title"], "text_md5": md5(p["text"]), "chars": len(p["text"])}
                         for p in pages[-len(LIB_PDFS):]}, "questions": []}
    name = f"l-{variant}"
    for q in QUESTIONS:
        r = run_lookup(q["question"], pages, f"L-{variant}")
        r.update({"id": q["id"], "kind": q["kind"], "question": q["question"], "page": q["page"],
                  "opened_right_page": q["page"] in r["opened"] if q["page"] else None, **grade(q, r["answer"])})
        out["questions"].append(r)
        save(name, out)
        print(variant, q["id"], "opened", r["opened"], "right" if r["code_right"] else r["code_right"],
              r["wrong_terms"], "| " + r["answer"].replace("\n", " ")[:150], f"spent ${spent():.3f}")
    print(save(name, out))


def cmd_l0():
    out = {"how": "look.look(path, question): the one PDF that answers it, as bytes + type label, no look-up; "
                  "look.py appends its SHORT line", "questions": []}
    for q in QUESTIONS:
        if not q["page"] or q["page"] not in LIB_PDFS:
            continue
        retries, t0 = [], time.time()
        while True:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    r = look.look(pdf_path(q["page"]), q["question"])
                status, err = 200, None
            except urllib.error.HTTPError as e:
                r, status, err = None, e.code, e.read().decode(errors="replace")
                if status == 402:
                    raise Stop("HTTP 402 (prepay empty)")
                if status in (429, 500, 503, 504) and len(retries) < 4:
                    retries.append(status)
                    time.sleep(20 if status == 429 else 5)
                    continue
            break
        rec = {"id": q["id"], "kind": q["kind"], "question": q["question"], "pdf": os.path.relpath(pdf_path(q["page"]),
               ROOT), "http": status, "error": err, "retries": retries, "wall_s": round(time.time() - t0, 3),
               "response": r}
        if r:
            rec["answer"] = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"]
                                    if not p.get("thought"))
            rec["cost_usd"] = cost(r["usageMetadata"])
            add_spend(rec["cost_usd"], "L0")
            rec.update(grade(q, rec["answer"]))
        out["questions"].append(rec)
        save("l0-pdf-bytes", out)
        print("L0", q["id"], rec.get("code_right"), rec.get("wrong_terms"), "|", rec.get("answer", err)[:120],
              f"spent ${spent():.3f}")
    if spent() > CAP:
        raise Stop("cap")


# ---------------------------------------------------------------- C: sizes

def cmd_c():
    out = {"how": "countTokens (free) on the PDF as inline bytes, and on each method's text", "per_pdf": {}}
    for slug in LIB_PDFS + list(P_ONLY):
        r = count_tokens([pdf_part(slug)])
        row = {"pdf_bytes_tokens": r.get("totalTokens"), "pdf_bytes_detail": r, "pdf_size_bytes":
               os.path.getsize(pdf_path(slug))}
        for m in ("P1", "P2", "P3", "P4", "P5", "P6-run1"):
            txt = open(os.path.join(PARSED, m, slug + ".txt")).read()
            row[m] = count_tokens([{"text": txt}])["totalTokens"] if txt.strip() else 0
        out["per_pdf"][slug] = row
        print(slug, {k: v for k, v in row.items() if k != "pdf_bytes_detail"})
    print(save("c-tokens", out))


# ---------------------------------------------------------------- F: freshness

F_SLUG = "postmortem-web-firewall-challenge"
F_QS = [{"id": "f-challenges-normal", "question": "In the firewall challenge postmortem, at what time did challenges "
         "on /book/* fall back to normal?", "rev1": "17:01", "rev2": "17:03"},
        {"id": "f-alert-action", "question": "In the firewall challenge postmortem, is the action item to alert when "
         "booking starts from new visitors fall more than 40 % below the same hour last week done, or still open?",
         "rev1": "open", "rev2": "done"}]
F_DROP = os.path.join(RUNS, "f-drop")       # the folder the team's PDFs land in (copies)
F_PAGES = os.path.join(RUNS, "f-pages")     # the converted pages, one per PDF


def convert_file(path, method):
    """turn one PDF into page text with the chosen method"""
    if method == "P6":
        body = {"contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": "application/pdf", "data":
                base64.b64encode(open(path, "rb").read()).decode()}}, {"text": P6_PROMPT}]}],
                "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}
        rec = generate(body, "F-convert")
        return rec.get("text", ""), rec
    from pypdf import PdfReader
    if method == "P1":
        return "\n\n".join(p.extract_text() for p in PdfReader(path).pages), None
    if method == "P2":
        return "\n\n".join(p.extract_text(extraction_mode="layout") for p in PdfReader(path).pages), None
    if method == "P3":
        txt = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
        return "\n\n".join(p.strip("\n") for p in txt.split("\f") if p.strip()), None
    raise ValueError(method)


def converter(method, date):
    """re-convert a PDF only when its md5 differs from the source line at the top of its page"""
    os.makedirs(F_PAGES, exist_ok=True)
    log = []
    for pdf in sorted(glob.glob(os.path.join(F_DROP, "*.pdf"))):
        name = os.path.basename(pdf)
        digest = md5(open(pdf, "rb").read())
        page = os.path.join(F_PAGES, name[:-4] + ".md")
        if os.path.exists(page):
            first = open(page).readline()
            m = re.search(r"md5 ([0-9a-f]{8})", first)
            if m and m.group(1) == digest[:8]:
                log.append({"file": name, "md5": digest[:8], "action": "kept"})
                continue
        text, rec = convert_file(pdf, method)
        open(page, "w").write(f"Source: {name} · md5 {digest[:8]} · converted {date}\n\n{text}")
        log.append({"file": name, "md5": digest[:8], "action": "converted",
                    "call": {k: rec[k] for k in ("http", "wall_s", "cost_usd") if k in rec} if rec else None})
    return log


def f_ask(pages, stage):
    out = []
    for q in F_QS:
        for run in (1, 2, 3):
            r = run_lookup(q["question"], pages, f"F-{stage}")
            a = r["answer"].lower()
            r.update({"id": q["id"], "run": run, "question": q["question"], "has_rev1": q["rev1"] in a,
                      "has_rev2": q["rev2"] in a})
            out.append(r)
            print(stage, q["id"], run, "opened", r["opened"], "rev1" if r["has_rev1"] else "", "rev2" if r["has_rev2"]
                  else "", "|", r["answer"].replace("\n", " ")[:140])
    return out


def cmd_f(stage, method):
    import shutil
    if stage == "stale":
        # the variant keeps the page converted from revision 1; the PDF on the drive is now revision 2
        pages = variant_pages(method)
        register_pages(pages, method)
        res = f_ask(pages, "stale")
        print(save("f-stale", {"method": method, "page_kept_from": "revision 1", "pdf_now": "revision 2 (md5 "
                               + md5(open(os.path.join(PDFDIR, F_SLUG + ".rev2.pdf"), "rb").read()) + ")",
                               "asks": res}))
    elif stage == "convert":
        os.makedirs(F_DROP, exist_ok=True)
        for slug in LIB_PDFS:
            shutil.copyfile(pdf_path(slug), os.path.join(F_DROP, slug + ".pdf"))           # revision 1 everywhere
        first = converter(method, DAY)
        shutil.copyfile(os.path.join(PDFDIR, F_SLUG + ".rev2.pdf"), os.path.join(F_DROP, F_SLUG + ".pdf"))  # rev 2 lands
        second = converter(method, DAY)
        print(save("f-convert", {"method": method, "first_run": first, "after_rev2_lands": second,
                                 "converted_on_rerun": sum(1 for x in second if x["action"] == "converted")}))
    elif stage == "fresh":
        pages = lookup.pages()
        for slug in LIB_PDFS:
            text = open(os.path.join(F_PAGES, slug + ".md")).read()
            pages.append({"id": slug, "title": truth_of(slug)["title"], "updated": None,
                          "source": f"runs/ep11/f-drop/{slug}.pdf", "text": text})
        register_pages(pages, method + "-fresh")
        res = f_ask(pages, "fresh")
        print(save("f-fresh", {"method": method, "asks": res}))


if __name__ == "__main__":
    try:
        cmd = sys.argv[1]
        if cmd == "plocal":
            cmd_plocal()
        elif cmd == "p6":
            cmd_p6()
        elif cmd == "score":
            cmd_score()
        elif cmd == "l":
            cmd_l(sys.argv[2])
        elif cmd == "l0":
            cmd_l0()
        elif cmd == "c":
            cmd_c()
        elif cmd == "f":
            cmd_f(sys.argv[2], sys.argv[3])
    except Stop as e:
        print("STOP:", e)
        sys.exit(3)
