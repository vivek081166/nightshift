"""EP13 measurement harness, not episode code: does the page really say that?

    python3 measure/ep13.py p       # P: the 30 new questions, lookup.search_it's call exactly (keyword top 5)
    python3 measure/ep13.py c1      # C1: all 70, the same pages (each with its id), claims + page id, structured output
    python3 measure/ep13.py c2      # C2: all 70, check.py's call exactly: claims + page id + quote
Call style as lookup.py: raw HTTP with urllib, gemini-3.8-flash, thinking low, rules.SYSTEM, lookup.ASK.
Run files keep each request with every page text replaced by md5 + token count, the full response incl.
usageMetadata, and wall time. Spend is tracked in runs/ep13/spend.json as calls return. No re-rolls: a question
already in a run file is never asked again.
"""
import concurrent.futures as cf, contextlib, hashlib, io, json, os, sys, threading, time, urllib.error, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

RUNS = os.path.join(ROOT, "runs", "ep13")
DAY = "2026-10-12"
MODEL = "gemini-3.8-flash"
BASE = "https://generativelanguage.googleapis.com/v1beta"
CAP = 3.00
SPENT_FILE = os.path.join(RUNS, "spend.json")
REPORT = os.path.expanduser("~/Projects/vivek-ai/content/ai-engineering-course/qc/ep13/measure/report.json")
QFILE = "tickets/questions-ep13.json"
FREEZE = os.path.join(RUNS, f"{DAY}-q-freeze.json")
EP12_FREEZE = "runs/ep12/2026-10-11-a-freeze.json"     # per-page countTokens; the page texts are the same (md5 checked)

if not os.environ.get("GEMINI_API_KEY"):
    for line in open(os.path.join(ROOT, ".env")):
        if line.startswith("GEMINI_API_KEY="):
            os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")

_lock = threading.Lock()
_spend_lock = threading.Lock()     # spend.json is read while another thread writes it: one lock for both
_local = threading.local()


class Stop(Exception):
    pass


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def spent():
    with _spend_lock:
        return _spent()


def _spent():
    try:
        return json.load(open(SPENT_FILE))["usd"]
    except FileNotFoundError:
        return 0.0


def add_spend(usd, step):
    with _spend_lock:
        try:
            d = json.load(open(SPENT_FILE))
        except FileNotFoundError:
            d = {"usd": 0.0, "cap_usd": CAP, "by_step": {}, "calls": 0,
                 "note": "every billed call, added from its usageMetadata as it returned"}
        d["usd"] += usd
        d["calls"] += 1
        d["by_step"][step] = d["by_step"].get(step, 0.0) + usd
        d["updated_utc"] = stamp()
        json.dump(d, open(SPENT_FILE, "w"), indent=1)
        return d["usd"]


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
        r["spend_file"] = "nightshift/runs/ep13/spend.json"
        json.dump(r, open(REPORT, "w"), indent=1, ensure_ascii=False)


PRICE_IN, PRICE_OUT = 0.75, 3.75          # lookup.py's PRICE_IN / PRICE_OUT, dollars per million; thinking billed as out


def cost(u):
    return (u.get("promptTokenCount", 0) * PRICE_IN
            + (u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)) * PRICE_OUT) / 1e6


BODIES = {}


def register(text, n_tokens, name):
    BODIES[text] = f"<omitted page {name}: md5 {md5(text)}, {n_tokens} tokens by countTokens>"


def redact(obj):
    s = json.dumps(obj, ensure_ascii=False)
    for text, label in sorted(BODIES.items(), key=lambda kv: -len(kv[0])):
        s = s.replace(json.dumps(text, ensure_ascii=False)[1:-1], label)
    return json.loads(s)


def http(body):
    req = urllib.request.Request(f"{BASE}/models/{MODEL}:generateContent", json.dumps(body).encode(),
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "content-type": "application/json"})
    t0 = time.time()
    try:
        raw = urllib.request.urlopen(req, timeout=300).read().decode()
        st, err, r = 200, None, json.loads(raw)
    except urllib.error.HTTPError as e:
        st, err, r = e.code, e.read().decode(errors="replace"), None
    except Exception as e:
        st, err, r = 0, f"{type(e).__name__}: {e}", None
    if st == 402:
        raise Stop(f"HTTP 402: {err[:300]}")
    return st, r, err, round(time.time() - t0, 3)


