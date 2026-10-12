"""EP12 measurement harness, not episode code: when the titles aren't enough, search the pages.

    python3 measure/ep12.py m0-list            # M0: models.list + models.get for the embedding model (free)
    python3 measure/ep12.py m0-long            # M0: ONE embed call on the longest existing page, past the limit
    python3 measure/ep12.py a-draft            # A: draft the new pages from library/SPEC-ep12.json
    python3 measure/ep12.py a-freeze           # A+Q: INDEX-ep12.json, countTokens every page, md5 of every input
    python3 measure/ep12.py r                  # R: recall at 5, three methods (+ the cut-at-limit variant)
    python3 measure/ep12.py t                  # T: titles alone (lookup.py's look-up on INDEX-ep12)
    python3 measure/ep12.py e1 code|model      # E1: search then answer
    python3 measure/ep12.py e2                 # E2: carry it all, explicit cache
Call style as lookup.py: raw HTTP with urllib, gemini-3.8-flash, thinking low, rules.SYSTEM, lookup.ASK.
Run files keep each request with long bodies replaced by md5 + token count, the full response incl. usageMetadata,
every tool call and tool result, and wall time. Spend is tracked in runs/ep12/spend.json as calls return.
"""
import concurrent.futures as cf, hashlib, json, os, re, statistics, sys, threading, time, urllib.error, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

RUNS = os.path.join(ROOT, "runs", "ep12")
DAY = "2026-10-11"
MODEL = "gemini-3.8-flash"
BASE = "https://generativelanguage.googleapis.com/v1beta"
CAP = 4.00
SPENT_FILE = os.path.join(RUNS, "spend.json")
REPORT = os.path.expanduser("~/Projects/vivek-ai/content/ai-engineering-course/qc/ep12/measure/report.json")

if not os.environ.get("GEMINI_API_KEY"):          # the key lives in .env (gitignored); never printed, never logged
    for line in open(os.path.join(ROOT, ".env")):
        if line.startswith("GEMINI_API_KEY="):
            os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")

_lock = threading.Lock()


class Stop(Exception):
    pass


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()


def file_md5(path):
    return hashlib.md5(open(os.path.join(ROOT, path), "rb").read()).hexdigest()


