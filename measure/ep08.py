"""EP08 measurement harness, not episode code: images and PDFs sent to Gemini, every answer scored.

    python3 measure/ep08.py truth                 # graph truths from arch/latency.csv -> arch/latency.truth.json
    python3 measure/ep08.py graph A|B|csv RUN     # M1
    python3 measure/ep08.py res LOW|MEDIUM|HIGH RUN   # M2, panel A with generationConfig.mediaResolution
    python3 measure/ep08.py small RUN             # M2, panel A at 800 px, default resolution
    python3 measure/ep08.py count                 # M2, countTokens on the image alone + per-part resolution probe
    python3 measure/ep08.py pdf pdf|text RUN      # M3
Call style as triage.py: raw HTTP, gemini-3.8-flash, thinking low. Saves requests without the base64 body (md5 kept).
"""
import base64, threading, concurrent.futures as cf, csv, hashlib, json, os, re, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "runs", "ep08")
DAY = "2026-10-03"
MODEL = "gemini-3.8-flash"
PRICE_IN, PRICE_OUT = 0.75, 3.75   # triage.py
CAP = 2.80                          # stop before the $3 cap
SPENT_FILE = os.path.join(RUNS, f"{DAY}-spend.json")

if not os.environ.get("GEMINI_API_KEY"):          # the key lives in .env (gitignored); never printed
    for line in open(os.path.join(ROOT, ".env")):
        if line.startswith("GEMINI_API_KEY="):
            os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip()

FMT = ("Reply with only the answer: a time as HH:MM, a latency in ms, a rate in req/s, a number of minutes, "
       "or one word. No explanation.")
PDF_FMT = "Reply with only the answer, as short as possible. No explanation."

QUESTIONS = {
    "Q1": ("At what time did the payments p95 latency first go above 2 seconds?", "time", 2),
    "Q2": ("What was the highest payments p95 latency of the night, in milliseconds?", "ms", 0.10),
    "Q3": ("At what time did the payments p95 latency reach its highest point?", "time", 2),
    "Q4": ("At what time was payments v2.31 deployed?", "time", 2),
    "Q5": ("Did the payments p95 latency first go above 1 second before or after the deploy?", "word", None),
    "Q6": ("At what time did the rollback start?", "time", 2),
    "Q7": ("After the peak, at what time did the payments p95 latency drop back under 500 ms and stay there?", "time", 2),
    "Q8": ("At the moment payments p95 latency peaked, what was the api p95 latency, in milliseconds?", "ms", 0.10),
    "Q9": ("What was the payments p95 latency at 01:30, in milliseconds?", "ms", 0.10),
    "Q10": ("For how many minutes in total was the payments p95 latency above 2 seconds?", "minutes", 3),
    "R1": ("What was the payments request rate at the moment payments p95 latency peaked, in requests per second?", "rps", 0.10),
    "R2": ("What was the payments request rate at 01:30, in requests per second?", "rps", 0.10),
}
CORE = [f"Q{i}" for i in range(1, 11)]
PDF_QS = {
    "P1": "At what time were payments restored?",
    "P2": "Who rolled back payments?",
    "P3": "How many minutes passed from the first alert to the start of the rollback?",
    "P4": "In the timeline, what is the entry right after the incident was declared? Give its time and who.",
    "P5": "Who acknowledged the page, and at what time?",
    "P6": "What happened at 03:20, and who did it?",
    "P7": "How many payments failed?",
    "P8": "Which version was payments rolled back to?",
    "P9": "How many timeline entries list Mei under Who?",
    "P10": "Who is listed for the 02:56 entry in the timeline?",
}
NAMES = ["Mei", "Ravi", "Aiko", "Tom", "Hana", "PagerDuty"]


