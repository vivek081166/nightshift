"""EP10 measurement harness, not episode code: carry the documents, or look them up?

    python3 measure/ep10.py draft            # A: draft the 45 spec'd documents with Gemini (library building, not measured)
    python3 measure/ep10.py index            # A: split into pages, countTokens each, write library/INDEX.json + freeze md5s
    python3 measure/ep10.py models           # M0: models.get (free)
    python3 measure/ep10.py m1               # sizes and cost at 1, 5, 50
    python3 measure/ep10.py m4 SHAPE         # carry-5 | carry-50 | model-50 | code-50 | fix-dates | fix-archived | fix-notice
    python3 measure/ep10.py m2 SHAPE         # carry-50 | model-50 | code-50
    python3 measure/ep10.py m3 SHAPE         # carry-1 | model-1
Call style as triage.py: raw HTTP, gemini-3.8-flash, thinking low. Tool calls as tools.py; explicit cache as cache.py.
Run files keep each request with long document bodies replaced by md5 + token count, the full response with every
usageMetadata field, every tool call and tool result, and wall time.
"""
import concurrent.futures as cf, hashlib, json, os, re, statistics, sys, threading, time, urllib.error, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rules import SYSTEM, ACTIONS                 # noqa: E402
from sorrel.oncall import SERVICES, PROVIDERS     # noqa: E402

RUNS = os.path.join(ROOT, "runs", "ep10")
LIB = os.path.join(ROOT, "library")
DAY = "2026-10-07"
MODEL = "gemini-3.8-flash"
BASE = "https://generativelanguage.googleapis.com/v1beta"
PRICE_IN, PRICE_OUT = 0.75, 3.75     # triage.py, dollars per million; thinking billed as out
PRICE_CACHED = 0.075                 # pricing page (runs/ep09/2026-10-05-m0-docs-pricing.md), paid tier, through 2026-12-31
PRICE_STORAGE_H = 0.50               # same page: per 1M tokens per hour, through 2026-12-31
CAP = 7.60                           # stop before the $8 cap
SPENT_FILE = os.path.join(RUNS, f"{DAY}-spend.json")
HANDBOOK_FILE = os.path.join(ROOT, "runbooks", "handbook.md")
CASES = json.load(open(os.path.join(ROOT, "tickets", "incidents.json")))
REPORT = os.path.expanduser("~/Projects/vivek-ai/content/ai-engineering-course/qc/ep10/measure/report.json")
ASK = "Reply in JSON with the severity, the service, the first move, and why."
SCHEMA = {"type": "object", "properties": {
    "severity": {"type": "string", "enum": ["P1", "P2", "P3"]},
    "service": {"type": "string", "enum": SERVICES},
    "first_move": {"type": "string", "enum": ACTIONS},
    "reason": {"type": "string"}},
    "required": ["severity", "service", "first_move", "reason"]}

if not os.environ.get("GEMINI_API_KEY"):          # the key lives in .env (gitignored); never printed, never logged
    for line in open(os.path.join(ROOT, ".env")):
        if line.startswith("GEMINI_API_KEY="):
            os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")

_lock = threading.Lock()


class Stop(Exception):
    pass


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()


def spent():
    try:
        return json.load(open(SPENT_FILE))["usd"]
    except FileNotFoundError:
        return 0.0


