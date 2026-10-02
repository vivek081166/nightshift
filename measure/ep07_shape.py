"""EP07 measurement: the thirty as a JSON triage record, every call saved to runs/ep07/.

    python3 measure/ep07_shape.py run loose-prompt|loose-json|loose-schema|prompt|json|schema [run]
    python3 measure/ep07_shape.py count [glob]          # counts from the saved runs, no API

loose = the request a developer would write: no key names, no allowed values.
prompt/json/schema = triage.py's tight prompt (field names + allowed values listed), as in runs/ep06.
Env: GEMINI_API_KEY. Stops on HTTP 402.
"""
import collections, datetime, glob, json, os, sys, time, urllib.error, urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from sorrel.oncall import SERVICES  # noqa: E402
from rules import SYSTEM, ACTIONS  # noqa: E402
from triage import SCHEMA, MODEL, URL, PRICE_IN, PRICE_OUT  # noqa: E402
FIELDS = "severity (P1, P2 or P3), service, first_move (one of: " + ", ".join(ACTIONS) + "), reason"  # the 09-29 tight prompt

CASES = json.load(open(os.path.join(ROOT, "tickets/incidents.json")))
LOOSE = "Reply in JSON with the severity, the service, the first move, and why."
ALLOWED = {"severity": ["P1", "P2", "P3"], "service": SERVICES, "first_move": ACTIONS}
OUT = os.path.join(ROOT, "runs/ep07")


def post(body, tag):
    req = urllib.request.Request(URL, json.dumps(body).encode(),
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                                  "content-type": "application/json"})
    rec = {"tag": tag, "model": MODEL, "think": "low", "request": body, "retries": 0,
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    for attempt in range(4):
        t0 = time.time()
        try:
            resp = urllib.request.urlopen(req, timeout=300)
            rec.update(status=resp.status, response=json.load(resp), latency_s=round(time.time() - t0, 2))
            return rec
        except urllib.error.HTTPError as e:
            rec.update(status=e.code, error=e.read().decode(errors="replace"), latency_s=round(time.time() - t0, 2))
            if e.code == 402:
                json.dump(rec, open(os.path.join(OUT, "402.json"), "w"), indent=1)
                sys.exit("HTTP 402: the prepaid Gemini balance is empty, top up before measuring more")
            if e.code in (429, 500, 503) and attempt < 3:
                rec["retries"] += 1
                time.sleep(5 * (attempt + 1))
                continue
            return rec
    return rec


def cost(rec):
    u = (rec.get("response") or {}).get("usageMetadata", {})
    return (u.get("promptTokenCount", 0) * PRICE_IN
            + (u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)) * PRICE_OUT) / 1e6


def body_for(mode, alert):
    ask = LOOSE if mode.startswith("loose") else f"Reply with a JSON object with these fields: {FIELDS}."
    cfg = {"thinkingConfig": {"thinkingLevel": "low"}}
    if mode not in ("prompt", "loose-prompt"):
        cfg["responseMimeType"] = "application/json"
    if mode.endswith("schema"):
        cfg["responseSchema"] = SCHEMA
    return {"systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": f"Alert:\n{alert}\n{ask}"}]}],
            "generationConfig": cfg}


def run(mode, n):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{datetime.date.today()}-shape-{mode}-run{n}.json")
    if os.path.exists(path):
        sys.exit(f"{path} exists: record once, never re-roll")
    out, spent, t0 = [], 0.0, time.time()
    for case in CASES:
        rec = post(body_for(mode, case["alert"]), f"shape/{mode}/{case['id']}")
        spent += cost(rec)
        out.append({"case": case["id"], "want": case["want"], "rec": rec})
        print(".", end="", flush=True)
    json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
    print(f"\nsaved {os.path.relpath(path, ROOT)} · 30 cases · ${spent:.4f} · {time.time() - t0:.0f} s")


def text_of(rec):
    try:
        return "".join(p.get("text", "") for p in rec["response"]["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        return None


def count(pattern):
    for path in sorted(glob.glob(os.path.join(OUT, pattern))):
        rows = json.load(open(path))
        c, keysets, offlist, spent = collections.Counter(), collections.Counter(), [], 0.0
        for k in ("parsed", "exact shape + allowed values", "triage['first_move'] KeyError", "first_move right"):
            c[k] = 0
        for row in rows:
            rec = row["rec"]
            spent += cost(rec)
            if rec.get("status") != 200:
                c[f"http {rec.get('status')}"] += 1
                continue
            raw = text_of(rec) or ""
            if raw.lstrip().startswith("```"):
                c["opens with backticks"] += 1
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                c["json.loads fails"] += 1
                continue
            c["parsed"] += 1
            if not isinstance(obj, dict):
                c["not an object"] += 1
                keysets[f"<{type(obj).__name__}>"] += 1
                c["triage['first_move'] raises"] += 1
                continue
            keysets[tuple(obj)] += 1
            if "first_move" not in obj:
                c["triage['first_move'] KeyError"] += 1
            if set(obj) == {"severity", "service", "first_move", "reason"} and all(
                    obj[k] in v for k, v in ALLOWED.items()):
                c["exact shape + allowed values"] += 1
            for k, allowed in ALLOWED.items():
                if k in obj and obj[k] not in allowed:
                    c[f"{k} off-list"] += 1
                    offlist.append((row["case"], k, obj[k]))
            if obj.get("first_move") == row["want"]:
                c["first_move right"] += 1
            for k, v in obj.items():   # values under other keys, e.g. firstMove, first move
                if k not in ALLOWED and k != "reason" and isinstance(v, str) and len(v) < 60:
                    offlist.append((row["case"], k, v))
        print(os.path.relpath(path, ROOT), f"${spent:.4f}")
        for k, v in sorted(c.items()):
            print(f"  {k:32} {v}")
        print("  distinct key sets:", len(keysets))
        for ks, v in keysets.most_common():
            print(f"    {v:2} x {list(ks) if isinstance(ks, tuple) else ks}")
        if offlist:
            print("  values outside the allowed lists / under other keys:")
            for case, k, v in offlist:
                print(f"    {case:26} {k!r}: {v!r}")


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "1")
    else:
        count(sys.argv[2] if len(sys.argv) > 2 else "*-shape-*.json")