# ---------- truth ----------
def mins(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def graph_truth():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "arch", "latency.csv"))))
    pay = [int(r["payments_p95_ms"]) for r in rows]
    t = [r["time"] for r in rows]
    ev = {r["event"]: r["time"] for r in rows if r["event"]}
    peak = max(range(len(pay)), key=lambda i: pay[i])
    deploy = ev["deploy payments v2.31"]
    over1 = next(i for i, p in enumerate(pay) if p > 1000)
    rec = next(i for i in range(peak, len(pay)) if all(p < 500 for p in pay[i:]))
    i130 = t.index("01:30")
    return {
        "Q1": t[next(i for i, p in enumerate(pay) if p > 2000)],
        "Q2": pay[peak], "Q3": t[peak], "Q4": deploy,
        "Q5": "after" if mins(t[over1]) > mins(deploy) else "before",
        "Q6": ev["rollback payments v2.30"], "Q7": t[rec],
        "Q8": int(rows[peak]["api_p95_ms"]), "Q9": pay[i130],
        "Q10": sum(1 for p in pay if p > 2000),
        "R1": float(rows[peak]["payments_rps"]), "R2": float(rows[i130]["payments_rps"]),
    }


# ---------- scoring ----------
def first_time(s):
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", s)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def first_number(s, kind):
    s2 = re.sub(r"\b\d{1,2}:\d{2}\b", " ", s)
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(milliseconds|ms|seconds|secs?|s)?\b", s2, re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    if kind == "ms" and unit in ("s", "sec", "secs", "seconds"):
        v *= 1000
    return v


def score_graph(qid, text, truth):
    _, kind, tol = QUESTIONS[qid]
    want = truth[qid]
    if kind == "time":
        got = first_time(text)
        ok = got is not None and abs(mins(got) - mins(want)) <= tol
    elif kind == "word":
        low = text.lower()
        got = "after" if "after" in low and "before" not in low else "before" if "before" in low and "after" not in low else None
        ok = got == want
    elif kind == "minutes":
        got = first_number(text, kind)
        ok = got is not None and abs(got - want) <= tol
    else:
        got = first_number(text, kind)
        ok = got is not None and abs(got - want) <= tol * want
    return {"parsed": got, "truth": want, "ok": ok}


def score_pdf(qid, text, truth):
    a = truth[qid]["answer"]
    low = text.lower()
    named = [n for n in NAMES if re.search(rf"\b{n.lower()}\b", low)]
    if qid in ("P2", "P10"):
        ok, got = named == [a], named
    elif qid == "P1":
        got = first_time(text); ok = got == a
    elif qid in ("P3", "P7", "P9"):
        m = re.search(r"\d[\d,]*", text); got = int(m.group().replace(",", "")) if m else None; ok = got == a
    elif qid == "P4":
        got = {"time": first_time(text), "named": named}; ok = got["time"] == a["time"] and named == [a["who"]]
    elif qid == "P5":
        got = {"time": first_time(text), "named": named}; ok = got["time"] == a["time"] and named == [a["who"]]
    elif qid == "P6":
        got = named; ok = named == [a["who"]] and ("receipt" in low or "email" in low)
    elif qid == "P8":
        got = re.findall(r"v?\d+\.\d+", text); ok = bool(got) and got[0].lstrip("v") == "2.30"
    return {"parsed": got, "truth": a, "ok": ok}


# ---------- the call ----------
def spent():
    try:
        return json.load(open(SPENT_FILE))["usd"]
    except (OSError, ValueError):
        return 0.0


LOCK = threading.Lock()