def stamp():
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
            d = {"usd": 0.0, "cap_usd": CAP, "by_step": {}, "note": "every billed call, added as it returned"}
        d["usd"] += usd
        d["by_step"][step] = d["by_step"].get(step, 0.0) + usd
        d["updated_utc"] = stamp()
        json.dump(d, open(SPENT_FILE, "w"), indent=1)
        return d["usd"]


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
        r["spend_file"] = "nightshift/" + os.path.relpath(SPENT_FILE, ROOT)
        json.dump(r, open(REPORT, "w"), indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- M0: the embedding model (free calls)

def m0_list():
    out = {"sent_utc": stamp(), "pages": []}
    token, models = None, []
    while True:
        st, r, err, secs = http("GET", "models?pageSize=1000" + (f"&pageToken={token}" if token else ""))
        out["pages"].append({"http": st, "wall_s": secs, "error": err, "response": r})
        if st != 200:
            break
        models += r.get("models", [])
        token = r.get("nextPageToken")
        if not token:
            break
    embed = [m for m in models if "embedContent" in m.get("supportedGenerationMethods", [])]
    out["embedContent_models"] = [{k: m.get(k) for k in ("name", "displayName", "version", "inputTokenLimit",
                                                          "outputTokenLimit", "supportedGenerationMethods",
                                                          "description")} for m in embed]
    path = save("m0-models-list", out)
    for m in out["embedContent_models"]:
        print(m["name"], m["inputTokenLimit"], m["supportedGenerationMethods"], "|", m["displayName"])
    print("->", path)


def m0_get(name):
    st, r, err, secs = http("GET", name)
    path = save("m0-models-get-" + name.split("/")[-1], {"request": f"GET {BASE}/{name}", "http": st, "wall_s": secs,
                                                         "sent_utc": stamp(), "response": r, "error": err})
    print(st, json.dumps(r, indent=1) if r else err)
    print("->", path)


EMBED = "models/gemini-embedding-2"
PRICE_EMBED = 0.20                   # dollars per million text input tokens, pricing page (runs/ep12/m0), paid, standard


def embed_count(text):
    """countTokens on the embedding model (free)."""
    st, r, err, secs = http("POST", f"{EMBED}:countTokens", {"contents": [{"parts": [{"text": text}]}]})
    if st != 200:
        raise Stop(f"countTokens {EMBED} HTTP {st}: {err}")
    return r["totalTokens"]


def existing_pages():
    import lookup
    return lookup.pages()


def m0_long():
    """ONE embedContent call on the longest existing document, no autoTruncate set: cut, or error?"""
    pages = existing_pages()
    sizes = sorted(((embed_count(p["text"]), p["id"]) for p in pages if p["text"].strip()), reverse=True)
    hb = open("runbooks/handbook.md").read()
    hb_tokens = embed_count(hb)
    target_name, target = ("runbooks/handbook.md (whole file)", hb) if hb_tokens > sizes[0][0] else (sizes[0][1], None)
    body = {"model": EMBED, "content": {"parts": [{"text": target}]}}
    t0 = stamp()
    st, r, err, secs = http("POST", f"{EMBED}:embedContent", body)
    usage = (r or {}).get("usageMetadata", {})
    usd = usage.get("promptTokenCount", hb_tokens) * PRICE_EMBED / 1e6 if st == 200 else 0.0
    add_spend(usd, "M0-long")
    vals = ((r or {}).get("embedding") or {}).get("values") or []
    out = {"what": "M0: one embedContent call, no autoTruncate set, on the longest existing document",
           "target": target_name, "target_md5": md5(target), "target_tokens_by_embed_countTokens": hb_tokens,
           "input_token_limit_models_get": 8192,
           "longest_pages_by_embed_countTokens": [{"id": i, "tokens": n} for n, i in sizes[:8]],
           "pages_over_8192": [i for n, i in sizes if n > 8192], "pages_counted": len(sizes),
           "request": {"model": EMBED, "content": {"parts": [{"text": f"<omitted: md5 {md5(target)}, {hb_tokens} tokens>"}]}},
           "http": st, "sent_utc": t0, "wall_s": secs, "error": err,
           "response_without_values": {k: v for k, v in (r or {}).items() if k != "embedding"},
           "embedding_len": len(vals), "embedding_first5": vals[:5], "cost_usd": usd}
    path = save("m0-embed-longest", out)
    print(json.dumps({k: v for k, v in out.items() if k not in ("request",)}, indent=1)[:3000])
    print("->", path)


# ---------------------------------------------------------------- generateContent, as lookup.py calls it

PRICE_IN, PRICE_OUT = 0.75, 3.75                       # lookup.py, dollars per million; thinking billed as out
PRICE_CACHED = 0.075                                   # pricing page (runs/ep12/m0), 3.8 Flash, through 2026-12-31
PRICE_STORAGE_H = 0.50                                 # same page: per 1M tokens per hour, through 2026-12-31
BODIES = {}


def cost(u):
    p, c = u.get("promptTokenCount", 0), u.get("cachedContentTokenCount", 0)
    n_out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    return ((p - c) * PRICE_IN + c * PRICE_CACHED + n_out * PRICE_OUT) / 1e6


def register(text, n_tokens, name=""):
    if text not in BODIES and len(text) > 400:
        BODIES[text] = f"<omitted {name}: md5 {md5(text)}, {n_tokens} tokens by countTokens>"
    return text


def redact(obj):
    s = json.dumps(obj, ensure_ascii=False)
    for text, label in sorted(BODIES.items(), key=lambda kv: -len(kv[0])):
        s = s.replace(json.dumps(text, ensure_ascii=False)[1:-1], label)
    return json.loads(s)


def count_tokens(text):
    st, r, err, secs = http("POST", f"models/{MODEL}:countTokens",
                            {"contents": [{"role": "user", "parts": [{"text": text}]}]})
    if st != 200:
        raise Stop(f"countTokens HTTP {st}: {err}")
    return r["totalTokens"]


def generate(body, step, path=None):
    """One generateContent call (lookup.py's style: thinking low), retries on 429/5xx. Returns a record."""
    body.setdefault("generationConfig", {})["thinkingConfig"] = {"thinkingLevel": "low"}
    if spent() > CAP - 0.05:
        raise Stop(f"spend {spent():.4f} at the {CAP} cap")
    retries = []
    while True:
        t0 = stamp()
        st, r, err, secs = http("POST", path or f"models/{MODEL}:generateContent", body)
        if st in (0, 429, 500, 503, 504) and len(retries) < 4:
            retries.append({"why": f"HTTP {st}", "at": t0, "body": (err or "")[:500]})
            time.sleep(20 if st == 429 else 5)
            continue
        break
    rec = {"request": redact(body), "http": st, "sent_utc": t0, "wall_s": secs, "retries": retries, "error": err,
           "response": r}
    if r is not None:
        u = r.get("usageMetadata", {})
        cand = (r.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts", [])
        rec["content"] = cand.get("content")
        rec["text"] = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        rec["function_calls"] = [p["functionCall"] for p in parts if "functionCall" in p]
        rec["finishReason"] = cand.get("finishReason")
        rec["prompt"] = u.get("promptTokenCount", 0)
        rec["cached"] = u.get("cachedContentTokenCount", 0)
        rec["out"] = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
        rec["cost_usd"] = cost(u)
        add_spend(rec["cost_usd"], step)
    elif st != 200:
        print(f"  HTTP {st}: {(err or '')[:300]}", flush=True)
    return rec


# ---------------------------------------------------------------- A: drafting the new pages (library building)

CONTEXT = """Sorrel is a scheduling app (salons, clinics, tutors book appointments through it). Four services: web
(pages and the admin tool), api (businesses, bookings, search, the partner API, the audit log), payments (charges,
refunds, weekly payouts to businesses), notifier (email and SMS). Regions: ap-northeast, us-east, eu-west.
Owners: Aiko (web), Ravi (api), Mei (payments), Tom (notifier). Others: Kenji Sato (platform lead), Sara (platform
engineer), Hana (support lead), Daniel (api engineer), Yuki (notifier engineer), Priya (web engineer), Leo (payments
engineer), Noor (SRE, joined the rotation in April 2026). Providers: stripe (cards), twilio (SMS), sendgrid (email),
cloudflare (CDN and firewall), aws (hosting). The incident channel is #inc-live; boards are "Sorrel / web",
"Sorrel / api", "Sorrel / payments", "Sorrel / notifier"; logs are searched in sorrel-prod-*; people use the paging
tool, the metrics tool, the log search tool and the deploy tool. Severities: P1, P2, P3. A handover is finished when
the incoming on-call writes "taken" in #inc-live.
"""

DRAFT_RULES = """You write internal pages for the SRE team of Sorrel. Write ONE page in Markdown, plain and realistic,
the way a small, busy SRE team writes: specific, a little dry, short sections, bullets where they help, no marketing
tone, no summary of what the page is for. Length: {words} to {words_max} words; do not stop short.
{shape}

Start with exactly the header lines you are given, unchanged. Then write the body.

Hard rules:
- Use every fact you are given, with every number, name, code, config key and date exactly as written. Add no new
  facts: no new incidents, numbers, error codes, config keys, partner names or people. You may add connecting words,
  a one-line judgement from the author, and a routine sign-off.
- Keep the team's own words for things exactly as the facts give them; do not explain a term in other words and do not
  add a plain-language gloss.
- An error code (like ABC-1234) appears only where a fact puts it, written in passing inside a sentence. Never put an
  error code in a heading, a table header or the first line of a section.
- Never give rollback steps or rollback commands for any service. Never mention a tool called dtool. Mention Shipyard
  only if a fact does, and then only as the fact says, with no commands.
- No phone numbers, account ids, email addresses or URLs. Do not mention on-call pay, allowances or contracts.
- Do not copy alert rules or thresholds into tables, and do not write lists of 'for this alert, the first move is X'.
- Everything in the page happens on or before the page's date.

What the team works with:
""" + CONTEXT + "\nThe five actions on-call chooses from:\n"


SHAPE_HANDOVER = """Sections, in this order, with numbered '## ' headings in the house style ('## 1. Shift summary'):
shift summary (two or three sentences, the author's view of the week); what happened (each fact, with the author's
plain account of what was seen and done); a one-line-per-service status for web, api, payments and notifier (normal,
or pointing back to what happened; no new numbers); notes for the incoming on-call; sign-off."""
SHAPE_TEAM = """Sections with '## ' headings: a two-sentence intro on who keeps this page; one section per fact, each
told as the team learned it; a short 'when you see this on call' line where it fits (no new facts)."""


def header(spec):
    if spec["kind"] == "handover":
        d = spec["date"]
        first = f"Date: {d}" if int(md5(d), 16) % 2 else f"Last updated: {d} 10:00 JST"
        who = "Author" if int(md5(d + "a"), 16) % 2 else "Owner"
        return (f"# {spec['title']}\n\n{first}  \n{who}: {spec['author']}, outgoing on-call  \n"
                f"Incoming on-call: {spec['incoming']}  \n")
    return f"# {spec['title']}\n\nLast updated: {spec['date']}  \nOwner: {spec['owner']}  \n"


def draft(only=None, limit=None):
    from rules import RULES
    spec = json.load(open("library/SPEC-ep12.json"))
    pages = [p for p in spec["pages"] if not only or p["file"] in only][: int(limit) if limit else None]
    out_path = os.path.join(RUNS, f"{DAY}-a-draft.json")
    try:
        out = json.load(open(out_path))
    except FileNotFoundError:
        out = {"meta": {"what": "A: drafting calls for the new pages (library building, not measured)",
                        "spec_md5": file_md5("library/SPEC-ep12.json")}, "calls": []}

    def one(p):
        path = os.path.join(ROOT, p["file"])
        if os.path.exists(path):
            return None
        shape = SHAPE_HANDOVER if p["kind"] == "handover" else SHAPE_TEAM
        system = DRAFT_RULES.format(words=550, words_max=700, shape=shape) + RULES
        task = {k: p[k] for k in ("title", "kind", "date", "facts") if k in p}
        if p.get("note"):
            task["note"] = p["note"]
        user = ("Header lines (copy exactly):\n" + header(p) + "\nPage spec:\n" + json.dumps(task, indent=1, ensure_ascii=False))
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}]}
        rec = generate(body, "A-draft")
        rec["file"] = p["file"]
        if rec["http"] == 200 and rec.get("text"):
            text = re.sub(r"^```(?:markdown)?\n|\n```\s*$", "", rec["text"].strip())
            open(path, "w").write(text.strip() + "\n")
        print(f"  {p['file']:42} http {rec['http']} in {rec.get('prompt')} out {rec.get('out')} "
              f"${rec.get('cost_usd', 0):.4f}", flush=True)
        return rec

    with cf.ThreadPoolExecutor(4) as ex:
        for rec in ex.map(one, pages):
            if rec:
                with _lock:
                    out["calls"].append(rec)
                    save("a-draft", out)
    print(f"spent so far ${spent():.4f}")


