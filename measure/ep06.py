"""EP06 measurement: structured output and tool calls, every call saved to runs/ep06/.

    python3 measure/ep06.py shape prompt|json|schema [run]     # the thirty as a JSON triage record
    python3 measure/ep06.py calls enum|free AUTO|ANY|VALIDATED [run]   # the first call the model proposes
    python3 measure/ep06.py loop enum AUTO [run]               # the full loop, with the check deciding
    python3 measure/ep06.py sig                                # the second turn sent without the thought signature

Env: GEMINI_API_KEY. THINK=low|default (default low). CASES=id,id to run a subset. Stops on HTTP 402.
"""
import datetime, json, os, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorrel.oncall import SERVICES, PROVIDERS, alert_service, deploys, run  # noqa: E402

MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PRICE_IN, PRICE_OUT = 0.75, 3.75
THINK = os.environ.get("THINK", "low")
ACTIONS = ["roll back", "read logs", "check provider", "page owner", "no action"]
ROOT = os.path.join(os.path.dirname(__file__), "..")
CASES = json.load(open(os.path.join(ROOT, "tickets/incidents.json")))
if os.environ.get("CASES"):
    keep = os.environ["CASES"].split(",")
    CASES = [c for c in CASES if c["id"] in keep]

# score.py's RULES with the page owner line narrowed (EP05's end state)
RULES = """At this company the five actions mean:
- roll back: undo the most recent deploy, when that deploy is recent enough to be the cause.
- read logs: go and read the service's own output, when nobody knows yet what happened.
- check provider: look at an outside service we depend on, when the alert already points at one.
- page owner: wake the person who owns this service, when something has already happened that you cannot undo - data seen, money moved, accounts deleted - or when somebody has to make a decision you are not allowed to make.
- no action: write it down and move on, when nothing has failed and no customer is affected.
"""
SYSTEM = ("You are the on-call assistant for Sorrel, a scheduling app with four services: "
          "web, api, payments and notifier.\n" + RULES)