def recording_call(step):
    """stands in for lookup.call / check.call: the body as the camera code built it, thinking low, recorded.
    Only transport failures (0/429/5xx, no billed answer) are retried; an answer is never asked for twice."""
    def call(body):
        body.setdefault("generationConfig", {})["thinkingConfig"] = {"thinkingLevel": "low"}
        if spent() > CAP - 0.05:
            raise Stop(f"spend {spent():.4f} at the {CAP} cap")
        retries = []
        while True:
            t0 = stamp()
            st, r, err, secs = http(body)
            if st in (0, 429, 500, 503, 504) and len(retries) < 4:
                retries.append({"why": f"HTTP {st}", "at": t0, "body": (err or "")[:300]})
                time.sleep(20 if st == 429 else 5)
                continue
            break
        rec = {"request": redact(body), "http": st, "sent_utc": t0, "wall_s": secs, "retries": retries,
               "error": err, "response": r}
        if r is not None:
            u = r.get("usageMetadata", {})
            rec["cost_usd"] = cost(u)
            add_spend(rec["cost_usd"], step)
        _local.calls.append(rec)
        if st != 200 or not r or not r.get("candidates") or not r["candidates"][0].get("content"):
            raise Stop(f"generateContent HTTP {st}: {(err or '')[:300]}")
        return r["candidates"][0]["content"]
    return call


def load():
    fz = json.load(open(FREEZE))
    for f, h in fz["md5"].items():
        if hashlib.md5(open(f, "rb").read()).hexdigest() != h:
            raise Stop(f"{f} changed since the freeze")
    import lookup
    pages = lookup.pages()
    tok = {x["id"]: x["tokens"] for x in json.load(open(EP12_FREEZE))["pages"]}
    for p in pages:
        assert md5(p["text"]) == fz["pages_md5"][p["id"]], p["id"]
        register(p["text"], tok[p["id"]], p["id"])
    return pages, json.load(open(QFILE))["questions"]


def run(name, step, one, qs, workers=4):
    path = os.path.join(RUNS, f"{DAY}-{name}.json")
    out = {"what": name, "started_utc": stamp(), "questions": []}
    done = {}
    if os.path.exists(path):
        prev = json.load(open(path))
        out["started_utc"] = prev["started_utc"]
        done = {r["id"]: r for r in prev["questions"]
                if any("cost_usd" in c for c in r.get("calls", []))}         # billed once: never asked again
    todo = [q for q in qs if q["id"] not in done]
    if os.environ.get("ONLY"):                                               # a pilot: these ids first, kept as results
        todo = [q for q in todo if q["id"] in os.environ["ONLY"].split(",")]

    def wrap(q):
        _local.calls = []
        w0 = time.time()
        try:
            result, err = one(q), None
        except Stop as e:
            if "402" in str(e) or "cap" in str(e):
                raise
            result, err = {}, str(e)
        except (json.JSONDecodeError, KeyError, TypeError) as e:          # an answer that does not parse is a result
            result, err = {}, f"{type(e).__name__}: {e}"
        u = [c["response"].get("usageMetadata", {}) for c in _local.calls if c.get("response")]
        return {"id": q["id"], "kind": q["kind"], "question": q["question"], "answer_page": q["page"],
                **result, "error": err, "wall_s": round(time.time() - w0, 2), "calls": _local.calls,
                "prompt_tokens": sum(x.get("promptTokenCount", 0) for x in u),
                "out_tokens": sum(x.get("candidatesTokenCount", 0) + x.get("thoughtsTokenCount", 0) for x in u),
                "cost_usd": sum(c.get("cost_usd", 0) for c in _local.calls)}

    with cf.ThreadPoolExecutor(workers) as ex:
        for rec in ex.map(wrap, todo):
            with _lock:
                done[rec["id"]] = rec
                out["questions"] = [done[q["id"]] for q in qs if q["id"] in done]
                json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
            print(f"  {rec['id']:26} {rec['prompt_tokens']:>7,} in {rec['out_tokens']:>5,} out ${rec['cost_usd']:.4f} "
                  f"{rec['wall_s']} s {rec['error'] or ''}", flush=True)
    out["finished_utc"] = stamp()
    json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
    print("->", os.path.relpath(path, ROOT), f"spent ${spent():.4f}")
    return out


def in_call(q, ids):
    pages = q["page"] if isinstance(q["page"], list) else ([q["page"]] if q["page"] else [])
    return {"answer_page_in_call": any(p in ids for p in pages) if pages else None,
            "other_answer_pages_in_call": [p for p in q.get("other_pages", []) if p in ids]}