# ---------------------------------------------------------------- A + Q: the frozen list

INDEX12 = "library/INDEX-ep12.json"
QFILE = "tickets/questions-ep12.json"
FREEZE = os.path.join(RUNS, f"{DAY}-a-freeze.json")


def ep12_pages():
    """lookup.pages() with lookup.INDEX swapped for INDEX-ep12.json: every page, in the list's order."""
    import lookup
    lookup.INDEX = json.load(open(INDEX12))
    return lookup.pages()


def freeze():
    import lookup
    rows = json.load(open("library/INDEX.json"))
    assert len(rows) == 75
    spec = json.load(open("library/SPEC-ep12.json"))
    new = []
    for p in sorted(spec["pages"], key=lambda p: (p["date"], p["file"])):
        text = open(p["file"]).read()
        title = re.match(r"# (.+)", text).group(1).strip()
        assert title == p["title"], (title, p["title"])
        new.append({"id": os.path.basename(p["file"])[:-3], "title": title, "updated": p["date"], "source": p["file"],
                    "tokens": count_tokens(text), "md5": md5(text)})
    json.dump(rows + new, open(INDEX12, "w"), indent=1, ensure_ascii=False)
    pages = ep12_pages()
    assert len(pages) == len(rows) + len(new), (len(pages), len(rows) + len(new))
    per_page = []
    for p in pages:
        per_page.append({"id": p["id"], "tokens": count_tokens(p["text"]), "embed_tokens": embed_count(p["text"]),
                         "md5": md5(p["text"]), "chars": len(p["text"])})
    listing = lookup.contents_list(pages)
    files = (["lookup.py", "rules.py", "runbooks/handbook.md", "library/INDEX.json", INDEX12, "library/SPEC-ep12.json",
              QFILE, "measure/ep12_spec.py"] + sorted(f"library/{f}" for f in os.listdir("library") if f.endswith(".md"))
             + sorted(f"pages/{f}" for f in os.listdir("pages") if f.endswith(".md")))
    md5s = {f: file_md5(f) for f in files}
    total = sum(x["tokens"] for x in per_page)
    out = {"frozen_utc": stamp(), "md5": md5s, "pages": per_page, "n_pages": len(pages), "n_new": len(new),
           "total_tokens_countTokens_page_by_page": total,
           "total_embed_tokens": sum(x["embed_tokens"] for x in per_page),
           "contents_list_tokens": count_tokens(listing), "contents_list_chars": len(listing),
           "contents_list_tokens_75": count_tokens(lookup.contents_list(pages[:75])),
           "new_pages_tokens": sum(x["tokens"] for x in per_page if x["id"] in {n["id"] for n in new}),
           "new_handover_tokens_min_max": [min(n["tokens"] for n in new if n["id"].startswith("handover")),
                                           max(n["tokens"] for n in new if n["id"].startswith("handover"))],
           "pages_over_embed_limit": [x["id"] for x in per_page if x["embed_tokens"] > 8192],
           "scan_pages_note": "pages/scan-*.md were 0 bytes in the working tree (EP11 camera before-state); restored "
                              "from runs/ep11/camera/pages-after-k2/ before the freeze (no model call)"}
    path = save("a-freeze", out)
    print(json.dumps({k: v for k, v in out.items() if k not in ("md5", "pages")}, indent=1))
    report_set(["A_library"], {"run": "nightshift/" + path, **{k: v for k, v in out.items() if k not in ("md5", "pages")},
                               "md5_INDEX-ep12.json": md5s[INDEX12], "md5_SPEC-ep12.json": md5s["library/SPEC-ep12.json"],
                               "error_codes": spec["error_codes"], "draft_run": "nightshift/runs/ep12/2026-10-11-a-draft.json",
                               "hand_fixes": ["team-payments-notes: cut the plain gloss 'double billing ... appointments'",
                                              "handover-2025-12-01: header said 'outgoing'; Priya is the incoming"]})
    q = json.load(open(QFILE))
    from collections import Counter
    report_set(["Q_questions"], {"file": "nightshift/" + QFILE, "md5": md5s[QFILE], "n": len(q["questions"]),
                                 "per_kind": Counter(x["kind"] for x in q["questions"]), "grading": q["grading"],
                                 "written": q["written"], "mix_is_designed": True})
    print("frozen ->", path)