def post(body, tag):
    """One call, with the whole exchange kept. Retries 429/500/503 up to 3 times."""
    req = urllib.request.Request(URL, json.dumps(body).encode(),
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                                  "content-type": "application/json"})
    rec = {"tag": tag, "model": MODEL, "think": THINK, "request": body, "retries": 0,
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    for attempt in range(4):
        t0 = time.time()
        try:
            resp = urllib.request.urlopen(req, timeout=300)
            rec.update(status=resp.status, response=json.load(resp), latency_s=round(time.time() - t0, 2))
            return rec
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")
            rec.update(status=e.code, error=err, latency_s=round(time.time() - t0, 2))
            if e.code == 402:
                save_partial(rec)
                sys.exit("HTTP 402: the prepaid Gemini balance is empty, top up before measuring more")
            if e.code in (429, 500, 503) and attempt < 3:
                rec["retries"] += 1
                time.sleep(5 * (attempt + 1))
                continue
            return rec
    return rec


def save_partial(rec):
    with open(os.path.join(ROOT, "runs/ep06/402.json"), "w") as f:
        json.dump(rec, f, indent=1)


def gen_config(extra=None):
    cfg = {} if THINK == "default" else {"thinkingConfig": {"thinkingLevel": THINK}}
    cfg.update(extra or {})
    return cfg


def cost(rec):
    u = (rec.get("response") or {}).get("usageMetadata", {})
    n_in = u.get("promptTokenCount", 0)
    n_out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    return (n_in * PRICE_IN + n_out * PRICE_OUT) / 1e6


# ---- block: shape (structured output three ways) ----
TRIAGE_FIELDS = "severity (P1, P2 or P3), service, first_move (one of: " + ", ".join(ACTIONS) + "), reason"
TRIAGE_SCHEMA = {"type": "object", "properties": {
    "severity": {"type": "string", "enum": ["P1", "P2", "P3"]},
    "service": {"type": "string", "enum": SERVICES},
    "first_move": {"type": "string", "enum": ACTIONS},
    "reason": {"type": "string"}},
    "required": ["severity", "service", "first_move", "reason"]}


def shape(mode, case):
    text = (f"Alert:\n{case['alert']}\nReply with a JSON object with these fields: {TRIAGE_FIELDS}.")
    extra = {}
    if mode in ("json", "schema"):
        extra["responseMimeType"] = "application/json"
    if mode == "schema":
        extra["responseSchema"] = TRIAGE_SCHEMA
    body = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": gen_config(extra)}
    return post(body, f"shape/{mode}/{case['id']}")


# ---- block: calls (the first proposed function call) ----
def tools(variant):
    s = {"type": "string", "enum": SERVICES} if variant == "enum" else {"type": "string"}
    p = {"type": "string", "enum": PROVIDERS} if variant == "enum" else {"type": "string"}

    def fn(name, desc, **props):
        return {"name": name, "description": desc,
                "parameters": {"type": "object", "properties": props, "required": list(props)}}
    return [{"functionDeclarations": [
        fn("read_logs", "Read one of our services' recent log lines.", service=s,
           minutes={"type": "integer", "description": "how far back to read, 1 to 60"}),
        fn("list_deploys", "List one of our services' recent deploys, newest first, with their ids.", service=s),
        fn("roll_back", "Undo one deploy of one of our services.", service=s,
           deploy_id={"type": "string", "description": "the id of the deploy to undo"}),
        fn("check_provider", "Check the status of an outside provider we depend on.", provider=p),
        fn("page_owner", "Wake the person who owns one of our services.", service=s,
           reason={"type": "string"}),
        fn("no_action", "Write the alert down and take no action.", note={"type": "string"}),
    ]}]


def first_turn(case):
    return [{"role": "user", "parts": [{"text": f"Alert:\n{case['alert']}\n"
                                                "Make your first move by calling one of the functions."}]}]


def call_body(contents, variant, mode):
    body = {"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents,
            "tools": tools(variant), "generationConfig": gen_config()}
    if mode != "AUTO":
        body["toolConfig"] = {"functionCallingConfig": {"mode": mode}}
    return body


def calls(variant, mode, case):
    return post(call_body(first_turn(case), variant, mode), f"calls/{variant}/{mode}/{case['id']}")


def proposed(rec):
    """The function calls in a response, as (name, args)."""
    try:
        parts = rec["response"]["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return []
    return [(p["functionCall"]["name"], p["functionCall"].get("args", {})) for p in parts if "functionCall" in p]


def call_ids(rec):
    parts = rec["response"]["candidates"][0]["content"]["parts"]
    return [p["functionCall"].get("id") for p in parts if "functionCall" in p]


def reply(name, cid, result):
    fr = {"name": name, "response": result}
    if cid:
        fr["id"] = cid
    return {"functionResponse": fr}


# ---- the check: your code decides ----
def check(name, args, case):
    """None if the call may run, else the reason it may not."""
    if "service" in args:
        svc = args["service"]
        if svc not in SERVICES:
            return f"no service called {svc!r}; ours are {', '.join(SERVICES)}"
        if svc != alert_service(case) and name in ("roll_back", "read_logs", "page_owner"):
            return f"the alert is about {alert_service(case)}, not {svc}"
    if name == "check_provider" and args.get("provider") not in PROVIDERS:
        return f"no provider called {args.get('provider')!r}; ours are {', '.join(PROVIDERS)}"
    if name == "read_logs":
        m = args.get("minutes")
        if not isinstance(m, (int, float)) or not 1 <= m <= 60:
            return f"minutes must be 1 to 60, got {m!r}"
    if name == "roll_back":
        known = {d["id"]: d for d in deploys(case, args.get("service"))}
        d = known.get(args.get("deploy_id"))
        if d is None:
            return f"no deploy {args.get('deploy_id')!r} on {args.get('service')}; list_deploys shows the ids"
        if d["age_min"] > 60:
            return f"deploy {d['id']} is over an hour old, too old to be the cause"
    return None


def loop(variant, mode, case, steps=5):
    contents, trace, recs = first_turn(case), [], []
    for _ in range(steps):
        rec = post(call_body(contents, variant, mode), f"loop/{variant}/{mode}/{case['id']}")
        recs.append(rec)
        if rec.get("status") != 200:
            break
        cand = rec["response"]["candidates"][0]
        calls_ = proposed(rec)
        if not calls_:
            trace.append({"text": "".join(p.get("text", "") for p in cand["content"].get("parts", []))})
            break
        contents.append(cand["content"])   # the model's turn exactly as sent, thought signatures included
        replies = []
        for (name, args), cid in zip(calls_, call_ids(rec)):
            why = check(name, args, case)
            result = {"refused": why} if why else run(name, args, case)
            trace.append({"call": name, "args": args, "refused": why, "result": result})
            replies.append(reply(name, cid, result))
        contents.append({"role": "user", "parts": replies})
    return {"case": case["id"], "want": case["want"], "trace": trace, "calls": recs}


def sig():
    """Second turn with the thought signature stripped from the model's echoed turn."""
    case = next(c for c in CASES if c["id"] == "payments-latency") if any(
        c["id"] == "payments-latency" for c in CASES) else CASES[0]
    contents = first_turn(case)
    first = post(call_body(contents, "enum", "AUTO"), f"sig/first/{case['id']}")
    out = {"first": first}
    if first.get("status") == 200 and proposed(first):
        content = json.loads(json.dumps(first["response"]["candidates"][0]["content"]))
        had = sum("thoughtSignature" in p for p in content["parts"])
        for p in content["parts"]:
            p.pop("thoughtSignature", None)
        replies = [reply(n, cid, run(n, a, case)) for (n, a), cid in zip(proposed(first), call_ids(first))]
        contents += [content, {"role": "user", "parts": replies}]
        out["signatures_stripped"] = had
        out["second"] = post(call_body(contents, "enum", "AUTO"), f"sig/second/{case['id']}")
    return out


def main():
    block = sys.argv[1]
    stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    if block == "sig":
        out = sig()
        path = f"runs/ep06/{stamp}-sig-think-{THINK}.json"
        spent = cost(out["first"]) + cost(out.get("second", {}))
        s2 = out.get("second", {})
        print("stripped", out.get("signatures_stripped"), "· second call HTTP", s2.get("status"),
              (s2.get("error") or "")[:300])
    else:
        args = sys.argv[2:4] if block != "shape" else sys.argv[2:3] + [None]
        a, b = args
        rest = sys.argv[4:] if block != "shape" else sys.argv[3:]
        n = rest[0] if rest else "1"
        name = "-".join(x for x in (block, a, b) if x)
        path = f"runs/ep06/{stamp}-{name}-think-{THINK}-run{n}.json"
        out, spent, t0 = [], 0.0, time.time()
        for case in CASES:
            if block == "shape":
                r = shape(a, case)
                spent += cost(r)
            elif block == "calls":
                r = calls(a, b, case)
                spent += cost(r)
            else:
                r = loop(a, b, case)
                spent += sum(cost(x) for x in r["calls"])
            out.append({"case": case["id"], "want": case["want"], **({"rec": r} if block != "loop" else r)})
            print(".", end="", flush=True)
        print(f"\n{len(out)} cases · ${spent:.4f} · {time.time() - t0:.0f} s")
    with open(os.path.join(ROOT, path), "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("saved", path, f"${spent:.4f}")


if __name__ == "__main__":
    main()