def add_spend(usd):
  with LOCK:
    total = spent() + usd
    json.dump({"usd": total, "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}, open(SPENT_FILE, "w"))
  return total


class Stop(Exception):
    pass


def call(parts, config=None, api="v1beta", method="generateContent", model=MODEL):
    """parts: list of {'text':...} or {'inline_data': {'mime_type','data_path'}}. Returns (record, response)."""
    sent_parts, logged_parts = [], []
    for p in parts:
        if "file" in p:
            raw = open(p["file"], "rb").read()
            q = {"inline_data": {"mime_type": p["mime"], "data": base64.b64encode(raw).decode()}}
            if "part_extra" in p:
                q.update(p["part_extra"])
            sent_parts.append(q)
            lq = {"inline_data": {"mime_type": p["mime"], "data": f"<base64 omitted: {os.path.relpath(p['file'], ROOT)}, "
                                  f"{len(raw)} bytes, md5 {hashlib.md5(raw).hexdigest()}>"}}
            if "part_extra" in p:
                lq.update(p["part_extra"])
            logged_parts.append(lq)
        else:
            sent_parts.append(p); logged_parts.append(p)
    body = {"contents": [{"role": "user", "parts": sent_parts}]}
    if method == "generateContent":
        cfg = {"thinkingConfig": {"thinkingLevel": "low"}}
        cfg.update(config or {})
        body["generationConfig"] = cfg
    url = f"https://generativelanguage.googleapis.com/{api}/models/{model}:{method}"
    logged_body = json.loads(json.dumps({**body, "contents": [{"role": "user", "parts": logged_parts}]}))
    retries = []
    while True:
        req = urllib.request.Request(url, json.dumps(body).encode(),
                                     {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "content-type": "application/json"})
        stamp, t0 = datetime.now(timezone.utc).isoformat(timespec="seconds"), time.time()
        try:
            r, status, err = json.load(urllib.request.urlopen(req, timeout=300)), 200, None
        except urllib.error.HTTPError as e:
            r, status, err = None, e.code, e.read().decode(errors="replace")
            if status == 402:
                raise Stop(f"HTTP 402: {err}")
            if status in (429, 500, 503) and len(retries) < 4:
                retries.append({"why": f"HTTP {status}", "at": stamp, "body": err[:500]})
                time.sleep(30 if status == 429 else 5)
                continue
        break
    rec = {"model": model, "api": api, "method": method, "url_path": url.split(".com")[1], "request": logged_body,
           "http": status, "utc": stamp, "latency_s": round(time.time() - t0, 2), "retries": retries, "error": err}
    if r is not None:
        if method == "countTokens":
            rec["countTokens"] = r
        else:
            cand = (r.get("candidates") or [{}])[0]
            rec["finishReason"] = cand.get("finishReason")
            rec["usageMetadata"] = u = r.get("usageMetadata", {})
            rec["modelVersion"] = r.get("modelVersion")
            rec["text"] = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
            n_out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
            rec["cost_usd"] = (u.get("promptTokenCount", 0) * PRICE_IN + n_out * PRICE_OUT) / 1e6
            total = add_spend(rec["cost_usd"])
            if total > CAP:
                raise Stop(f"spend {total:.4f} over the {CAP} working cap")
    return rec


def run_batch(jobs, path):
    """jobs: list of (tag, qid, parts, config, scorer). Runs 4 at a time, saves as it goes."""
    out = []
    def one(job):
        tag, qid, parts, config, scorer = job
        rec = call(parts, config)
        rec["tag"], rec["qid"] = tag, qid
        if rec.get("text") is not None and rec["http"] == 200:
            rec["score"] = scorer(qid, rec["text"])
        return rec
    with cf.ThreadPoolExecutor(4) as ex:
        for rec in ex.map(one, jobs):
            out.append(rec)
            json.dump(out, open(path + ".tmp", "w"), indent=1, ensure_ascii=False)
    os.replace(path + ".tmp", path)
    ok = sum(1 for r in out if r.get("score", {}).get("ok"))
    cost = sum(r.get("cost_usd") or 0 for r in out)
    print(f"{os.path.basename(path)}: {ok}/{len(out)} right · ${cost:.4f} · total spent ${spent():.4f}")
    for r in out:
        s = r.get("score")
        if not s or not s["ok"]:
            print(f"  WRONG {r['qid']:4} got {r.get('text', r.get('error'))!r:60.200} truth {s and s['truth']}")
    return out


def img(path):
    return {"file": os.path.join(ROOT, path), "mime": "image/png"}


def graph_jobs(image, qids, truth, config=None):
    sc = lambda q, t: score_graph(q, t, truth)
    return [(image, q, [img(image), {"text": "This is a screenshot of our latency dashboard from last night. "
                                     f"{QUESTIONS[q][0]}\n{FMT}"}], config, sc) for q in qids]


if __name__ == "__main__":
    os.makedirs(RUNS, exist_ok=True)
    op = sys.argv[1]
    if op == "truth":
        t = graph_truth()
        json.dump({"source": "arch/latency.csv", "questions": {q: {"q": QUESTIONS[q][0], "kind": QUESTIONS[q][1],
                   "tol": QUESTIONS[q][2], "truth": t[q]} for q in QUESTIONS}}, open(os.path.join(ROOT, "arch", "latency.truth.json"), "w"), indent=1)
        print(json.dumps(t))
        sys.exit()
    truth = graph_truth()
    try:
        if op == "graph":
            which, run = sys.argv[2], sys.argv[3]
            if which == "csv":
                rows = open(os.path.join(ROOT, "arch", "latency.csv")).read()
                sc = lambda q, t: score_graph(q, t, truth)
                jobs = [("csv", q, [{"text": "These are the rows behind our latency dashboard from last night, as CSV:\n"
                                     f"{rows}\n{QUESTIONS[q][0]}\n{FMT}"}], None, sc) for q in QUESTIONS]
            else:
                image = "arch/latency.png" if which == "A" else "arch/latency-rate.png"
                jobs = graph_jobs(image, CORE if which == "A" else list(QUESTIONS), truth)
            run_batch(jobs, os.path.join(RUNS, f"{DAY}-graph-{which}-run{run}.json"))
        elif op == "res":
            level, run = sys.argv[2], sys.argv[3]
            jobs = graph_jobs("arch/latency.png", CORE, truth, {"mediaResolution": f"MEDIA_RESOLUTION_{level}"})
            run_batch(jobs, os.path.join(RUNS, f"{DAY}-graph-res-{level.lower()}-run{sys.argv[3]}.json"))
        elif op == "small":
            run_batch(graph_jobs("arch/latency-800.png", CORE, truth), os.path.join(RUNS, f"{DAY}-graph-800-run{sys.argv[2]}.json"))
        elif op == "count":
            recs = []
            for name in ("arch/latency.png", "arch/latency-rate.png", "arch/latency-800.png"):
                recs.append(call([img(name)], method="countTokens"))
            recs.append(call([{"file": os.path.join(ROOT, "postmortems/payments-timeout.pdf"), "mime": "application/pdf"}], method="countTokens"))
            recs.append(call([{"text": "x"}], method="countTokens"))
            ask = {"text": "This is a screenshot of our latency dashboard from last night. " + QUESTIONS["Q2"][0] + "\n" + FMT}
            for api in ("v1beta", "v1alpha"):
                for level in ("media_resolution_low", "media_resolution_medium", "media_resolution_high", "media_resolution_ultra_high"):
                    p = img("arch/latency.png"); p["part_extra"] = {"media_resolution": {"level": level}}
                    rec = call([p, ask], api=api); rec["tag"] = f"per-part {level} on {api}"
                    if rec.get("text"):
                        rec["score"] = score_graph("Q2", rec["text"], truth)
                    recs.append(rec)
            json.dump(recs, open(os.path.join(RUNS, f"{DAY}-graph-tokens.json"), "w"), indent=1, ensure_ascii=False)
            for r in recs:
                print(r.get("tag", r["request"]["contents"][0]["parts"][0].get("inline_data", {}).get("data", "text")[:60]),
                      r["http"], r.get("countTokens") or (r.get("usageMetadata") or {}).get("promptTokensDetails"), (r.get("error") or "")[:300])
        elif op == "pdf":
            which, run = sys.argv[2], sys.argv[3]
            pt = json.load(open(os.path.join(ROOT, "postmortems", "payments-timeout.truth.json")))["questions"]
            sc = lambda q, t: score_pdf(q, t, pt)
            if which == "pdf":
                doc = {"file": os.path.join(ROOT, "postmortems/payments-timeout.pdf"), "mime": "application/pdf"}
                jobs = [("pdf", q, [doc, {"text": f"This is the postmortem for last night's payments incident. {PDF_QS[q]}\n{PDF_FMT}"}], None, sc) for q in PDF_QS]
            else:
                text = open(os.path.join(RUNS, f"{DAY}-pdf-extracted.txt")).read()
                jobs = [("text", q, [{"text": f"This is the postmortem for last night's payments incident, as text:\n{text}\n{PDF_QS[q]}\n{PDF_FMT}"}], None, sc) for q in PDF_QS]
            run_batch(jobs, os.path.join(RUNS, f"{DAY}-pdf-{which}-run{run}.json"))
    except Stop as e:
        print("STOP:", e)
        sys.exit(2)