def load_frozen():
    fz = json.load(open(FREEZE))
    for f, h in fz["md5"].items():
        if file_md5(f) != h:
            raise Stop(f"{f} changed since the freeze")
    pages = ep12_pages()
    by = {x["id"]: x for x in fz["pages"]}
    for p in pages:
        assert md5(p["text"]) == by[p["id"]]["md5"], p["id"]
        p["tokens"] = by[p["id"]]["tokens"]
        register(p["text"], p["tokens"], p["id"])
    return pages, json.load(open(QFILE))["questions"]


# ---------------------------------------------------------------- S + R: recall at 5 (embeddings only)

EMBED_CALLS = []


def instrumented_search():
    """search.py exactly as written, with its embed() wrapped: identical text is embedded once, every real call
    is recorded (md5 of the text, tokens from usageMetadata, wall time) and its cost added to spend.json."""
    import search
    real = search.embed
    memo = {}

    def embed(text):
        if text in memo:
            return memo[text]
        t0, w0 = stamp(), time.time()
        for attempt in range(4):
            try:
                v = real(text)
                break
            except urllib.error.HTTPError as e:
                if e.code == 402:
                    raise Stop("HTTP 402 on embedContent")
                if e.code not in (429, 500, 503) or attempt == 3:
                    raise
                time.sleep(10)
        u = search.used[-1]
        usd = u.get("promptTokenCount", 0) * PRICE_EMBED / 1e6
        add_spend(usd, "S-R-embed")
        EMBED_CALLS.append({"sent_utc": t0, "wall_s": round(time.time() - w0, 3), "text_md5": md5(text),
                            "text_start": text[:60], "usageMetadata": u, "cost_usd": usd, "dims": len(v)})
        memo[text] = v
        return v

    search.embed = embed
    return search


def ranks_of(ranked, answer_ids):
    ids = [p["id"] for p in ranked]
    return {a: (ids.index(a) + 1 if a in ids[:20] else None) for a in answer_ids}