def add_spend(usd, what=""):
    with _lock:
        try:
            d = json.load(open(SPENT_FILE))
        except FileNotFoundError:
            d = {"usd": 0.0, "by_step": {}}
        d["usd"] += usd
        d.setdefault("by_step", {})
        d["by_step"][what] = d["by_step"].get(what, 0.0) + usd
        d["updated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json.dump(d, open(SPENT_FILE, "w"), indent=1)
        return d["usd"]


STEP = ["?"]


def cost(u):
    """Uncached prompt at PRICE_IN, cached at PRICE_CACHED, output incl. thinking at PRICE_OUT."""
    p, c = u.get("promptTokenCount", 0), u.get("cachedContentTokenCount", 0)
    n_out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    return ((p - c) * PRICE_IN + c * PRICE_CACHED + n_out * PRICE_OUT) / 1e6


def cost_full(u):
    """The same call with nothing cached: every prompt token at PRICE_IN."""
    n_out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    return (u.get("promptTokenCount", 0) * PRICE_IN + n_out * PRICE_OUT) / 1e6


def http(method, path, body=None, timeout=300):
    url = f"{BASE}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                                             "content-type": "application/json"}, method=method)
    t0 = time.time()
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode()
        status, err = 200, None
        r = json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        status, err, r = e.code, e.read().decode(errors="replace"), None
    except Exception as e:  # timeouts, resets
        status, err, r = 0, f"{type(e).__name__}: {e}", None
    if status == 402:
        raise Stop(f"HTTP 402: {err}")
    return status, r, err, round(time.time() - t0, 3)


BODIES = {}    # long text -> "<omitted: md5 …, N tokens by countTokens>"


def redact(obj):
    """Replace every long document body registered in BODIES with its md5 + token count."""
    s = json.dumps(obj, ensure_ascii=False)
    for text, label in sorted(BODIES.items(), key=lambda kv: -len(kv[0])):
        s = s.replace(json.dumps(text, ensure_ascii=False)[1:-1], label)
    return json.loads(s)


def register(text, n_tokens=None, name=""):
    if text not in BODIES and len(text) > 400:
        n = n_tokens if n_tokens is not None else count_tokens(text)
        BODIES[text] = f"<omitted {name}: md5 {md5(text)}, {n} tokens by countTokens>"
    return text


def generate(body, step):
    """One generateContent call with retries on 429/5xx. Returns a record (request redacted, full response)."""
    retries = []
    while True:
        stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        status, r, err, secs = http("POST", f"models/{MODEL}:generateContent", body)
        if status in (0, 429, 500, 503, 504) and len(retries) < 4:
            retries.append({"why": f"HTTP {status}", "at": stamp, "body": (err or "")[:500]})
            time.sleep(20 if status == 429 else 5)
            continue
        break
    rec = {"request": redact(body), "http": status, "sent_utc": stamp, "wall_s": secs,
           "retries": retries, "error": err, "response": r}
    if r is not None:
        u = r.get("usageMetadata", {})
        cand = (r.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts", [])
        rec["text"] = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        rec["function_calls"] = [p["functionCall"] for p in parts if "functionCall" in p]
        rec["finishReason"] = cand.get("finishReason")
        rec["prompt"] = u.get("promptTokenCount", 0)
        rec["cached"] = u.get("cachedContentTokenCount", 0)
        rec["out"] = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
        rec["cost_usd"] = cost(u)
        rec["cost_full_rate_usd"] = cost_full(u)
        total = add_spend(rec["cost_usd"], step)
        if total > CAP:
            raise Stop(f"spend {total:.4f} over the {CAP} working cap")
    return rec


def count_tokens(text):
    status, r, err, secs = http("POST", f"models/{MODEL}:countTokens",
                                {"contents": [{"role": "user", "parts": [{"text": text}]}]})
    if status != 200:
        raise Stop(f"countTokens HTTP {status}: {err}")
    return r["totalTokens"]


def save(name, obj):
    path = os.path.join(RUNS, f"{DAY}-{name}.json")
    json.dump(obj, open(path, "w"), indent=1, ensure_ascii=False)
    return os.path.relpath(path, ROOT)


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
        json.dump(r, open(REPORT, "w"), indent=1, ensure_ascii=False)


def now_hms():
    return datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------- A: drafting the 45 documents

DRAFT_RULES = """You write internal documents for the SRE team of Sorrel, the company the handbook below describes.
Write ONE document in Markdown, plain and realistic, the way a small SRE team writes: specific, a little dry, some
tables or bullet lists where they help, no marketing tone. Start with '# <the exact title>' and then header lines
(date or 'Last updated: <date>', owner or author). Length: about 1,900 words.

Hard rules:
- Use every fact in the spec exactly as given. You may add realistic detail (times, panels, discussion, lessons), but
  invent no new people beyond: Aiko (web owner), Ravi (api owner), Mei (payments owner), Tom (notifier owner),
  Kenji Sato (platform lead), Sara (platform engineer), Hana (support lead), Daniel (api engineer), Yuki (notifier
  engineer), Priya (web engineer), Leo (payments engineer), Noor (SRE, joined the rotation in April 2026;
  never mention her in anything dated before 2026-04).
- Never contradict the handbook or the five actions at its top. Services, owners, providers and regions are the
  handbook's.
- Never give rollback steps or rollback commands for api or payments. A past rollback may be mentioned in the past
  tense in one sentence. Never mention a tool called dtool. Mention Shipyard only if the spec does, and then only as
  the spec says, with no commands.
- No phone numbers, account ids, email addresses or URLs other than the status pages the handbook names. Do not
  mention on-call pay, allowances or overtime. Do not mention support phone lines of any provider.
- Do not copy alert lines, and do not write lists of 'for this alert, the first move is X'.
- Everything in the document happens on or before its date.

The handbook (revision 2026-10-07a) follows.

"""


def draft(limit=None):
    STEP[0] = "A-draft"
    spec = json.load(open(os.path.join(LIB, "SPEC.json")))
    if limit:
        spec = spec[:int(limit)]
    hb = open(HANDBOOK_FILE).read()
    register(hb, name="handbook.md")
    system = DRAFT_RULES + hb
    out = {"meta": {"what": "A: library drafting calls (not measured)", "handbook_md5": md5(hb),
                    "draft_rules": DRAFT_RULES}, "calls": []}

    def one(s):
        path = os.path.join(ROOT, s["file"])
        if os.path.exists(path):
            return None
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": "Spec:\n" + json.dumps(
                    {k: s[k] for k in ("title", "kind", "date", "owner", "facts")}, indent=1, ensure_ascii=False)}]}],
                "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}
        rec = generate(body, "A-draft")
        rec["file"] = s["file"]
        if rec["http"] == 200 and rec.get("text"):
            text = rec["text"].strip()
            text = re.sub(r"^```(?:markdown)?\n|\n```$", "", text)
            open(path, "w").write(text.strip() + "\n")
        print(f"  {now_hms()} {s['file']:55} http {rec['http']} out {rec.get('out')} ${rec.get('cost_usd', 0):.4f}",
              flush=True)
        return rec

    with cf.ThreadPoolExecutor(4) as ex:
        for rec in ex.map(one, spec):
            if rec:
                with _lock:
                    out["calls"].append(rec)
                    save("a-draft", out)
    print(f"spent so far ${spent():.4f}")


