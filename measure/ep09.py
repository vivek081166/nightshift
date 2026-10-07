"""EP09 measurement harness, not episode code: prompt caching on the thirty alerts with the long handbook.

    python3 measure/ep09.py count                  # countTokens on the handbook (free)
    python3 measure/ep09.py m1                     # baseline: SYSTEM + handbook, alert last, 30 one at a time
    python3 measure/ep09.py m2 time|alert|fix TAG  # the changing line at the top, 10 alerts
    python3 measure/ep09.py m3 cold|warm|serial TAG
    python3 measure/ep09.py m4 plain | m4 cut N TAG
    python3 measure/ep09.py m5                     # explicit cachedContents
    python3 measure/ep09.py m6 bust|fixed|plain [TAG]
Call style as triage.py: raw HTTP, gemini-3.8-flash, thinking low. Run files keep the request minus the
handbook body (md5 + token count kept), the full response with every usageMetadata field, and wall time.
"""
import concurrent.futures as cf, hashlib, json, os, re, statistics, sys, threading, time, urllib.error, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rules import SYSTEM, ACTIONS                 # noqa: E402
from sorrel.oncall import SERVICES                # noqa: E402

RUNS = os.path.join(ROOT, "runs", "ep09")
DAY = "2026-10-05"
MODEL = "gemini-3.8-flash"
BASE = "https://generativelanguage.googleapis.com/v1beta"
PRICE_IN, PRICE_OUT = 0.75, 3.75     # triage.py, dollars per million; thinking billed as out
PRICE_CACHED = 0.075               # M0: pricing page, Standard paid tier, through 2026-12-31
PRICE_STORAGE_H = 0.50             # M0: per 1M tokens per hour
CAP = 3.80                           # stop before the $4 cap
SPENT_FILE = os.path.join(RUNS, f"{DAY}-spend.json")
HANDBOOK_PATH = os.path.join(RUNS, f"{DAY}-handbook-frozen.md")   # the measured text (md5 a837a135); runbooks/handbook.md is the camera copy, rules on top
CASES = json.load(open(os.path.join(ROOT, "tickets", "incidents.json")))
ASK = "Reply in JSON with the severity, the service, the first move, and why."
SCHEMA = {"type": "object", "properties": {
    "severity": {"type": "string", "enum": ["P1", "P2", "P3"]},
    "service": {"type": "string", "enum": SERVICES},
    "first_move": {"type": "string", "enum": ACTIONS},
    "reason": {"type": "string"}},
    "required": ["severity", "service", "first_move", "reason"]}

if not os.environ.get("GEMINI_API_KEY"):          # the key lives in .env (gitignored); never printed
    for line in open(os.path.join(ROOT, ".env")):
        if line.startswith("GEMINI_API_KEY="):
            os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")

_lock = threading.Lock()


class Stop(Exception):
    pass


def handbook(tag=None):
    text = open(HANDBOOK_PATH).read()
    if tag:
        first, rest = text.split("\n", 1)
        assert first.startswith("Revision "), first
        text = f"Revision {tag}\n" + rest
    return text


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()


def spent():
    try:
        return json.load(open(SPENT_FILE))["usd"]
    except FileNotFoundError:
        return 0.0