def recall():
    pages, qs = load_frozen()
    search = instrumented_search()
    t0 = time.time()
    vecs = search.page_vectors(pages)
    split = [p["id"] for p in pages if len(vecs[p["id"]]) > 1]
    embed_pages_s = round(time.time() - t0, 1)
    page_calls = list(EMBED_CALLS)
    methods = {"keyword": search.keyword_search, "meaning": search.meaning_search, "both": search.both}
    rows = []
    for q in qs:
        answer = q["page"] if isinstance(q["page"], list) else ([q["page"]] if q["page"] else [])
        row = {"id": q["id"], "kind": q["kind"], "question": q["question"], "answer_pages": answer}
        for name, fn in methods.items():
            w0 = time.time()
            ranked = fn(q["question"], pages, len(pages))
            r = ranks_of(ranked, answer)
            top5 = [p["id"] for p in ranked[:5]]
            row[name] = {"top5": top5, "top20": [p["id"] for p in ranked[:20]], "answer_rank": r,
                         "found_any": any(v and v <= 5 for v in r.values()) if answer else None,
                         "found_all": all(v and v <= 5 for v in r.values()) if answer else None,
                         "listed": len(ranked), "wall_s": round(time.time() - w0, 3)}
        rows.append(row)
        print(f"  {q['id']:24} " + "  ".join(f"{m}:{row[m]['answer_rank']}" for m in methods), flush=True)
    summary = {}
    kinds = ["code", "other words", "hidden", "plain"]
    for m in methods:
        summary[m] = {}
        for k in kinds + ["all"]:
            sel = [r for r in rows if r["answer_pages"] and (k == "all" or r["kind"] == k)]
            summary[m][k] = {"found_any": sum(r[m]["found_any"] for r in sel), "of": len(sel),
                             "found_all_two_page": sum(r[m]["found_all"] for r in sel if len(r["answer_pages"]) > 1),
                             "two_page_of": sum(len(r["answer_pages"]) > 1 for r in sel)}
    flags = {"code_meaning_miss_keyword_find": [], "other_words_keyword_miss_meaning_find": []}
    for r in rows:
        if r["kind"] == "code" and not r["meaning"]["found_any"] and r["keyword"]["found_any"]:
            flags["code_meaning_miss_keyword_find"].append({k: r[k] if k in ("id", "question", "answer_pages") else
                {"answer_rank": r[k]["answer_rank"], "top5": r[k]["top5"]} for k in ("id", "question", "answer_pages", "keyword", "meaning")})
        if r["kind"] == "other words" and not r["keyword"]["found_any"] and r["meaning"]["found_any"]:
            flags["other_words_keyword_miss_meaning_find"].append({k: r[k] if k in ("id", "question", "answer_pages") else
                {"answer_rank": r[k]["answer_rank"], "top5": r[k]["top5"]} for k in ("id", "question", "answer_pages", "keyword", "meaning")})
    out = {"what": "R: recall at 5 for keyword_search, meaning_search, both (search.py as frozen), 40 questions; "
                   "not-in-pages questions are out of recall (their top 5 is listed)",
           "search_py_md5": file_md5("search.py"), "embed_model": "gemini-embedding-2",
           "page_embedding": {"calls": len(page_calls), "tokens": sum(c["usageMetadata"].get("promptTokenCount", 0) for c in page_calls),
                              "cost_usd": sum(c["cost_usd"] for c in page_calls), "wall_s": embed_pages_s,
                              "pages_split_into_pieces": split, "vectors_file": "search/vectors.json",
                              "vectors_md5": file_md5("search/vectors.json")},
           "question_embedding_calls": len(EMBED_CALLS) - len(page_calls),
           "cut_at_limit_variant": "not run: 0 of 127 pages is over the 8,192-token input limit (a-freeze "
                                   "pages_over_embed_limit = []), so cutting at the limit changes no page",
           "summary": summary, "flags": flags, "questions": rows, "embed_calls": EMBED_CALLS}
    path = save("r-recall", out)
    report_set(["R_recall"], {"run": "nightshift/" + path, "summary": summary, "flags": flags,
                              "page_embedding": out["page_embedding"], "cut_at_limit_variant": out["cut_at_limit_variant"]})
    print(json.dumps(summary, indent=1))
    print(json.dumps(flags, indent=1)[:4000])
    print("->", path, f"spent ${spent():.4f}")


# ---------------------------------------------------------------- grading (code side; hand checks go in a file)

NOT_SAY = ["do not say", "don't say", "does not say", "doesn't say", "do not mention", "does not mention",
           "doesn't mention", "don't mention", "do not contain", "does not contain", "doesn't contain", "not in the pages",
           "no information", "not listed", "do not include", "does not include", "doesn't include", "don't include",
           "not documented", "do not specify", "does not specify", "doesn't specify", "do not provide",
           "does not provide", "doesn't provide", "not mentioned", "not specified", "no record", "not found",
           "do not have", "don't have", "couldn't find", "could not find", "not available in the pages", "no mention",
           "nothing in the pages", "do not state", "does not state", "doesn't state", "not stated"]


def grade(q, answer):
    a = (answer or "").lower()
    says_not = any(w in a for w in NOT_SAY)
    if q["truth"] == ["NOT_IN_PAGES"]:
        return {"code": "said-not-in-pages" if says_not else "needs-hand", "truth_hit": None, "wrong_hit": [],
                "says_not_in_pages": says_not}
    hits = [any(alt.lower() in a for alt in g) for g in q["truth"]]
    wrong = [w for w in q["wrong"] if w.lower() in a]
    code = "right" if all(hits) and not wrong else ("said-not-in-pages" if says_not and not any(hits) else "wrong")
    return {"code": code, "truth_hit": hits, "wrong_hit": wrong, "says_not_in_pages": says_not}