# ---------------------------------------------------------------- A: pages and the index

STORY_DATES = {"deploying-with-shipyard": "2026-09-28", "payments-rollback-runbook": "2024-03-11",
               "postmortem-payments-pool-timeout": "2025-11-20", "postmortem-api-rollback-queue": "2026-08-27"}
HANDBOOK_DATE = "2026-10-07"


def handbook_pages(hb):
    """One page per '## ' section. The rules block on top is already in every systemInstruction, so page 1 gets
    only the revision line, the title and the owner lines in front of section 1."""
    first, rest = hb.split("\n## ", 1)
    head = first.split("\n")
    rev = head[0]
    title_at = first.index("# Sorrel On-Call Handbook")
    intro = rev + "\n\n" + first[title_at:].strip()
    chunks = ("## " + rest).split("\n## ")
    chunks = [chunks[0]] + ["## " + c for c in chunks[1:]]
    pages = []
    for i, c in enumerate(chunks):
        m = re.match(r"## (\d+)\. (.+)", c)
        n, name = m.group(1), m.group(2).strip()
        text = c.strip() + "\n"
        if i == 0:
            text = intro + "\n\n" + text
        pages.append({"id": f"handbook-{n}", "title": f"Handbook {n}. {name}", "updated": HANDBOOK_DATE,
                      "source": "runbooks/handbook.md", "text": text})
    return pages


def library_docs():
    spec = {os.path.basename(s["file"])[:-3]: s for s in json.load(open(os.path.join(LIB, "SPEC.json")))}
    docs = []
    for f in sorted(os.listdir(LIB)):
        if not f.endswith(".md"):
            continue
        stem = f[:-3]
        text = open(os.path.join(LIB, f)).read()
        title = re.match(r"# (.+)", text).group(1).strip()
        date = spec[stem]["date"] if stem in spec else STORY_DATES[stem]
        docs.append({"id": stem, "title": title, "updated": date, "source": f"library/{f}", "text": text})
    docs.sort(key=lambda d: (d["updated"], d["id"]))
    return docs


def index():
    hb = open(HANDBOOK_FILE).read()
    pages = handbook_pages(hb) + library_docs()
    rows = []
    for p in pages:
        rows.append({"id": p["id"], "title": p["title"], "updated": p["updated"], "source": p["source"],
                     "tokens": count_tokens(p["text"]), "md5": md5(p["text"])})
    json.dump(rows, open(os.path.join(LIB, "INDEX.json"), "w"), indent=1, ensure_ascii=False)
    docs = [{"source": "runbooks/handbook.md", "tokens": count_tokens(hb), "md5": md5(hb)}]
    for p in pages:
        if p["source"] != "runbooks/handbook.md":
            docs.append({"source": p["source"], "tokens": next(r["tokens"] for r in rows if r["id"] == p["id"]),
                         "md5": md5(p["text"])})
    total = sum(d["tokens"] for d in docs)
    print(f"{len(pages)} pages, {len(docs)} documents, {total:,} tokens by countTokens (documents counted one by one)")
    for d in sorted(docs, key=lambda d: d["tokens"])[:6]:
        print(f"  smallest: {d['tokens']:6} {d['source']}")
    for d in sorted(docs, key=lambda d: d["tokens"])[-3:]:
        print(f"  largest:  {d['tokens']:6} {d['source']}")
    return rows, docs, total


def freeze():
    """A + Q frozen: md5 of every input file, token counts, written to a run file and the report."""
    rows, docs, total = index()
    files = ["runbooks/handbook.md", "library/SPEC.json", "library/INDEX.json", "tickets/questions.json"] + \
        sorted(f"library/{f}" for f in os.listdir(LIB) if f.endswith(".md"))
    md5s = {f: hashlib.md5(open(os.path.join(ROOT, f), "rb").read()).hexdigest() for f in files}
    hb = open(HANDBOOK_FILE).read()
    out = {"frozen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "md5": md5s,
           "documents": docs, "pages": rows, "documents_total_tokens": total}
    path = save("a-freeze", out)
    by = {r["id"]: r for r in rows}
    size5 = ["handbook", "deploying-with-shipyard", "payments-rollback-runbook",
             "postmortem-payments-pool-timeout", "postmortem-api-rollback-queue"]
    report_set(["A_library"], {
        "run": path, "documents": len(docs), "pages": len(rows), "handbook_pages": sum(r["id"].startswith("handbook-") for r in rows),
        "total_tokens_50_documents": total, "handbook_tokens": docs[0]["tokens"],
        "size_5_tokens": docs[0]["tokens"] + sum(by[i]["tokens"] for i in size5[1:]),
        "story_docs": {i: {"tokens": by[i]["tokens"], "md5": by[i]["md5"]} for i in size5[1:]},
        "min_doc_tokens": min(d["tokens"] for d in docs), "max_doc_tokens_excl_handbook": max(d["tokens"] for d in docs[1:]),
        "md5": md5s})
    q = json.load(open(os.path.join(ROOT, "tickets", "questions.json")))
    report_set(["Q_questions"], {"file": "tickets/questions.json", "md5": md5s["tickets/questions.json"],
                                 "n": len(q["questions"]), "grading": q["grading"],
                                 "questions": [{k: x[k] for k in ("id", "kind", "question", "truth", "wrong", "page")}
                                               for x in q["questions"]]})
    print("frozen ->", path)


