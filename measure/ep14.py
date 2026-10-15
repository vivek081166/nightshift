"""EP14 measurement harness, not episode code: answers that are not on any page.

    .venv/bin/python measure/ep14.py freeze   # md5 of the questions, the table and the code; no model call
    .venv/bin/python measure/ep14.py tokens   # countTokens for the table and the schema prompt (not billed)
    .venv/bin/python measure/ep14.py p        # P: ask the pages, lookup.search_it exactly + the TODAY line
    .venv/bin/python measure/ep14.py l        # L: the whole deploys.csv in the call, 3 runs per question
    .venv/bin/python measure/ep14.py s        # S: deploys.ask writes one SELECT, deploys.run runs it
    .venv/bin/python measure/ep14.py n        # N: one named function, count_deploys (only if S misses 2+ on definition)
Call style as lookup.py: raw HTTP with urllib, gemini-3.8-flash, thinking low, rules.SYSTEM, lookup.ASK.
Run files keep each request with every page text and the table replaced by md5 + token count, the full response incl.
usageMetadata, and wall time. Spend is tracked in runs/ep14/spend.json as calls return. No re-rolls: an item already
billed in a run file is never asked again.
"""
import concurrent.futures as cf, contextlib, hashlib, io, json, os, sys, threading, time, urllib.error, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

RUNS = os.path.join(ROOT, "runs", "ep14")
DAY = "2026-10-14"
MODEL = "gemini-3.8-flash"
BASE = "https://generativelanguage.googleapis.com/v1beta"
CAP = 3.00
SPENT_FILE = os.path.join(RUNS, "spend.json")
REPORT = os.path.expanduser("~/Projects/vivek-ai/content/ai-engineering-course/qc/ep14/measure/report.json")
QFILE = "tickets/questions-ep14.json"
FREEZE = os.path.join(RUNS, f"{DAY}-q-freeze.json")
TOKENS = os.path.join(RUNS, f"{DAY}-tokens.json")
EP12_FREEZE = "runs/ep12/2026-10-11-a-freeze.json"     # per-page countTokens; page texts checked by md5
FROZEN_FILES = [QFILE, "deploys/deploys.csv", "deploys/deploys.db", "deploys/CANON.json", "deploys/make_deploys.py",
                "measure/ep14_questions.py", "deploys.py", "lookup.py", "search.py", "rules.py", "check.py",
                "library/INDEX.json", "runbooks/handbook.md"]

if not os.environ.get("GEMINI_API_KEY"):
    for line in open(os.path.join(ROOT, ".env")):
        if line.startswith("GEMINI_API_KEY="):
            os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")

_lock = threading.Lock()
_spend_lock = threading.Lock()
_local = threading.local()


class Stop(Exception):
    pass


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()


def md5f(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def spent():
    with _spend_lock:
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
                 "note": "every billed call, added from its usageMetadata as it returned (cached tokens priced as "
                         "uncached: an upper bound)"}
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
        r["spend_file"] = "nightshift/runs/ep14/spend.json"
        os.makedirs(os.path.dirname(REPORT), exist_ok=True)
        json.dump(r, open(REPORT, "w"), indent=1, ensure_ascii=False)


import lookup                                             # noqa: E402  (after chdir: lookup reads library/INDEX.json)
PRICE_IN, PRICE_OUT = lookup.PRICE_IN, lookup.PRICE_OUT


def cost(u):
    return (u.get("promptTokenCount", 0) * PRICE_IN
            + (u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)) * PRICE_OUT) / 1e6


BODIES = {}


def register(text, n_tokens, name):
    BODIES[text] = f"<omitted {name}: md5 {md5(text)}, {n_tokens} tokens by countTokens>"


def redact(obj):
    s = json.dumps(obj, ensure_ascii=False)
    for text, label in sorted(BODIES.items(), key=lambda kv: -len(kv[0])):
        s = s.replace(json.dumps(text, ensure_ascii=False)[1:-1], label)
    return json.loads(s)