def answer_pages(q):
    return q["page"] if isinstance(q["page"], list) else ([q["page"]] if q["page"] else [])


# ---------------------------------------------------------------- T: the titles alone (lookup.py's look-up)

_local = threading.local()


def recording_call(step):
    """stands in for lookup.call: same body, same thinking level, but every call is recorded"""
    def call(body):
        rec = generate(body, step)
        _local.calls.append(rec)
        if rec["http"] != 200 or not rec.get("content"):
            raise Stop(f"generateContent HTTP {rec['http']}: {(rec.get('error') or '')[:300]} {rec.get('finishReason')}")
        return rec["content"]
    return call


def run_questions(name, one, qs, workers=4):
    path = os.path.join(RUNS, f"{DAY}-{name}.json")
    out = {"what": name, "started_utc": stamp(), "questions": []}
    done = {}
    if os.path.exists(path):                      # resume: a question already answered is never asked again
        prev = json.load(open(path))
        out["started_utc"] = prev.get("started_utc", out["started_utc"])
        done = {r["id"]: r for r in prev.get("questions", []) if r.get("answer") is not None}
    todo = [q for q in qs if q["id"] not in done]
    if os.environ.get("ONLY"):
        todo = [q for q in todo if q["id"] in os.environ["ONLY"].split(",")]

    def wrap(q):
        _local.calls = []
        w0 = time.time()
        try:
            result = one(q)
            err = None
        except Stop as e:
            result, err = {"answer": None}, str(e)
            if "402" in err:
                raise
        rec = {"id": q["id"], "kind": q["kind"], "question": q["question"], "answer_pages": answer_pages(q),
               **result, "error": err, "wall_s": round(time.time() - w0, 2), "calls": _local.calls,
               "prompt_tokens": sum(c.get("prompt", 0) for c in _local.calls),
               "cached_tokens": sum(c.get("cached", 0) for c in _local.calls),
               "out_tokens": sum(c.get("out", 0) for c in _local.calls),
               "cost_usd": sum(c.get("cost_usd", 0) for c in _local.calls)}
        rec["grade"] = grade(q, rec.get("answer"))
        return rec

    with cf.ThreadPoolExecutor(workers) as ex:
        for rec in ex.map(wrap, todo):
            with _lock:
                done[rec["id"]] = rec
                out["questions"] = [done[q["id"]] for q in qs if q["id"] in done]
                json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
            print(f"  {rec['id']:24} {rec['grade']['code']:18} opened {rec.get('opened')} "
                  f"{rec['prompt_tokens']:>7,} in  ${rec['cost_usd']:.4f}  {rec['wall_s']} s", flush=True)
    out["finished_utc"] = stamp()
    json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
    print("->", os.path.relpath(path, ROOT), f"spent ${spent():.4f}")
    return out


def titles():
    import contextlib, io, lookup
    pages, qs = load_frozen()
    listing = lookup.contents_list(pages)
    register(listing, json.load(open(FREEZE))["contents_list_tokens"], "contents list (INDEX-ep12)")
    from rules import SYSTEM
    lookup.call = recording_call("T-titles")

    ids = {p["id"] for p in pages}

    def one(q):
        answer = lookup.look_it_up(q["question"], pages)
        opened = [fc["args"].get("id") for c in _local.calls for fc in c.get("function_calls", [])
                  if fc.get("name") == "read_page" and fc["args"].get("id") in ids][:4]   # lookup.py's count
        return {"answer": answer, "opened": opened,
                "opened_answer_page": any(o in answer_pages(q) for o in opened) if answer_pages(q) else None}

    out = run_questions("t-titles", one, qs)
    out["meta"] = {"index": INDEX12, "code": "lookup.look_it_up exactly, lookup.INDEX swapped, lookup.call wrapped to "
                   "record", "contents_list_tokens": json.load(open(FREEZE))["contents_list_tokens"]}
    save("t-titles", out)


# ---------------------------------------------------------------- E1: search, then answer

SEARCH_PAGES = {"name": "search_pages", "description": "Search the team's pages. Returns the 5 best matches: rank, id, "
                "title and the start of the page.",
                "parameters": {"type": "object", "properties": {
                    "query": {"type": "string", "description": "what to search for"}}, "required": ["query"]}}


def best_method():
    r = json.load(open(os.path.join(RUNS, f"{DAY}-r-recall.json")))["summary"]
    order = sorted(r, key=lambda m: (-r[m]["all"]["found_any"], ["keyword", "both", "meaning"].index(m)))
    return order[0], {m: r[m]["all"] for m in r}