def models():
    """M0: models.get is free. Records inputTokenLimit as the API states it."""
    st, r, err, secs = http("GET", f"models/{MODEL}")
    path = save("m0-models-get", {"request": f"GET {BASE}/models/{MODEL}", "http": st, "wall_s": secs, "response": r,
                                   "error": err, "sent_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print(st, json.dumps(r, indent=1) if r else err)
    report_set(["M0_docs", "models_get"], {"run": path, "http": st, "inputTokenLimit": (r or {}).get("inputTokenLimit"),
                                           "outputTokenLimit": (r or {}).get("outputTokenLimit")})


# ---------------------------------------------------------------- the shapes (measured)

FREEZE = os.path.join(RUNS, f"{DAY}-a-freeze.json")
QFILE = os.path.join(ROOT, "tickets", "questions.json")
RETIRED = "payments-rollback-runbook"
NOTICE = ('> RETIRED 2026-09-28: payments no longer deploys or rolls back with dtool. '
          'See the page "Deploying with Shipyard".\n')
SIZE5 = ["deploying-with-shipyard", RETIRED, "postmortem-payments-pool-timeout", "postmortem-api-rollback-queue"]
USER_Q = "Question from the on-call engineer:\n{q}\nAnswer from the pages. If the pages do not say, say so."


def user_alert(alert):
    return f"Alert:\n{alert}\n{ASK}"


def load_frozen():
    """Pages and questions exactly as frozen; refuse to run if anything changed since the freeze."""
    fz = json.load(open(FREEZE))
    for f, h in fz["md5"].items():
        now = hashlib.md5(open(os.path.join(ROOT, f), "rb").read()).hexdigest()
        if now != h:
            raise Stop(f"{f} changed since the freeze ({h} -> {now})")
    hb = open(HANDBOOK_FILE).read()
    pages = handbook_pages(hb) + library_docs()
    idx = {r["id"]: r for r in json.load(open(os.path.join(LIB, "INDEX.json")))}
    for p in pages:
        assert md5(p["text"]) == idx[p["id"]]["md5"], p["id"]
        p["tokens"] = idx[p["id"]]["tokens"]
        register(p["text"], p["tokens"], p["id"])
    hb_tokens = next(d["tokens"] for d in fz["documents"] if d["source"] == "runbooks/handbook.md")
    register(hb, hb_tokens, "handbook.md")
    qs = json.load(open(QFILE))["questions"]
    return hb, pages, qs


def carry_text(hb, pages, size):
    """carry-N systemInstruction: the handbook file as it is (rules on top), then each other document whole."""
    if size == 1:
        return hb
    others = [p for p in pages if not p["id"].startswith("handbook-")]
    if size == 5:
        others = [p for p in others if p["id"] in SIZE5]
    return hb + "\n\nThe team's other pages follow.\n" + "".join(
        f"\n----- page: {p['title']} -----\n\n{p['text']}" for p in others)


def contents_list(pages, size, dates=False, archived=False):
    rows = [p for p in pages if size == 50 or p["id"].startswith("handbook-") or (size == 5 and p["id"] in SIZE5)]
    if archived:
        rows = [p for p in rows if p["id"] != RETIRED]
    return "\n".join(f"{p['id']}: {p['title']}" + (f" (last updated {p['updated']})" if dates else "") for p in rows)


def lookup_system(pages, size, dates=False, archived=False):
    return (SYSTEM + "\nThe team's pages are listed below, one per line as id: title. To read a page, call read_page "
            "with its id. You may read up to 4 pages.\n\n" + contents_list(pages, size, dates, archived))


READ_PAGE = {"name": "read_page", "description": "Read one of the team's pages by its id from the contents list.",
             "parameters": {"type": "object", "properties": {
                 "id": {"type": "string", "description": "the page id, exactly as the contents list gives it"}},
                 "required": ["id"]}}


def page_reader(pages, size, archived=False, notice=False):
    allowed = {p["id"]: p for p in pages
               if size == 50 or p["id"].startswith("handbook-") or (size == 5 and p["id"] in SIZE5)}
    if archived:
        allowed.pop(RETIRED, None)

    def read(pid):
        p = allowed.get(pid)
        if p is None:
            return {"error": f"no page with id {pid!r}"}
        text = p["text"]
        if notice and pid == RETIRED:
            text = NOTICE + text
            register(text, None, RETIRED + "+notice")
        return {"id": pid, "title": p["title"], "text": text}
    return read


def ask_lookup(system, user, read, step, schema=False, max_reads=4):
    """The model sees the contents list and may call read_page up to 4 times; then it answers.
    Returns the calls, the pages read in order, and the final text."""
    conversation = [{"role": "user", "parts": [{"text": user}]}]
    calls, reads, refused = [], [], []
    text = ""
    for _ in range(10):
        cfg = {"thinkingConfig": {"thinkingLevel": "low"}}
        if schema:
            cfg["responseMimeType"] = "application/json"
            cfg["responseSchema"] = SCHEMA
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": conversation,
                "tools": [{"functionDeclarations": [READ_PAGE]}], "generationConfig": cfg}
        if len(reads) >= max_reads:
            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}   # 4 pages read: now it answers
        rec = generate(body, step)
        calls.append(rec)
        if rec["http"] != 200:
            return {"calls": calls, "reads": reads, "text": None, "error": rec["error"], "refused_reads": refused}
        turn = (rec["response"].get("candidates") or [{}])[0].get("content")
        fcs = rec.get("function_calls") or []
        if not fcs or turn is None:
            text = rec.get("text", "")
            break
        conversation.append(turn)                      # the model's turn back exactly as it came
        replies = []
        for fc in fcs:
            pid = (fc.get("args") or {}).get("id")
            if fc.get("name") != "read_page":
                result = {"error": f"no function called {fc.get('name')!r}"}
            elif len(reads) >= max_reads:
                result = {"error": "read limit reached: 4 pages. Answer from the pages you have read."}
                refused.append(pid)
            else:
                result = read(pid)
                reads.append(pid)
            rec.setdefault("tool_results", []).append({"call": fc, "result": redact(result)})
            reply = {"name": fc.get("name"), "response": result}
            if fc.get("id"):
                reply["id"] = fc["id"]
            replies.append({"functionResponse": reply})
        conversation.append({"role": "user", "parts": replies})
    return {"calls": calls, "reads": reads, "text": text, "error": None, "refused_reads": refused}