# ---------------------------------------------------------------- P: lookup.search_it exactly, the 30 new questions

def plain():
    import lookup, search
    pages, qs = load()
    lookup.call = recording_call("P-plain")

    def one(q):
        with contextlib.redirect_stdout(io.StringIO()):                   # search_it prints the five page ids
            answer = lookup.search_it(q["question"], pages)
        ids = [p["id"] for p in search.keyword_search(q["question"], pages, 5)]
        return {"answer": answer, "pages_in_call": ids, **in_call(q, ids)}

    out = run("p-plain", "P-plain", one, [q for q in qs if q["kind"] in ("steps", "half")])
    out["meta"] = {"code": "lookup.search_it exactly (keyword top 5 in systemInstruction with rules.SYSTEM, lookup.ASK); "
                           "lookup.call swapped for a recording call with the same body and thinking low",
                   "ep12_40": "not re-run: P for the 40 EP12 questions is runs/ep12/2026-10-11-e1-code.json + its hand "
                              "grades (same model, same pages, same prompt)"}
    json.dump(out, open(os.path.join(RUNS, f"{DAY}-p-plain.json"), "w"), indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- C1: tell me which page

C1_ASK = None
C1_SHAPE = {"type": "object", "properties": {
    "claims": {"type": "array", "items": {"type": "object", "properties": {
        "claim": {"type": "string"}, "page": {"type": "string"}}, "required": ["claim", "page"]}},
    "not_in_pages": {"type": "array", "items": {"type": "string"}}}, "required": ["claims", "not_in_pages"]}


def pages_tell():
    import lookup, search
    from rules import SYSTEM
    global C1_ASK
    C1_ASK = lookup.ASK + ("\nAnswer only from the pages. Give each claim and the id of the page it came from. Put any "
                           "part of the question the pages do not answer under not_in_pages.")
    pages, qs = load()
    call = recording_call("C1-pages")

    def one(q):
        top = search.keyword_search(q["question"], pages, 5)
        system = SYSTEM + "\nThe team's pages that matched the question follow, each with its id.\n" + "".join(
            f"\n----- page {p['id']}: {p['title']} -----\n\n{p['text']}" for p in top)      # check.py's header
        reply = call({"systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": C1_ASK.format(q=q["question"])}]}],
                      "generationConfig": {"responseMimeType": "application/json", "responseSchema": C1_SHAPE}})
        text = "".join(part.get("text", "") for part in reply["parts"] if not part.get("thought"))
        ids = [p["id"] for p in top]
        rec = {"pages_in_call": ids, **in_call(q, ids), "raw_text": text}
        rec["answer"] = json.loads(text)
        rec["page_id_check"] = [c["page"] in ids for c in rec["answer"]["claims"]]
        return rec

    out = run("c1-pages", "C1-pages", one, qs)
    out["meta"] = {"ask": C1_ASK, "schema": C1_SHAPE, "header": "----- page <id>: <title> ----- (check.py's)",
                   "code_check": "page_id_check = the cited id is one of the five sent"}
    json.dump(out, open(os.path.join(RUNS, f"{DAY}-c1-pages.json"), "w"), indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- C2: quote, then find (check.py exactly)

def quotes():
    import check, search
    pages, qs = load()
    check.call_original = check.call
    rec_call = recording_call("C2-quotes")

    def call(body):                                    # check.call's body, recorded; check.call adds thinking low too
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
        return rec_call(body)
    check.call = call

    def one(q):
        ids = [p["id"] for p in search.keyword_search(q["question"], pages, 5)]
        rec = {"pages_in_call": ids, **in_call(q, ids)}
        answer, sent = check.ask(q["question"], pages)
        rec["answer"] = answer
        rec["found_camera"] = [bool(sent.get(c["page"])) and check.found(c["quote"], sent[c["page"]]["text"])
                               for c in answer["claims"]]
        return rec

    out = run("c2-quotes", "C2-quotes", one, qs)
    out["meta"] = {"code": "check.ask exactly (check.call swapped for a recording call, same body, thinking low)",
                   "check_py_md5": hashlib.md5(open("check.py", "rb").read()).hexdigest(),
                   "ask": check.ASK, "schema": check.SHAPE}
    json.dump(out, open(os.path.join(RUNS, f"{DAY}-c2-quotes.json"), "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    cmd = sys.argv[1]
    try:
        {"p": plain, "c1": pages_tell, "c2": quotes}[cmd]()
    except Stop as e:
        print("STOP:", e)
        sys.exit(2)