def e1(shape):
    import lookup
    from rules import SYSTEM
    pages, qs = load_frozen()
    search = instrumented_search()
    method, table = best_method()
    find = {"keyword": search.keyword_search, "meaning": search.meaning_search, "both": search.both}[method]
    lookup.call = recording_call(f"E1-{shape}")
    by_id = {p["id"]: p for p in pages}

    def code_searches(q):
        top = find(q["question"], pages, 5)
        system = SYSTEM + "\nThe team's pages that matched the question follow.\n" + "".join(
            f"\n----- page: {p['title']} -----\n\n{p['text']}" for p in top)
        reply = lookup.call({"systemInstruction": {"parts": [{"text": system}]},
                             "contents": [{"role": "user", "parts": [{"text": lookup.ASK.format(q=q["question"])}]}]})
        answer = "".join(part.get("text", "") for part in reply["parts"] if not part.get("thought"))
        ids = [p["id"] for p in top]
        return {"answer": answer, "pages_in_call": ids, "opened": ids,
                "opened_answer_page": any(i in answer_pages(q) for i in ids) if answer_pages(q) else None}

    def model_searches(q):
        system = (SYSTEM + "\nTo find the team's pages, call search_pages with what to search for; it returns the 5 best "
                  "matches. To read a page, call read_page with its id. You may make up to 4 calls in all.")
        turns = [{"role": "user", "parts": [{"text": lookup.ASK.format(q=q["question"])}]}]
        used_calls, queries, opened, answer = 0, [], [], None
        while True:
            body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": turns,
                    "tools": [{"functionDeclarations": [SEARCH_PAGES, lookup.READ_PAGE]}]}
            if used_calls >= 4:
                body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
            reply = lookup.call(body)
            asks = [part["functionCall"] for part in reply["parts"] if "functionCall" in part]
            if not asks:
                answer = "".join(part.get("text", "") for part in reply["parts"] if not part.get("thought"))
                break
            turns.append(reply)
            answers = []
            for ask in asks:
                if used_calls >= 4:
                    res = {"error": "call limit reached: 4 calls. Answer from what you have."}
                elif ask["name"] == "search_pages":
                    used_calls += 1
                    hits = find(ask["args"].get("query", ""), pages, 5)
                    queries.append({"query": ask["args"].get("query", ""), "results": [p["id"] for p in hits]})
                    res = {"results": [{"rank": i + 1, "id": p["id"], "title": p["title"],
                                        "start": p["text"][:200]} for i, p in enumerate(hits)]}
                elif ask["name"] == "read_page" and ask["args"].get("id") in by_id:
                    used_calls += 1
                    opened.append(ask["args"]["id"])
                    res = {k: by_id[ask["args"]["id"]][k] for k in ("id", "title", "text")}
                else:
                    res = {"error": f"no page with id {ask['args'].get('id')!r}" if ask["name"] == "read_page"
                           else f"no function called {ask['name']}"}
                answers.append({"functionResponse": {"name": ask["name"], "response": res,
                                                     **({"id": ask["id"]} if "id" in ask else {})}})
            turns.append({"role": "user", "parts": answers})
        return {"answer": answer, "queries": queries, "opened": opened,
                "opened_answer_page": any(i in answer_pages(q) for i in opened) if answer_pages(q) else None,
                "search_results_held_answer_page": any(i in answer_pages(q) for x in queries for i in x["results"])
                if answer_pages(q) else None}

    out = run_questions(f"e1-{shape}", code_searches if shape == "code" else model_searches, qs)
    out["meta"] = {"method": method, "chosen_from": table, "search_py_md5": file_md5("search.py"),
                   "embed_calls": EMBED_CALLS}
    save(f"e1-{shape}", out)


# ---------------------------------------------------------------- E2: carry it all, explicit cache

def e2():
    import lookup
    from rules import SYSTEM
    pages, qs = load_frozen()
    hb = open("runbooks/handbook.md").read()
    others = [p for p in pages if not p["id"].startswith("handbook-")]
    system = hb + "\n\nThe team's other pages follow.\n" + "".join(
        f"\n----- page: {p['title']} -----\n\n{p['text']}" for p in others)            # lookup.carry's text
    n = count_tokens(system)
    register(system, n, "carry-all systemInstruction (lookup.carry's text on INDEX-ep12)")
    left = CAP - spent()
    run_qs = qs if left >= 1.20 else [q for q in qs if q["kind"] in ("code", "other words")]
    ttl = 900
    create_body = {"model": f"models/{MODEL}", "ttl": f"{ttl}s", "systemInstruction": {"parts": [{"text": system}]}}
    t0 = stamp()
    st, r, err, secs = http("POST", "cachedContents", create_body)
    if st != 200:
        raise Stop(f"cache create HTTP {st}: {err}")
    cached_n = r.get("usageMetadata", {}).get("totalTokenCount", n)
    create_usd = cached_n * PRICE_IN / 1e6                     # counted at the full input rate (docs silent): upper bound
    storage_usd = cached_n * PRICE_STORAGE_H * ttl / 3600 / 1e6  # the whole TTL, even if deleted early
    add_spend(create_usd, "E2-cache-create")
    add_spend(storage_usd, "E2-cache-storage")
    cache = {"name": r["name"], "create_http": st, "create_wall_s": secs, "created_utc": t0, "ttl_s": ttl,
             "create_response": r, "system_tokens_countTokens": n, "system_md5": md5(system),
             "create_cost_usd_counted": create_usd, "storage_cost_usd_counted": storage_usd,
             "billing_note": "docs: billed on cached token count when used + storage for the TTL; the create call "
                             "itself is not priced on the page, so it is counted here at the full input rate"}
    print("cache", r["name"], cached_n, "tokens", flush=True)
    lookup.call = recording_call("E2-carry")

    def one(q):
        reply = lookup.call({"cachedContent": r["name"],
                             "contents": [{"role": "user", "parts": [{"text": lookup.ASK.format(q=q["question"])}]}]})
        return {"answer": "".join(part.get("text", "") for part in reply["parts"] if not part.get("thought")),
                "opened": ["(every page)"], "opened_answer_page": True if answer_pages(q) else None}

    try:
        out = run_questions("e2-carry", one, run_qs)
    finally:
        st2, r2, err2, s2 = http("DELETE", r["name"])
        cache["deleted_http"], cache["deleted_utc"] = st2, stamp()
    out["meta"] = {"cache": cache, "questions_run": len(run_qs), "budget_left_at_start": left,
                   "explicit_cache": True}
    save("e2-carry", out)