NAMES = SERVICES + PROVIDERS + ["shipyard"]


def code_pick(pages, question):
    """No model choice: every page whose title names a service, provider or Shipyard that the question names,
    plus the handbook's runbook page (section 5) when a service is named."""
    found = [n for n in NAMES if re.search(rf"\b{n}\b", question, re.I)]
    picked = [p for p in pages if any(re.search(rf"\b{n}\b", p["title"], re.I) for n in found)]
    if any(n in SERVICES for n in found) and not any(p["id"] == "handbook-5" for p in picked):
        picked.append(next(p for p in pages if p["id"] == "handbook-5"))
    return found, picked


def code_system(picked):
    if not picked:
        return SYSTEM + "\nYour code found no page whose title matches this question."
    return SYSTEM + "\nThe pages your code picked for this question:\n" + "".join(
        f"\n----- page: {p['title']} -----\n\n{p['text']}" for p in picked)


def plain_call(system, user, step, schema=False, cached=None, tools=None):
    cfg = {"thinkingConfig": {"thinkingLevel": "low"}}
    if schema:
        cfg["responseMimeType"] = "application/json"
        cfg["responseSchema"] = SCHEMA
    body = {"contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": cfg}
    if cached:
        body["cachedContent"] = cached
    else:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        body["tools"] = tools
    return generate(body, step)


class Cache:
    """An explicit cache of the carry-50 systemInstruction, as cache.py makes one. Storage billed per second alive."""
    def __init__(self, text, step, ttl=3600):
        self.step, self.t0 = step, time.time()
        body = {"model": f"models/{MODEL}", "systemInstruction": {"parts": [{"text": text}]}, "ttl": f"{ttl}s"}
        stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        st, r, err, secs = http("POST", "cachedContents", body)
        self.create = {"request": redact(body), "http": st, "sent_utc": stamp, "wall_s": secs, "response": r, "error": err}
        if st != 200:
            raise Stop(f"cache create HTTP {st}: {err}")
        self.name = r["name"]
        self.tokens = r.get("usageMetadata", {}).get("totalTokenCount", 0)
        self.create_cost = self.tokens * PRICE_IN / 1e6     # docs silent on a create charge: counted at input rate (as ep09)
        add_spend(self.create_cost, step)

    def close(self):
        st, r, err, _ = http("DELETE", self.name)
        alive = time.time() - self.t0
        storage = self.tokens * PRICE_STORAGE_H / 1e6 * alive / 3600
        add_spend(storage, self.step)
        return {"create": self.create, "name": self.name, "tokens": self.tokens,
                "create_cost_counted_usd": self.create_cost, "alive_s": round(alive, 1),
                "storage_cost_usd": storage,
                "storage_arithmetic": f"{self.tokens} tokens x $0.50 / 1M / hour x {alive:.0f} s / 3600 s = ${storage:.6f}",
                "delete_http": st, "delete_error": err}


NOT_IN_PAGES = ["do not say", "don't say", "does not say", "doesn't say", "not in the pages", "no information",
                "do not mention", "don't mention", "does not mention", "doesn't mention", "not mentioned",
                "not specified", "do not specify", "don't specify", "does not specify", "doesn't specify",
                "not covered", "do not contain", "don't contain", "does not contain", "doesn't contain",
                "not provided", "do not include", "don't include", "does not include", "doesn't include",
                "not listed", "no mention", "not documented", "do not list", "don't list", "not available in",
                "do not provide", "don't provide", "does not provide", "doesn't provide", "not stated", "not found"]


