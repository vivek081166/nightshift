"""The model proposes a function call. Your code decides whether it runs.

    python3 tools.py payments-provider-timeout          # one alert from the thirty, by name
    python3 tools.py payments-provider-timeout --list   # the same, with the names it may use given as a list
    python3 tools.py --all                              # all thirty: what the check refused, and what came next
    python3 tools.py --all --list

Nothing real happens: the functions in sorrel/oncall.py return what a real one would.
"""
import json, os, sys, time, urllib.request

from sorrel.oncall import SERVICES, PROVIDERS, alert_service, deploys, run
from rules import SYSTEM

MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PRICE_IN, PRICE_OUT = 0.75, 3.75   # dollars per million tokens; thinking is billed as out
CASES = {c["id"]: c for c in json.load(open("tickets/incidents.json"))}
LIST = "--list" in sys.argv


def fn(name, description, **params):
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": params, "required": list(params)}}


service = {"type": "string", "enum": SERVICES} if LIST else {"type": "string"}
provider = {"type": "string", "enum": PROVIDERS} if LIST else {"type": "string"}
FUNCTIONS = [
    fn("read_logs", "Read one of our services' recent log lines.", service=service,
       minutes={"type": "integer", "description": "how far back to read, 1 to 60"}),
    fn("list_deploys", "List one of our services' recent deploys, newest first, with their ids.", service=service),
    fn("roll_back", "Undo one deploy of one of our services.", service=service,
       deploy_id={"type": "string", "description": "the id of the deploy to undo"}),
    fn("check_provider", "Check the status of an outside provider we depend on.", provider=provider),
    fn("page_owner", "Wake the person who owns one of our services.", service=service, reason={"type": "string"}),
    fn("no_action", "Write the alert down and take no action.", note={"type": "string"}),
]


def check(name, args, case):
    """None if the call may run, otherwise the reason it may not. Lookups need a real name; changes get checked harder."""
    if "service" in args and args["service"] not in SERVICES:
        return f"no service called {args['service']!r}; ours are {', '.join(SERVICES)}"
    if name == "check_provider" and args.get("provider") not in PROVIDERS:
        return f"no provider called {args.get('provider')!r}; ours are {', '.join(PROVIDERS)}"
    if name == "roll_back":
        if args["service"] != alert_service(case):
            return f"the alert is about {alert_service(case)}, not {args['service']}"
        deploy = {d["id"]: d for d in deploys(case, args["service"])}.get(args.get("deploy_id"))
        if deploy is None:
            return f"no deploy {args.get('deploy_id')!r} on {args['service']}; list_deploys shows the ids"
        if deploy["age_min"] > 60:
            return f"{deploy['id']} went out over an hour ago, too long to be the cause"
    return None


def call(contents):
    body = {"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents,
            "tools": [{"functionDeclarations": FUNCTIONS}],
            "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}
    req = urllib.request.Request(URL, json.dumps(body).encode(),
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                                  "content-type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def handle(case, show=print):
    """Send the alert, then run or refuse each call the model asks for, until it answers in words."""
    contents = [{"role": "user", "parts": [{"text": f"Alert:\n{case['alert']}\n"
                                                    "Make your first move by calling one of the functions."}]}]
    refused, n_in, n_out, calls = [], 0, 0, 0
    for _ in range(5):
        r = call(contents)
        calls += 1
        usage = r["usageMetadata"]
        n_in += usage["promptTokenCount"]
        n_out += usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
        turn = r["candidates"][0]["content"]
        asks = [p["functionCall"] for p in turn["parts"] if "functionCall" in p]
        if not asks:
            show("model  " + "".join(p.get("text", "") for p in turn["parts"]).strip())
            break
        contents.append(turn)   # send the model's answer back exactly as it came
        replies = []
        for a in asks:
            show(f"model  {a['name']}({', '.join(f'{k}={v!r}' for k, v in a['args'].items())})")
            why = check(a["name"], a["args"], case)
            result = {"refused": why} if why else run(a["name"], a["args"], case)
            show(f"code   refused: {why}" if why else f"code   ran: {result}")
            if why:
                refused.append((a["name"], a["args"]))
            reply = {"name": a["name"], "response": result}
            if a.get("id"):
                reply["id"] = a["id"]
            replies.append({"functionResponse": reply})
        contents.append({"role": "user", "parts": replies})
    return refused, n_in, n_out, calls


def cost_line(n_in, n_out, calls, secs):
    return (f"{MODEL} · {calls} calls · {n_in:,} in / {n_out:,} out · "
            f"${(n_in * PRICE_IN + n_out * PRICE_OUT) / 1e6:.4f} · {secs:.1f} s")


if __name__ == "__main__":
    t0 = time.time()
    if "--all" not in sys.argv:
        case = CASES[sys.argv[1]]
        print("alert  " + case["alert"])
        _, n_in, n_out, calls = handle(case)
        print(cost_line(n_in, n_out, calls, time.time() - t0))
        sys.exit()
    total, refusals = [0, 0, 0], 0
    for case in CASES.values():
        lines = []
        refused, i, o, c = handle(case, show=lines.append)
        total = [total[0] + i, total[1] + o, total[2] + c]
        if refused:
            refusals += len(refused)
            print(case["id"])
            print("\n".join("  " + line for line in lines[:-1]))   # every call and verdict, not the last words
    print(f"\nrefused {refusals}")
    print(cost_line(*total, time.time() - t0))