# ---------------------------------------------------------------- the tables, hand grades applied

def final_grade(rec, hand):
    o = hand.get("overrides", {}).get(rec["id"])
    if o:
        return o["hand"]
    c = rec["grade"]["code"]
    return {"right": "right", "wrong": "wrong", "said-not-in-pages": "said-not", "needs-hand": "needs-hand"}[c]


def table(name):
    d = json.load(open(os.path.join(RUNS, f"{DAY}-{name}.json")))
    hand = json.load(open(os.path.join(RUNS, f"{DAY}-{name}-hand-grades.json")))
    kinds = ["code", "other words", "hidden", "plain", "not in pages"]
    rows = {}
    for k in kinds + ["all"]:
        sel = [r for r in d["questions"] if k == "all" or r["kind"] == k]
        if not sel:
            continue
        g = [final_grade(r, hand) for r in sel]
        ans = [r for r in sel if r["answer_pages"]]
        rows[k] = {"n": len(sel), "right": g.count("right"), "partial": g.count("partial"),
                   "said_not": g.count("said-not"), "wrong": g.count("wrong"),
                   "opened_answer_page": sum(bool(r.get("opened_answer_page")) for r in ans), "answerable": len(ans),
                   "prompt_tokens_per_q": round(sum(r["prompt_tokens"] for r in sel) / len(sel)),
                   "cost_usd_per_q": round(sum(r["cost_usd"] for r in sel) / len(sel), 5),
                   "median_wall_s": round(statistics.median(r["wall_s"] for r in sel), 2),
                   "calls": sum(len(r["calls"]) for r in sel)}
    per_q = [{"id": r["id"], "kind": r["kind"], "grade": final_grade(r, hand), "code_grade": r["grade"]["code"],
              "opened": r.get("opened"), "queries": [x["query"] for x in r.get("queries", [])] or None,
              "prompt_tokens": r["prompt_tokens"], "cost_usd": round(r["cost_usd"], 5), "wall_s": r["wall_s"]}
             for r in d["questions"]]
    return {"run": f"nightshift/runs/ep12/{DAY}-{name}.json",
            "hand_grades": f"nightshift/runs/ep12/{DAY}-{name}-hand-grades.json",
            "hand_overrides": hand.get("overrides", {}), "by_kind": rows, "questions": per_q}


def tables():
    report_set(["T_titles"], table("t-titles"))
    e1c, e1m = table("e1-code"), table("e1-model")
    meta = json.load(open(os.path.join(RUNS, f"{DAY}-e1-code.json")))["meta"]
    report_set(["E1_search_then_answer"], {"method": meta["method"], "chosen_from_R_found_any": meta["chosen_from"],
                                           "code_searches": e1c, "model_searches": e1m})
    e2 = table("e2-carry")
    e2["cache"] = {k: v for k, v in json.load(open(os.path.join(RUNS, f"{DAY}-e2-carry.json")))["meta"]["cache"].items()
                   if k != "create_response"}
    e2["pilot_cache"] = "nightshift/runs/ep12/2026-10-11-e2-pilot-cache.json (the 1-question pilot made its own cache)"
    report_set(["E2_carry_all"], e2)
    sp = json.load(open(SPENT_FILE))
    report_set(["spend"], {"total_usd": round(sp["usd"], 4), "cap_usd": CAP, "by_step": {k: round(v, 4) for k, v in sp["by_step"].items()},
                           "file": "nightshift/runs/ep12/spend.json"})
    for name, t in (("T", report_get("T_titles")), ("E1 code", e1c), ("E1 model", e1m), ("E2", e2)):
        t = t["by_kind"] if "by_kind" in t else t
        print(name)
        for k, v in t.items():
            print(f"  {k:13} right {v['right']:2} partial {v['partial']} said-not {v['said_not']:2} wrong {v['wrong']:2} "
                  f"opened {v['opened_answer_page']}/{v['answerable']}  {v['prompt_tokens_per_q']:>7,} tok  "
                  f"${v['cost_usd_per_q']:.4f}  {v['median_wall_s']} s")


def report_get(key):
    return json.load(open(REPORT))[key]


if __name__ == "__main__":
    cmd = sys.argv[1]
    try:
        if cmd == "m0-list":
            m0_list()
        elif cmd == "a-draft":
            draft(only=[a for a in sys.argv[2:] if a.endswith(".md")] or None,
                  limit=next((a[8:] for a in sys.argv[2:] if a.startswith("--limit=")), None))
        elif cmd == "a-freeze":
            freeze()
        elif cmd == "r":
            recall()
        elif cmd == "t":
            titles()
        elif cmd == "e1":
            e1(sys.argv[2])
        elif cmd == "e2":
            e2()
        elif cmd == "tables":
            tables()
        elif cmd == "m0-long":
            m0_long()
        elif cmd == "m0-get":
            m0_get(sys.argv[2])
        else:
            raise SystemExit(f"unknown command {cmd}")
    except Stop as e:
        print("STOP:", e)
        sys.exit(2)