def grade(q, text):
    t = (text or "").lower()
    truth_groups = [g for g in q["truth"] if isinstance(g, list)]
    truth_ok = bool(truth_groups) and all(any(a.lower() in t for a in g) for g in truth_groups)
    wrong_hit = [w for w in q["wrong"] if w.lower() in t]
    says_not = any(s in t for s in NOT_IN_PAGES)
    if q["kind"] == "trap":
        verdict = "mixed" if truth_ok and wrong_hit else "right" if truth_ok else "wrong" if wrong_hit else "other"
    elif q["kind"] == "none":
        verdict = "said-not-in-pages" if says_not else "answered"          # graded by hand
    else:
        verdict = "right" if truth_ok and not wrong_hit else "said-not-in-pages" if says_not and not truth_ok else "wrong"
    return {"code_verdict": verdict, "truth_ok": truth_ok, "wrong_terms": wrong_hit, "says_not_in_pages": says_not}


def loop_totals(calls):
    ok = [c for c in calls if c.get("response") is not None]
    return {"calls": len(calls), "prompt_tokens": sum(c.get("prompt", 0) for c in ok),
            "cached_tokens": sum(c.get("cached", 0) for c in ok), "out_tokens": sum(c.get("out", 0) for c in ok),
            "cost_usd": sum(c.get("cost_usd", 0) for c in ok),
            "cost_full_rate_usd": sum(c.get("cost_full_rate_usd", 0) for c in ok),
            "wall_s": round(sum(c["wall_s"] for c in calls), 3)}



def count_request(body):
    st, r, err, _ = http("POST", f"models/{MODEL}:countTokens",
                         {"generateContentRequest": {"model": f"models/{MODEL}", **body}})
    if st != 200:
        raise Stop(f"countTokens HTTP {st}: {err}")
    return r["totalTokens"]