def http(body, method="generateContent"):
    req = urllib.request.Request(f"{BASE}/models/{MODEL}:{method}", json.dumps(body).encode(),
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


def recording_call(step, floor=0.05):
    """stands in for lookup.call / deploys.call: the body as the camera code built it, thinking low, recorded.
    Only transport failures (0/429/5xx, no billed answer) are retried; an answer is never asked for twice."""
    def call(body):
        body.setdefault("generationConfig", {})["thinkingConfig"] = {"thinkingLevel": "low"}
        if spent() > CAP - floor:
            raise Stop(f"spend {spent():.4f} within {floor} of the {CAP} cap")
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
            rec["cost_usd"] = cost(r.get("usageMetadata", {}))
            add_spend(rec["cost_usd"], step)
        _local.calls.append(rec)
        if st != 200 or not r or not r.get("candidates") or not r["candidates"][0].get("content"):
            raise Stop(f"generateContent HTTP {st}: {(err or '')[:300]}")
        return r["candidates"][0]["content"]
    return call


def load():
    fz = json.load(open(FREEZE))
    for f, h in fz["md5"].items():
        if md5f(f) != h:
            raise Stop(f"{f} changed since the freeze")
    pages = lookup.pages()
    tok = {x["id"]: x["tokens"] for x in json.load(open(EP12_FREEZE))["pages"]}
    for p in pages:
        assert md5(p["text"]) == fz["pages_md5"][p["id"]], p["id"]
        register(p["text"], tok[p["id"]], "page " + p["id"])
    if os.path.exists(TOKENS):
        t = json.load(open(TOKENS))
        register(open("deploys/deploys.csv").read(), t["csv_tokens"], "deploys.csv")
    return pages, json.load(open(QFILE))["questions"]


def run(name, step, one, items, workers=4):
    path = os.path.join(RUNS, f"{DAY}-{name}.json")
    out = {"what": name, "started_utc": stamp(), "items": []}
    done = {}
    if os.path.exists(path):
        prev = json.load(open(path))
        out["started_utc"] = prev["started_utc"]
        done = {r["item"]: r for r in prev["items"] if any("cost_usd" in c for c in r.get("calls", []))}
    todo = [it for it in items if it["item"] not in done]
    out["items"] = [done[it["item"]] for it in items if it["item"] in done]   # a rerun keeps what was billed
    stop = None

    def wrap(it):
        _local.calls = []
        w0 = time.time()
        try:
            result, err = one(it), None
        except Stop as e:
            if "402" in str(e) or "cap" in str(e):
                raise
            result, err = {}, str(e)
        except (json.JSONDecodeError, KeyError, TypeError) as e:          # an answer that does not parse is a result
            result, err = {}, f"{type(e).__name__}: {e}"
        u = [c["response"].get("usageMetadata", {}) for c in _local.calls if c.get("response")]
        return {"item": it["item"], "id": it["id"], "kind": it["kind"], "question": it["question"],
                **result, "error": err, "wall_s": round(time.time() - w0, 2), "calls": _local.calls,
                "prompt_tokens": sum(x.get("promptTokenCount", 0) for x in u),
                "cached_tokens": sum(x.get("cachedContentTokenCount", 0) for x in u),
                "out_tokens": sum(x.get("candidatesTokenCount", 0) + x.get("thoughtsTokenCount", 0) for x in u),
                "cost_usd": sum(c.get("cost_usd", 0) for c in _local.calls)}

    with cf.ThreadPoolExecutor(workers) as ex:
        futures = [ex.submit(wrap, it) for it in todo]
        for fu in futures:
            try:
                rec = fu.result()
            except Stop as e:
                stop = stop or e
                continue
            with _lock:
                done[rec["item"]] = rec
                out["items"] = [done[it["item"]] for it in items if it["item"] in done]
                json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
            print(f"  {rec['item']:8} {rec['prompt_tokens']:>7,} in {rec['out_tokens']:>5,} out "
                  f"${rec['cost_usd']:.4f} {rec['wall_s']} s {rec['error'] or ''}", flush=True)
    out["finished_utc"] = stamp()
    json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
    print("->", os.path.relpath(path, ROOT), f"spent ${spent():.4f}")
    if stop:
        raise stop
    return out


def items(qs, runs=1):
    return [{**q, "item": q["id"] + (f"-r{k}" if runs > 1 else "")} for k in range(1, runs + 1) for q in qs]


TODAY = json.load(open(QFILE))["today_line"] if os.path.exists(QFILE) else None


# ---------------------------------------------------------------- freeze (no model call)

def freeze():
    if os.path.exists(FREEZE):
        raise Stop("already frozen: " + FREEZE)
    pages = lookup.pages()
    fz = {"frozen_utc": stamp(), "note": "frozen before the first EP14 model call; questions-ep14.json and "
                                          "deploys.csv are not edited after this",
          "md5": {f: md5f(f) for f in FROZEN_FILES}, "n_pages": len(pages),
          "pages_md5": {p["id"]: md5(p["text"]) for p in pages}}
    os.makedirs(RUNS, exist_ok=True)
    json.dump(fz, open(FREEZE, "w"), indent=1)
    print("frozen:", {k: v for k, v in fz["md5"].items() if k in (QFILE, "deploys/deploys.csv")})


def tokens():
    """countTokens: what the table and the schema prompt weigh. Not billed; recorded, not added to spend."""
    import deploys
    csv_text = open("deploys/deploys.csv").read()
    rec = {"utc": stamp(), "method": "countTokens (not billed)"}
    for name, text in (("csv", csv_text), ("schema", deploys.table())):
        st, r, err, secs = http({"contents": [{"role": "user", "parts": [{"text": text}]}]}, "countTokens")
        if st != 200:
            raise Stop(f"countTokens HTTP {st}: {(err or '')[:200]}")
        rec[f"{name}_tokens"] = r["totalTokens"]
        rec[f"{name}_md5"] = md5(text)
        rec[f"{name}_chars"] = len(text)
        rec[f"{name}_response"] = r
    json.dump(rec, open(TOKENS, "w"), indent=1)
    print({k: v for k, v in rec.items() if k.endswith(("tokens", "chars"))})


# ---------------------------------------------------------------- P: lookup.search_it exactly, + the TODAY line

def pages_arm():
    import search
    pages, qs = load()
    lookup.call = recording_call("P-pages")
    lookup.SYSTEM = lookup.SYSTEM + "\n" + TODAY            # search_it builds its system text from lookup.SYSTEM
    lookup.print = lambda *a, **k: None                    # search_it prints the five page ids; threads: no redirect

    def one(q):
        answer = lookup.search_it(q["question"], pages)
        ids = [p["id"] for p in search.keyword_search(q["question"], pages, 5)]
        return {"answer": answer, "pages_in_call": ids,
                "holding_page_in_call": [h for h in q["holding_page_ids"] if h in ids]}

    out = run("p-pages", "P-pages", one, items(qs))
    out["meta"] = {"code": "lookup.search_it exactly (keyword top 5 in systemInstruction with rules.SYSTEM, lookup.ASK); "
                           "lookup.SYSTEM given the TODAY line on its own line; lookup.call swapped for a recording "
                           "call with the same body and thinking low", "today_line": TODAY}
    json.dump(out, open(os.path.join(RUNS, f"{DAY}-p-pages.json"), "w"), indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- L: paste the whole table

L_HEAD = "\nThe team's pages follow: one page, the deploy tool's history of every deploy, as CSV.\n\n"


def table_arm():
    pages, qs = load()
    if not os.path.exists(TOKENS):
        raise Stop("run tokens first: the run file needs the table's token count")
    csv_text = open("deploys/deploys.csv").read()
    call = recording_call("L-table", floor=0.30)                        # keep $0.30 for S and N
    system = lookup.SYSTEM + "\n" + TODAY + L_HEAD + csv_text

    def one(q):
        reply = call({"systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": lookup.ASK.format(q=q["question"])}]}]})
        return {"answer": "".join(p.get("text", "") for p in reply["parts"] if not p.get("thought"))}

    out = run("l-table", "L-table", one, items(qs, 3))
    out["meta"] = {"system": "rules.SYSTEM + TODAY line + " + json.dumps(L_HEAD) + " + deploys.csv (whole)",
                   "ask": lookup.ASK, "today_line": TODAY, "csv_md5": md5(csv_text),
                   "csv_tokens": json.load(open(TOKENS))["csv_tokens"], "runs_per_question": 3,
                   "order": "all 20 questions once, then again, then a third time"}
    json.dump(out, open(os.path.join(RUNS, f"{DAY}-l-table.json"), "w"), indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- S: the model writes one SELECT, deploys.py runs it

def sql_arm():
    import deploys
    load()
    deploys.call_original = deploys.call
    rec_call = recording_call("S-sql")

    def call(body):
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
        return rec_call(body)
    deploys.call = call
    deploys.print = lambda *a, sep=" ", end="\n": _local.screen.append(sep.join(str(x) for x in a) + end)
    qs = json.load(open(QFILE))["questions"]

    def one(q):
        sql = deploys.ask(q["question"])
        rec = {"sql": sql, "refused": deploys.refuse(sql)}
        if not rec["refused"]:
            try:
                rec["result"] = [list(r) for r in deploys.run(sql)]
            except Exception as e:                                       # a query that does not run is a result
                rec["run_error"] = f"{type(e).__name__}: {e}"
        _local.screen = []
        if rec.get("result") is not None:
            deploys.show(sql, rec["result"])
        rec["screen"] = "".join(_local.screen)
        return rec

    out = run("s-sql", "S-sql", one, items(qs))
    out["meta"] = {"code": "deploys.ask + deploys.refuse + deploys.run exactly (deploys.call swapped for a recording "
                           "call, same body, thinking low)", "deploys_py_md5": md5f("deploys.py"),
                   "schema_shown": deploys.table(), "response_schema": deploys.SHAPE, "today_line": TODAY}
    json.dump(out, open(os.path.join(RUNS, f"{DAY}-s-sql.json"), "w"), indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- S2: the same call, plus the table's own words

S_COPY = "runs/ep14/2026-10-14-deploys-as-measured-in-S.py"


def words_arm():
    """deploys.ask(q, words=True): S's call, with a comment per column and the values of the short columns.
    deploys.py changed after the freeze by design (the helper); every other frozen file must match, the copy of
    deploys.py as S ran it must match the freeze, and words=False must rebuild S's recorded system text exactly."""
    import deploys
    fz = json.load(open(FREEZE))
    for f, h in fz["md5"].items():
        if f != "deploys.py" and md5f(f) != h:
            raise Stop(f"{f} changed since the freeze")
    if md5f(S_COPY) != fz["md5"]["deploys.py"]:
        raise Stop("the copy of deploys.py as S ran it does not match the freeze")
    s_text = json.load(open(os.path.join(RUNS, f"{DAY}-s-sql.json")))["items"][0]["calls"][0]["request"][
        "systemInstruction"]["parts"][0]["text"]
    plain = (lookup.SYSTEM + "\n" + deploys.TODAY + "\nThe deploy history is one SQLite table:\n\n" + deploys.table() +
             "\n\nWrite one SQLite SELECT that answers the question.")
    if plain != s_text:
        raise Stop("words=False no longer rebuilds S's system text")
    rec_call = recording_call("S2-words")

    def call(body):
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
        return rec_call(body)
    deploys.call = call
    deploys.print = lambda *a, sep=" ", end="\n": _local.screen.append(sep.join(str(x) for x in a) + end)
    qs = json.load(open(QFILE))["questions"]

    def one(q):
        sql = deploys.ask(q["question"], words=True)
        rec = {"sql": sql, "refused": deploys.refuse(sql)}
        if not rec["refused"]:
            try:
                rec["result"] = [list(r) for r in deploys.run(sql)]
            except Exception as e:
                rec["run_error"] = f"{type(e).__name__}: {e}"
        _local.screen = []
        if rec.get("result") is not None:
            deploys.show(sql, rec["result"])
        rec["screen"] = "".join(_local.screen)
        return rec

    out = run("s2-words", "S2-words", one, items(qs))
    out["meta"] = {"code": "deploys.ask(q, words=True) + deploys.refuse + deploys.run (deploys.call swapped for a "
                           "recording call, same body, thinking low)", "deploys_py_md5_now": md5f("deploys.py"),
                   "deploys_py_md5_in_S": fz["md5"]["deploys.py"], "plain_rebuilds_S_system_text": True,
                   "table_shown": deploys.table_with_words(), "today_line": TODAY}
    json.dump(out, open(os.path.join(RUNS, f"{DAY}-s2-words.json"), "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    cmd = sys.argv[1]
    try:
        {"freeze": freeze, "tokens": tokens, "p": pages_arm, "l": table_arm, "s": sql_arm, "s2": words_arm}[cmd]()
    except Stop as e:
        print("STOP:", e)
        sys.exit(2)