def add_spend(usd):
    with _lock:
        total = spent() + usd
        json.dump({"usd": total, "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                  open(SPENT_FILE, "w"))
        return total


def cost(u):
    """Uncached prompt at PRICE_IN, cached at PRICE_CACHED, output incl. thinking at PRICE_OUT."""
    p, c = u.get("promptTokenCount", 0), u.get("cachedContentTokenCount", 0)
    n_out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    return ((p - c) * PRICE_IN + c * PRICE_CACHED + n_out * PRICE_OUT) / 1e6


def http(method, path, body=None):
    url = f"{BASE}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                                             "content-type": "application/json"}, method=method)
    t0 = time.time()
    try:
        raw = urllib.request.urlopen(req, timeout=300).read().decode()
        status, err = 200, None
        r = json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        status, err, r = e.code, e.read().decode(errors="replace"), None
    if status == 402:
        raise Stop(f"HTTP 402: {err}")
    return status, r, err, round(time.time() - t0, 3)


def redact(obj, hb_text, hb_meta):
    """Replace the handbook body inside a logged request with its md5 + token count."""
    s = json.dumps(obj)
    if hb_text:
        s = s.replace(json.dumps(hb_text)[1:-1], f"<handbook omitted: {hb_meta}>")
    return json.loads(s)


def generate(system_text, user_text, hb_text=None, hb_meta=None, schema=False, cached=None, extra_parts=None):
    """One generateContent call. Returns a record with the full response and wall time."""
    cfg = {"thinkingConfig": {"thinkingLevel": "low"}}
    if schema:
        cfg["responseMimeType"] = "application/json"
        cfg["responseSchema"] = SCHEMA
    body = {"contents": [{"role": "user", "parts": [{"text": user_text}]}], "generationConfig": cfg}
    if system_text is not None:
        body["systemInstruction"] = {"parts": [{"text": system_text}]}
    if cached:
        body["cachedContent"] = cached
    retries = []
    while True:
        stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        status, r, err, secs = http("POST", f"models/{MODEL}:generateContent", body)
        if status in (429, 500, 503) and len(retries) < 4:
            retries.append({"why": f"HTTP {status}", "at": stamp, "body": (err or "")[:500]})
            time.sleep(20 if status == 429 else 5)
            continue
        break
    rec = {"request": redact(body, hb_text, hb_meta), "http": status, "sent_utc": stamp, "wall_s": secs,
           "retries": retries, "error": err, "response": r}
    if r is not None:
        u = r.get("usageMetadata", {})
        cand = (r.get("candidates") or [{}])[0]
        rec["text"] = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", [])
                              if not p.get("thought"))
        rec["prompt"] = u.get("promptTokenCount", 0)
        rec["cached"] = u.get("cachedContentTokenCount", 0)
        rec["cost_usd"] = cost(u)
        total = add_spend(rec["cost_usd"])
        if total > CAP:
            save_partial = rec
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


REPORT = os.path.expanduser("~/Projects/vivek-ai/content/ai-engineering-course/qc/ep09/measure/report.json")
_meta_cache = {}


def hb_meta(text):
    key = md5(text)
    if key not in _meta_cache:
        _meta_cache[key] = f"md5 {key}, {count_tokens(text)} tokens by countTokens"
    return _meta_cache[key]


def report_set(path, value):
    with _lock:
        r = json.load(open(REPORT))
        node = r
        for k in path[:-1]:
            node = node.setdefault(k, {})
        node[path[-1]] = value
        r["spend_usd_so_far"] = round(spent(), 6)
        json.dump(r, open(REPORT, "w"), indent=1, ensure_ascii=False)


def user_msg(alert):
    return f"Alert:\n{alert}\n{ASK}"


def now_hms():
    return datetime.now().strftime("%H:%M:%S")


def score(text, want):
    try:
        t = json.loads(text)
        return t.get("first_move") == want, t.get("first_move")
    except Exception:
        return False, None


def summarize(calls):
    ok = [c for c in calls if c.get("http") == 200]
    hits = [c for c in ok if c["cached"] > 0]
    miss = [c for c in ok if c["cached"] == 0]
    med = lambda xs: round(statistics.median(xs), 3) if xs else None
    return {
        "calls": len(calls), "http_200": len(ok), "hits": len(hits),
        "first_hit_call": next((i + 1 for i, c in enumerate(ok) if c["cached"] > 0), None),
        "cached_share_on_hits": sorted({round(c["cached"] / c["prompt"], 4) for c in hits}),
        "cached_counts_on_hits": sorted({c["cached"] for c in hits}),
        "prompt_tokens_range": [min(c["prompt"] for c in ok), max(c["prompt"] for c in ok)] if ok else None,
        "median_wall_s_hit": med([c["wall_s"] for c in hits]), "median_wall_s_miss": med([c["wall_s"] for c in miss]),
        "prompt_billed_full": sum(c["prompt"] - c["cached"] for c in ok), "cached_tokens": sum(c["cached"] for c in ok),
        "cost_usd": round(sum(c.get("cost_usd", 0) for c in ok), 6),
        "per_call": [[i + 1, c.get("id"), c["prompt"], c["cached"], c["wall_s"], round(c.get("cost_usd", 0), 6)]
                     for i, c in enumerate(ok)],
    }


def run_serial(name, jobs, meta):
    """jobs: list of dicts {id, build: () -> kwargs for generate}. One at a time; saves after each call."""
    out = {"meta": meta, "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "calls": []}
    t0 = time.time()
    for j in jobs:
        kw = j["build"]()
        rec = generate(**kw)
        rec["id"] = j["id"]
        out["calls"].append(rec)
        out["wall_total_s"] = round(time.time() - t0, 2)
        path = save(name, out)
        print(f"  {j['id']:28} prompt {rec.get('prompt')} cached {rec.get('cached')} {rec['wall_s']} s", flush=True)
    return path, out


def run_parallel(name, jobs, meta, workers=30):
    out = {"meta": meta, "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "calls": []}
    t0 = time.time()
    built = [(j["id"], j["build"]()) for j in jobs]
    def one(item):
        rec = generate(**item[1]); rec["id"] = item[0]; return rec
    with cf.ThreadPoolExecutor(workers) as ex:
        out["calls"] = list(ex.map(one, built))
    out["wall_total_s"] = round(time.time() - t0, 2)
    return save(name, out), out


def std_job(case, tag, schema=False, hb_text=None):
    hb = hb_text if hb_text is not None else handbook(tag)
    return {"id": case["id"], "build": lambda: dict(system_text=SYSTEM + "\n" + hb, user_text=user_msg(case["alert"]),
                                                     hb_text=hb, hb_meta=hb_meta(hb), schema=schema)}


def layout_meta(tag, extra=None):
    hb = handbook(tag)
    m = {"revision_tag": f"Revision {tag}" if tag else "Revision 2026-10-05a", "handbook": hb_meta(hb),
         "systemInstruction": "rules.SYSTEM + '\\n' + handbook", "contents": "Alert:\\n<alert>\\n" + ASK,
         "mode": "triage.py prompt mode (no JSON mode)"}
    m.update(extra or {})
    return m


def m1():
    jobs = [std_job(c, None) for c in CASES]
    path, out = run_serial("m1-baseline", jobs, layout_meta(None, {"order": "30 alerts in incidents.json order, serial"}))
    report_set(["M1_baseline"], {"run": path, **summarize(out["calls"])})


def m2(variant, tag):
    hb = handbook(tag); meta_hb = hb_meta(hb); cases = CASES[:10]
    if variant == "time":
        mk = lambda c: dict(system_text=f"It is now {now_hms()}.\n" + SYSTEM + "\n" + hb, user_text=user_msg(c["alert"]),
                            hb_text=hb, hb_meta=meta_hb)
        lay = "systemInstruction = 'It is now <HH:MM:SS>.' (local clock at send) + '\\n' + SYSTEM + '\\n' + handbook; contents = alert + ASK"
    elif variant == "alert":
        mk = lambda c: dict(system_text=f"Alert:\n{c['alert']}\n\n" + SYSTEM + "\n" + hb, user_text=ASK,
                            hb_text=hb, hb_meta=meta_hb)
        lay = "systemInstruction = 'Alert:\\n<alert>\\n\\n' + SYSTEM + '\\n' + handbook; contents = ASK only"
    elif variant == "fix":
        mk = lambda c: dict(system_text=SYSTEM + "\n" + hb, user_text=user_msg(c["alert"]) + f"\nIt is now {now_hms()}.",
                            hb_text=hb, hb_meta=meta_hb)
        lay = "systemInstruction = SYSTEM + '\\n' + handbook; contents = alert + ASK + '\\nIt is now <HH:MM:SS>.'"
    jobs = [{"id": c["id"], "build": (lambda c=c: mk(c))} for c in cases]
    meta = {"variant": variant, "revision_tag": f"Revision {tag}", "handbook": meta_hb, "layout": lay,
            "order": "first 10 alerts, serial", "mode": "triage.py prompt mode"}
    path, out = run_serial(f"m2-{variant}", jobs, meta)
    report_set(["M2_changing_line", variant], {"run": path, "revision_tag": f"Revision {tag}", "layout": lay,
                                              **summarize(out["calls"])})


def m3(variant, tag):
    jobs = [std_job(c, tag) for c in CASES]
    meta = layout_meta(tag, {"variant": variant})
    if variant == "cold":
        meta["how"] = "all 30 submitted at once, ThreadPoolExecutor(30), nothing sent with this tag before"
        path, out = run_parallel("m3-burst-cold", jobs, meta)
    elif variant == "warm":
        meta["how"] = "one warm-up call (alert 1), waited for it, then all 30 at once, ThreadPoolExecutor(30)"
        warm = generate(**std_job(CASES[0], tag)["build"]()); warm["id"] = "WARMUP " + CASES[0]["id"]
        time.sleep(0)   # no extra wait beyond the warm-up returning
        path, out = run_parallel("m3-burst-warm", jobs, meta)
        out["warmup"] = warm; save("m3-burst-warm", out)
    elif variant == "serial":
        meta["how"] = "one at a time, each sent as soon as the previous returned, no sleep"
        path, out = run_serial("m3-serial", jobs, meta)
    s = summarize(out["calls"])
    sent = sorted(out["calls"], key=lambda c: c["sent_utc"])
    s["sent_utc_span"] = [sent[0]["sent_utc"], sent[-1]["sent_utc"]]
    if variant == "warm":
        s["warmup"] = {"prompt": out["warmup"].get("prompt"), "cached": out["warmup"].get("cached"),
                       "wall_s": out["warmup"]["wall_s"], "cost_usd": round(out["warmup"].get("cost_usd", 0), 6)}
    report_set(["M3_burst", variant], {"run": path, "revision_tag": f"Revision {tag}", **s})


def cut_handbook(target, tag):
    """Largest prefix ending at a section boundary whose countTokens is closest to target."""
    hb = handbook(tag)
    bounds = [m.start() for m in re.finditer(r"\n#{2,3} ", hb)] + [len(hb)]
    best = None
    for b in bounds:
        if b < target * 2.5 or b > target * 6:
            continue
        n = count_tokens(hb[:b])
        if best is None or abs(n - target) < abs(best[1] - target):
            best = (b, n)
    return hb[:best[0]].rstrip() + "\n", best[1]


def m4_plain():
    jobs = []
    for c in CASES[:3]:
        for k in (1, 2):
            jobs.append({"id": f"{c['id']}#{k}", "build": (lambda c=c: dict(system_text=SYSTEM, user_text=user_msg(c["alert"])))})
    meta = {"layout": "systemInstruction = rules.SYSTEM only (no handbook); each of 3 alerts sent twice in a row",
            "SYSTEM_tokens_by_countTokens": count_tokens(SYSTEM)}
    path, out = run_serial("m4-plain", jobs, meta)
    report_set(["M4_size_floor", "plain_SYSTEM"], {"run": path, "SYSTEM_tokens": meta["SYSTEM_tokens_by_countTokens"],
                                                   **summarize(out["calls"])})


def m4_cut(target, tag):
    cut, n = cut_handbook(target, tag)
    jobs = [std_job(c, tag, hb_text=cut) for c in CASES[:3]]
    meta = {"target_tokens": target, "revision_tag": f"Revision {tag}", "handbook_cut": hb_meta(cut),
            "cut_tokens": n, "cut_ends_before": cut.rstrip().splitlines()[-1][:80],
            "layout": "systemInstruction = SYSTEM + '\\n' + handbook cut at a section boundary; 3 alerts in a row"}
    path, out = run_serial(f"m4-cut-{target}", jobs, meta)
    report_set(["M4_size_floor", f"cut_{target}"], {"run": path, "revision_tag": f"Revision {tag}", "cut_tokens": n,
                                                    **summarize(out["calls"])})


def m5(tag):
    hb = handbook(tag); meta_hb = hb_meta(hb)
    res = {"revision_tag": f"Revision {tag}", "handbook": meta_hb}
    body = {"model": f"models/{MODEL}", "systemInstruction": {"parts": [{"text": SYSTEM + "\n" + hb}]}, "ttl": "300s"}
    stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    status, r, err, secs = http("POST", "cachedContents", body)
    create = {"request": redact(body, hb, meta_hb), "http": status, "sent_utc": stamp, "wall_s": secs, "response": r, "error": err}
    out = {"meta": res, "create": create, "calls": []}
    path = save("m5-explicit", out)
    if status != 200:
        report_set(["M5_explicit"], {"run": path, "create_http": status, "create_error": err})
        return
    name = r["name"]; expire = r["expireTime"]
    cu = r.get("usageMetadata", {})
    create_cost = cu.get("totalTokenCount", 0) * PRICE_IN / 1e6   # docs silent; counted at the input rate, conservative
    add_spend(create_cost)
    for c in CASES:
        rec = generate(system_text=None, user_text=user_msg(c["alert"]), cached=name)
        rec["id"] = c["id"]; out["calls"].append(rec); save("m5-explicit", out)
        print(f"  {c['id']:28} http {rec['http']} prompt {rec.get('prompt')} cached {rec.get('cached')} {rec['wall_s']} s", flush=True)
    s = summarize(out["calls"])
    res.update({"run": path, "cache_name_shape": "cachedContents/<id>", "create_http": status,
                "create_usageMetadata": cu, "createTime": r.get("createTime"), "expireTime": expire,
                "create_cost_counted_usd": round(create_cost, 6), **s,
                "non_200_calls": [[c["id"], c["http"], (c["error"] or "")[:300]] for c in out["calls"] if c["http"] != 200]})
    report_set(["M5_explicit"], res)
    exp = datetime.fromisoformat(expire.replace("Z", "+00:00"))
    wait = (exp - datetime.now(timezone.utc)).total_seconds() + 20
    print(f"  waiting {wait:.0f} s past expireTime", flush=True)
    if wait > 0:
        time.sleep(wait)
    st_get, r_get, err_get, _ = http("GET", name)
    after = generate(system_text=None, user_text=user_msg(CASES[0]["alert"]), cached=name)
    after["id"] = CASES[0]["id"] + " (after expireTime)"
    out["after_expiry_get"] = {"http": st_get, "response": r_get, "error": err_get,
                               "at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    out["after_expiry_call"] = after
    st_del, r_del, err_del, _ = http("DELETE", name)
    out["delete"] = {"http": st_del, "response": r_del, "error": err_del}
    save("m5-explicit", out)
    n_cached = cu.get("totalTokenCount", 0)
    storage = n_cached * PRICE_STORAGE_H / 1e6 * 300 / 3600
    add_spend(storage)
    res.update({"after_expiry_call": {"sent_utc": after["sent_utc"], "http": after["http"], "error_body": after["error"],
                                      "retries": after["retries"]},
                "after_expiry_get": {"http": st_get, "error_body": err_get},
                "delete": {"http": st_del, "error_body": err_del},
                "storage_cost_usd": storage,
                "storage_arithmetic": f"{n_cached} tokens x $0.50 / 1M / hour x 300 s / 3600 s = ${storage:.8f}"})
    report_set(["M5_explicit"], res)


def m5_min():
    """Extra: an explicit cache of plain SYSTEM, far under 4,096: the exact refusal."""
    body = {"model": f"models/{MODEL}", "systemInstruction": {"parts": [{"text": SYSTEM}]}, "ttl": "300s"}
    status, r, err, secs = http("POST", "cachedContents", body)
    rec = {"request": body, "http": status, "wall_s": secs, "response": r, "error": err,
           "SYSTEM_tokens": count_tokens(SYSTEM)}
    if status == 200:
        rec["delete"] = http("DELETE", r["name"])[:3]
    path = save("m5-explicit-small", rec)
    report_set(["M5_explicit", "small_SYSTEM_create"], {"run": path, "http": status, "error_body": err,
                                                        "SYSTEM_tokens": rec["SYSTEM_tokens"]})


def m6(variant, tag=None):
    jobs = []
    for i, c in enumerate(CASES):
        if variant == "bust":
            t = f"2026-10-05-m6a-{i + 1:02d}"
            jobs.append(std_job(c, t, schema=True))
        elif variant == "fixed":
            jobs.append(std_job(c, tag, schema=True))
        elif variant == "plain":
            jobs.append({"id": c["id"], "build": (lambda c=c: dict(system_text=SYSTEM, user_text=user_msg(c["alert"]), schema=True))})
    meta = {"variant": variant, "mode": "triage.py schema mode (responseMimeType + SCHEMA)",
            "revision_tag": {"bust": "Revision 2026-10-05-m6a-NN, a different one per call",
                             "fixed": f"Revision {tag}", "plain": "no handbook"}[variant],
            "systemInstruction": "rules.SYSTEM only" if variant == "plain" else "rules.SYSTEM + '\\n' + handbook"}
    path, out = run_serial(f"m6-{variant}", jobs, meta)
    want = {c["id"]: c["want"] for c in CASES}
    right, misses = 0, []
    for rec in out["calls"]:
        ok, got = score(rec.get("text", ""), want[rec["id"]])
        right += ok
        if not ok:
            misses.append([rec["id"], want[rec["id"]], got])
    s = summarize(out["calls"])
    s.pop("per_call") if variant == "plain" else None
    report_set(["M6_module_close", variant], {"run": path, "revision_tag": meta["revision_tag"], "first_move_right": right,
                                              "of": len(CASES), "misses": misses, **s})


def m4_ext(target, tag, n):
    """Extra: the same cut, n calls in a row (cycling the alerts), because 3 calls cannot separate 'too small' from 'unlucky'."""
    cut, ntok = cut_handbook(target, tag)
    jobs = [std_job(CASES[i % 30], tag, hb_text=cut) for i in range(n)]
    meta = {"extra": True, "target_tokens": target, "revision_tag": f"Revision {tag}", "handbook_cut": hb_meta(cut),
            "cut_tokens": ntok, "layout": "systemInstruction = SYSTEM + '\\n' + handbook cut; n alerts in a row"}
    path, out = run_serial(f"m4-ext-{target}", jobs, meta)
    report_set(["M4_size_floor", f"EXTRA_cut_{target}_x{n}"], {"run": path, "revision_tag": f"Revision {tag}",
                                                               "cut_tokens": ntok, **summarize(out["calls"])})


def m4_explicit(target, tag):
    """Extra: does an explicit cache of SYSTEM + a cut handbook get created? (floor in the error vs the docs' 4,096)"""
    cut, ntok = cut_handbook(target, tag)
    body = {"model": f"models/{MODEL}", "systemInstruction": {"parts": [{"text": SYSTEM + "\n" + cut}]}, "ttl": "60s"}
    status, r, err, secs = http("POST", "cachedContents", body)
    rec = {"request": redact(body, cut, hb_meta(cut)), "http": status, "response": r, "error": err, "cut_tokens": ntok}
    if status == 200:
        add_spend(r.get("usageMetadata", {}).get("totalTokenCount", 0) * PRICE_IN / 1e6)
        d = http("DELETE", r["name"]); rec["delete"] = {"http": d[0], "error": d[2]}
    path = save(f"m4-explicit-{target}", rec)
    report_set(["M4_size_floor", f"EXTRA_explicit_create_{target}"], {"run": path, "http": status, "cut_tokens": ntok,
               "usageMetadata": (r or {}).get("usageMetadata"), "error_body": err})


def m2_fix_ext(tag):
    """Extra: fix, alerts 11-30, continuing m2-fix with the same tag."""
    hb = handbook(tag); meta_hb = hb_meta(hb)
    mk = lambda c: dict(system_text=SYSTEM + "\n" + hb, user_text=user_msg(c["alert"]) + f"\nIt is now {now_hms()}.",
                        hb_text=hb, hb_meta=meta_hb)
    jobs = [{"id": c["id"], "build": (lambda c=c: mk(c))} for c in CASES[10:]]
    meta = {"extra": True, "variant": "fix", "revision_tag": f"Revision {tag}", "handbook": meta_hb,
            "order": "alerts 11-30, serial, continuing m2-fix"}
    path, out = run_serial("m2-fix-ext", jobs, meta)
    first = json.load(open(os.path.join(RUNS, f"{DAY}-m2-fix.json")))["calls"]
    report_set(["M2_changing_line", "EXTRA_fix_30"], {"runs": ["runs/ep09/2026-10-05-m2-fix.json", path],
                                                     **summarize(first + out["calls"])})


def m2_time_ext(tag):
    """Extra: time first, alerts 11-30, so the comparison with M1 is 30 against 30."""
    hb = handbook(tag); meta_hb = hb_meta(hb)
    mk = lambda c: dict(system_text=f"It is now {now_hms()}.\n" + SYSTEM + "\n" + hb, user_text=user_msg(c["alert"]),
                        hb_text=hb, hb_meta=meta_hb)
    jobs = [{"id": c["id"], "build": (lambda c=c: mk(c))} for c in CASES[10:]]
    meta = {"extra": True, "variant": "time", "revision_tag": f"Revision {tag}", "handbook": meta_hb,
            "order": "alerts 11-30, serial, continuing m2-time"}
    path, out = run_serial("m2-time-ext", jobs, meta)
    first = json.load(open(os.path.join(RUNS, f"{DAY}-m2-time.json")))["calls"]
    report_set(["M2_changing_line", "EXTRA_time_30"], {"runs": ["runs/ep09/2026-10-05-m2-time.json", path],
                                                      **summarize(first + out["calls"])})


def m7(tag):
    """Coordinator M7: the thirty in schema mode against an EXPLICIT cache of SYSTEM + handbook (as m6-fixed), ttl 900 s."""
    global CAP
    CAP = min(CAP, spent() + 0.40)
    hb = handbook(tag); meta_hb = hb_meta(hb)
    body = {"model": f"models/{MODEL}", "systemInstruction": {"parts": [{"text": SYSTEM + "\n" + hb}]}, "ttl": "900s"}
    stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    status, r, err, secs = http("POST", "cachedContents", body)
    out = {"meta": {"revision_tag": f"Revision {tag}", "handbook": meta_hb, "mode": "triage.py schema mode (responseMimeType + SCHEMA), thinking low",
                    "systemInstruction_in_cache": "rules.SYSTEM + '\\n' + handbook (same text as m6-fixed)", "ttl": "900s",
                    "run_cap_usd": round(CAP, 6)},
           "create": {"request": redact(body, hb, meta_hb), "http": status, "sent_utc": stamp, "wall_s": secs, "response": r, "error": err},
           "calls": []}
    path = save("m7-explicit-scored", out)
    if status != 200:
        report_set(["M7_explicit_scored"], {"run": path, "create_http": status, "create_error": err}); return
    name = r["name"]; cu = r.get("usageMetadata", {}); n_cache = cu.get("totalTokenCount", 0)
    create_cost = n_cache * PRICE_IN / 1e6
    add_spend(create_cost)
    t_create = time.time()
    want = {c["id"]: c["want"] for c in CASES}
    try:
        for c in CASES:
            rec = generate(system_text=None, user_text=user_msg(c["alert"]), cached=name, schema=True)
            rec["id"] = c["id"]; out["calls"].append(rec); save("m7-explicit-scored", out)
            print(f"  {c['id']:28} http {rec['http']} prompt {rec.get('prompt')} cached {rec.get('cached')} {rec['wall_s']} s", flush=True)
    finally:
        st_del, r_del, err_del, _ = http("DELETE", name)
        lifetime = time.time() - t_create
        out["delete"] = {"http": st_del, "response": r_del, "error": err_del,
                         "at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        storage = n_cache * PRICE_STORAGE_H / 1e6 * lifetime / 3600
        add_spend(storage)
        out["storage"] = {"lifetime_s": round(lifetime, 1), "usd": storage}
        save("m7-explicit-scored", out)
    right, misses = 0, []
    for rec in out["calls"]:
        ok, got = score(rec.get("text", ""), want[rec["id"]])
        right += ok
        if not ok:
            misses.append([rec["id"], want[rec["id"]], got])
    s = summarize(out["calls"])
    calls_cost = s["cost_usd"]
    report_set(["M7_explicit_scored"], {"run": path, "revision_tag": f"Revision {tag}", "first_move_right": right, "of": len(CASES),
        "misses": misses, "create_http": status, "create_usageMetadata": cu, "createTime": r.get("createTime"),
        "expireTime": r.get("expireTime"), "create_cost_usd": round(create_cost, 6),
        "storage_arithmetic": f"{n_cache} tokens x $0.50 / 1M / hour x {lifetime:.1f} s / 3600 s = ${storage:.8f}",
        "storage_cost_usd": storage, "calls_cost_usd": calls_cost,
        "cost_incl_creation_and_storage_usd": round(calls_cost + create_cost + storage, 6),
        "delete": {"http": st_del, "error_body": err_del}, **s})


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    try:
        if cmd == "count":
            hb = handbook()
            print(json.dumps({"tokens": count_tokens(hb), "md5": md5(hb), "chars": len(hb)}))
        elif cmd == "m1":
            m1()
        elif cmd == "m2":
            m2(args[0], args[1])
        elif cmd == "m3":
            m3(args[0], args[1])
        elif cmd == "m4" and args[0] == "plain":
            m4_plain()
        elif cmd == "m4":
            m4_cut(int(args[1]), args[2])
        elif cmd == "m5":
            m5(args[0])
        elif cmd == "m4ext":
            m4_ext(int(args[0]), args[1], int(args[2]))
        elif cmd == "m4explicit":
            m4_explicit(int(args[0]), args[1])
        elif cmd == "m2fixext":
            m2_fix_ext(args[0])
        elif cmd == "m2timeext":
            m2_time_ext(args[0])
        elif cmd == "m7":
            m7(args[0])
        elif cmd == "m5min":
            m5_min()
        elif cmd == "m6":
            m6(args[0], args[1] if len(args) > 1 else None)
    except Stop as e:
        print(f"STOP: {e}")
        report_set(["STOPPED"], str(e))
        sys.exit(2)
    print(f"spend so far ${spent():.4f}")