def m1():
    STEP[0] = "M1"
    hb, pages, qs = load_frozen()
    case = CASES[0]
    assert case["id"] == "payments-latency"
    out = {"meta": {"what": "M1: one call per size, alert payments-latency, triage.py prompt mode (no schema)",
                    "alert": case["alert"], "user_text": user_alert(case["alert"])}, "carry": [], "contents_list": []}
    summary = {"carry": {}, "contents_list": {}}
    for size in (1, 5, 50):
        sys_text = carry_text(hb, pages, size)
        register(sys_text, None, f"carry-{size} systemInstruction")
        body = {"systemInstruction": {"parts": [{"text": sys_text}]},
                "contents": [{"role": "user", "parts": [{"text": user_alert(case["alert"])}]}],
                "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}
        n_sys, n_req = count_tokens(sys_text), count_request(body)
        rec = generate(body, "M1")
        rec.update({"size": size, "countTokens_systemInstruction": n_sys, "countTokens_request": n_req})
        out["carry"].append(rec)
        path = save("m1-sizes", out)
        summary["carry"][str(size)] = {"countTokens_system": n_sys, "countTokens_request": n_req,
                                       "promptTokenCount": rec.get("prompt"), "cached": rec.get("cached"),
                                       "out_tokens": rec.get("out"), "wall_s": rec["wall_s"],
                                       "cost_full_rate_usd": round(rec.get("cost_full_rate_usd", 0), 6),
                                       "cost_billed_usd": round(rec.get("cost_usd", 0), 6), "answer": rec.get("text")}
        print(f"  carry-{size}: system {n_sys:,} / request {n_req:,} / promptTokenCount {rec.get('prompt')} "
              f"{rec['wall_s']} s ${rec.get('cost_full_rate_usd', 0):.5f}", flush=True)
    for size in (5, 50):
        sys_text = lookup_system(pages, size)
        body = {"systemInstruction": {"parts": [{"text": sys_text}]},
                "contents": [{"role": "user", "parts": [{"text": user_alert(case["alert"])}]}],
                "tools": [{"functionDeclarations": [READ_PAGE]}],
                "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}
        n_sys, n_req = count_tokens(sys_text), count_request(body)
        rec = generate(body, "M1")
        rec.update({"size": size, "countTokens_systemInstruction": n_sys, "countTokens_request_with_tool": n_req,
                    "note": "first call of a look-up loop only: the contents list + read_page declared; no page read"})
        out["contents_list"].append(rec)
        path = save("m1-sizes", out)
        summary["contents_list"][str(size)] = {"countTokens_system": n_sys, "countTokens_request_with_tool": n_req,
                                               "promptTokenCount": rec.get("prompt"), "out_tokens": rec.get("out"),
                                               "wall_s": rec["wall_s"],
                                               "cost_full_rate_usd": round(rec.get("cost_full_rate_usd", 0), 6),
                                               "function_calls": rec.get("function_calls")}
        print(f"  list-{size}: system {n_sys:,} / request {n_req:,} / promptTokenCount {rec.get('prompt')} "
              f"{rec['wall_s']} s ${rec.get('cost_full_rate_usd', 0):.5f} calls {rec.get('function_calls')}", flush=True)
    summary["run"] = path
    report_set(["M1_sizes"], summary)


def run_question(shape, q, hb, pages, cache=None, step="?"):
    user = USER_Q.format(q=q["question"])
    if shape == "carry-5":
        rec = plain_call(carry_text(hb, pages, 5), user, step)
        res = {"calls": [rec], "text": rec.get("text"), "error": rec["error"]}
    elif shape == "carry-50":
        rec = plain_call(None, user, step, cached=cache.name)
        res = {"calls": [rec], "text": rec.get("text"), "error": rec["error"]}
    elif shape == "code-50":
        found, picked = code_pick(pages, q["question"])
        rec = plain_call(code_system(picked), user, step)
        res = {"calls": [rec], "text": rec.get("text"), "error": rec["error"], "names_found": found,
               "picked": [p["id"] for p in picked]}
    else:   # model-50 and the three fixes
        dates, archived, notice = shape == "fix-dates", shape == "fix-archived", shape == "fix-notice"
        res = ask_lookup(lookup_system(pages, 50, dates, archived), user,
                         page_reader(pages, 50, archived, notice), step)
    res["grade"] = grade(q, res.get("text"))
    res["totals"] = loop_totals(res["calls"])
    return res


SHAPE_META = {
    "carry-5": "systemInstruction = handbook.md as it is (rules on top) + the 4 story documents whole",
    "carry-50": "systemInstruction = handbook.md + all 49 other documents whole, sent through an explicit cache "
                "(cachedContents, as cache.py) to save money; the cache holds exactly that systemInstruction, "
                "so answers do not depend on it",
    "model-50": "systemInstruction = rules.SYSTEM + the contents list (id: title, one per line, INDEX order) + "
                "read_page(id); up to 4 reads, then toolConfig mode NONE so it answers",
    "code-50": "code picks every page whose title names a service/provider/Shipyard named in the question, plus "
               "handbook-5 when a service is named; one call with SYSTEM + the picked pages",
    "fix-dates": "model-50 with each contents line showing (last updated YYYY-MM-DD)",
    "fix-archived": "model-50 with the retired runbook removed from the list and from read_page",
    "fix-notice": "model-50 with a one-line retired notice on top of the retired runbook's text; list unchanged. "
                  "Notice: " + NOTICE.strip(),
}


def m4(shape):
    STEP[0] = "M4"
    hb, pages, qs = load_frozen()
    traps = [q for q in qs if q["kind"] == "trap"]
    out = {"meta": {"what": f"M4 trap, shape {shape}", "shape": SHAPE_META[shape], "user_template": USER_Q,
                    "order": "run 1..5, both trap questions per run, one call at a time"}, "items": []}
    cache = Cache(carry_text(hb, pages, 50), "M4") if shape == "carry-50" else None
    name = f"m4-{shape}"
    try:
        for run in range(1, 6):
            for q in traps:
                res = run_question(shape, q, hb, pages, cache, "M4")
                res.update({"qid": q["id"], "run": run})
                out["items"].append(res)
                save(name, out)
                print(f"  {now_hms()} {shape} run {run} {q['id']:18} {res['grade']['code_verdict']:6} "
                      f"reads {res.get('reads', res.get('picked'))} ${res['totals']['cost_usd']:.4f}", flush=True)
    finally:
        if cache:
            out["cache"] = cache.close()
            save(name, out)
    path = save(name, out)
    summ = {"run": path, "shape": SHAPE_META[shape]}
    for q in traps:
        its = [i for i in out["items"] if i["qid"] == q["id"]]
        v = [i["grade"]["code_verdict"] for i in its]
        summ[q["id"]] = {"right": v.count("right"), "wrong": v.count("wrong"), "mixed": v.count("mixed"),
                         "other": v.count("other"), "n": len(v),
                         "pages_read_or_picked": [i.get("reads", i.get("picked")) for i in its]}
    tot = [i["totals"] for i in out["items"]]
    summ.update({"calls": sum(t["calls"] for t in tot), "prompt_tokens": sum(t["prompt_tokens"] for t in tot),
                 "cost_usd": round(sum(t["cost_usd"] for t in tot), 6),
                 "cost_full_rate_usd": round(sum(t["cost_full_rate_usd"] for t in tot), 6),
                 "median_wall_s": statistics.median(t["wall_s"] for t in tot)})
    if cache:
        summ["cache"] = {k: out["cache"][k] for k in ("tokens", "create_cost_counted_usd", "storage_cost_usd", "alive_s")}
    report_set(["M4_trap", shape], summ)


def m2(shape):
    STEP[0] = "M2"
    hb, pages, qs = load_frozen()
    out = {"meta": {"what": f"M2 question set, shape {shape}", "shape": SHAPE_META[shape], "user_template": USER_Q,
                    "order": "tickets/questions.json order, once each, one call at a time"}, "items": []}
    cache = Cache(carry_text(hb, pages, 50), "M2") if shape == "carry-50" else None
    name = f"m2-{shape}"
    try:
        for q in qs:
            res = run_question(shape, q, hb, pages, cache, "M2")
            res["qid"] = q["id"]
            out["items"].append(res)
            save(name, out)
            print(f"  {now_hms()} {shape} {q['id']:20} {res['grade']['code_verdict']:18} "
                  f"reads {res.get('reads', res.get('picked'))} ${res['totals']['cost_usd']:.4f}", flush=True)
    finally:
        if cache:
            out["cache"] = cache.close()
            save(name, out)
    path = save(name, out)
    tot = [i["totals"] for i in out["items"]]
    v = [i["grade"]["code_verdict"] for i in out["items"]]
    summ = {"run": path, "shape": SHAPE_META[shape], "code_verdicts": {k: v.count(k) for k in sorted(set(v))},
            "per_question": [{"id": i["qid"], "verdict": i["grade"]["code_verdict"],
                              "wrong_terms": i["grade"]["wrong_terms"],
                              "pages": i.get("reads", i.get("picked")), "calls": i["totals"]["calls"],
                              "prompt_tokens": i["totals"]["prompt_tokens"], "wall_s": i["totals"]["wall_s"]}
                             for i in out["items"]],
            "calls": sum(t["calls"] for t in tot), "prompt_tokens": sum(t["prompt_tokens"] for t in tot),
            "tokens_per_question_mean": round(sum(t["prompt_tokens"] + t["out_tokens"] for t in tot) / len(tot)),
            "cost_usd": round(sum(t["cost_usd"] for t in tot), 6),
            "cost_full_rate_usd": round(sum(t["cost_full_rate_usd"] for t in tot), 6),
            "median_wall_s": statistics.median(t["wall_s"] for t in tot)}
    if cache:
        summ["cache"] = {k: out["cache"][k] for k in ("tokens", "create_cost_counted_usd", "storage_cost_usd", "alive_s")}
    report_set(["M2_questions", shape], summ)


def in_my_shape(t):
    return (isinstance(t, dict) and set(t) == {"severity", "service", "first_move", "reason"}
            and t["severity"] in ("P1", "P2", "P3") and t["service"] in SERVICES and t["first_move"] in ACTIONS)


def m3(shape):
    STEP[0] = "M3"
    hb, pages, qs = load_frozen()
    out = {"meta": {"what": f"M3 thirty alerts, shape {shape}, triage.py schema mode", "items_order": "incidents.json"},
           "items": []}
    name = f"m3-{shape}"
    fallback = False
    hb_pages = {p["id"]: p for p in pages if p["id"].startswith("handbook-")}
    for case in CASES:
        user = user_alert(case["alert"])
        if shape == "carry-1":
            rec = plain_call(hb, user, "M3", schema=True)
            res = {"calls": [rec], "text": rec.get("text")}
        else:
            system = lookup_system(pages, 1)
            res = None
            if not fallback:
                res = ask_lookup(system, user, page_reader(pages, 1), "M3", schema=True)
                first = res["calls"][0]
                if first["http"] == 400:
                    fallback = True
                    out["schema_plus_tools_error"] = {"http": 400, "error": first["error"], "request": first["request"]}
                    out["meta"]["fallback"] = ("tools + responseSchema refused: look-up loop without schema, then a "
                                               "second call in schema mode without tools, pages read included")
                    save(name, out)
                    print("  tools + schema refused; switching to the two-step fallback", flush=True)
                    res = None
            if res is None:
                res = ask_lookup(system, user, page_reader(pages, 1), "M3", schema=False)
                read_text = "".join(f"\n----- page: {hb_pages[p]['title']} -----\n\n{hb_pages[p]['text']}"
                                    for p in dict.fromkeys(res["reads"]) if p in hb_pages)
                fin = plain_call(SYSTEM + ("\nThe pages you read:\n" + read_text if read_text else ""), user, "M3",
                                 schema=True)
                res["calls"].append(fin)
                res["text"] = fin.get("text")
        try:
            t = json.loads(res["text"] or "")
            valid = True
        except Exception:
            t, valid = None, False
        shaped = valid and in_my_shape(t)
        res.update({"id": case["id"], "want": case["want"], "valid": valid, "shaped": shaped,
                    "got": t.get("first_move") if isinstance(t, dict) else None})
        res["right"] = bool(shaped and t["first_move"] == case["want"])
        res["totals"] = loop_totals(res["calls"])
        out["items"].append(res)
        save(name, out)
        print(f"  {now_hms()} {shape} {case['id']:28} want {case['want']:15} got {res['got']} "
              f"reads {res.get('reads')} ${res['totals']['cost_usd']:.4f}", flush=True)
    path = save(name, out)
    its = out["items"]
    tot = [i["totals"] for i in its]
    summ = {"run": path, "score": f"{sum(i['right'] for i in its)}/30",
            "valid_json": sum(i["valid"] for i in its), "in_my_shape": sum(i["shaped"] for i in its),
            "misses": [[i["id"], i["want"], i["got"]] for i in its if not i["right"]],
            "calls": sum(t["calls"] for t in tot), "calls_per_alert_mean": round(sum(t["calls"] for t in tot) / 30, 2),
            "prompt_tokens": sum(t["prompt_tokens"] for t in tot),
            "tokens_per_alert_mean": round(sum(t["prompt_tokens"] + t["out_tokens"] for t in tot) / 30),
            "cost_usd": round(sum(t["cost_usd"] for t in tot), 6),
            "cost_full_rate_usd": round(sum(t["cost_full_rate_usd"] for t in tot), 6),
            "median_wall_s": statistics.median(t["wall_s"] for t in tot)}
    if shape == "model-1":
        summ["pages_read_per_alert"] = {i["id"]: i.get("reads") for i in its}
        summ["tools_plus_schema"] = ("refused: see schema_plus_tools_error in the run file" if fallback
                                     else "accepted in one request")
    report_set(["M3_alerts", shape], summ)


if __name__ == "__main__":
    cmd = sys.argv[1]
    try:
        globals()[cmd](*sys.argv[2:])
    except Stop as e:
        print(f"STOP: {e}", flush=True)
        report_set(["stopped"], {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "why": str(e)})
        sys.exit(2)
