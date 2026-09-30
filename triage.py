"""Ask for an alert's triage as JSON: the severity, the service, the first move and why.

    python3 triage.py                  # JSON asked for in the prompt, nothing else
    python3 triage.py json             # JSON mode: the answer is JSON and only JSON
    python3 triage.py schema           # JSON mode and the shape: the fields, and the values each may take
    python3 triage.py schema --all     # all thirty: how many parse, and how many are the move you wanted
"""
import json, os, sys, time, urllib.request

from sorrel.oncall import SERVICES
from rules import SYSTEM, ACTIONS

MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PRICE_IN, PRICE_OUT = 0.75, 3.75   # dollars per million tokens; thinking is billed as out
CASES = json.load(open("tickets/incidents.json"))

FIELDS = "severity (P1, P2 or P3), service, first_move (one of: " + ", ".join(ACTIONS) + "), reason"
SCHEMA = {"type": "object", "properties": {
    "severity": {"type": "string", "enum": ["P1", "P2", "P3"]},
    "service": {"type": "string", "enum": SERVICES},
    "first_move": {"type": "string", "enum": ACTIONS},
    "reason": {"type": "string"}},
    "required": ["severity", "service", "first_move", "reason"]}


def ask(alert, mode):
    config = {"thinkingConfig": {"thinkingLevel": "low"}}
    if mode in ("json", "schema"):
        config["responseMimeType"] = "application/json"   # JSON and nothing around it
    if mode == "schema":
        config["responseSchema"] = SCHEMA                  # and in this shape
    body = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text":
                f"Alert:\n{alert}\nReply with a JSON object with these fields: {FIELDS}."}]}],
            "generationConfig": config}
    req = urllib.request.Request(URL, json.dumps(body).encode(),
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                                  "content-type": "application/json"})
    r = json.load(urllib.request.urlopen(req))
    usage = r["usageMetadata"]
    n_out = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
    return "".join(p["text"] for p in r["candidates"][0]["content"]["parts"]), usage["promptTokenCount"], n_out


def cost_line(n_in, n_out, secs):
    return f"{MODEL} · {n_in:,} in / {n_out:,} out · ${(n_in * PRICE_IN + n_out * PRICE_OUT) / 1e6:.4f} · {secs:.1f} s"


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "--all" else "prompt"
    t0 = time.time()
    if "--all" not in sys.argv:
        text, n_in, n_out = ask(CASES[0]["alert"], mode)
        print(text)
        print(cost_line(n_in, n_out, time.time() - t0))
        print(json.loads(text))
        sys.exit()
    parsed, right, n_in, n_out = 0, 0, 0, 0
    for case in CASES:
        text, i, o = ask(case["alert"], mode)
        n_in, n_out = n_in + i, n_out + o
        try:
            triage = json.loads(text)
        except json.JSONDecodeError:
            continue
        parsed += 1
        if triage.get("first_move") == case["want"]:
            right += 1
        else:
            print(f"  {case['id']:26} wanted {case['want']:15} got {triage.get('first_move')}")
    print(f"\nparsed {parsed} / {len(CASES)} · first move right {right} / {len(CASES)}")
    print(cost_line(n_in, n_out, time.time() - t0))
