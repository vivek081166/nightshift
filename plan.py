"""Ask for an action plan as JSON, with a limit on how long the answer may run.

    python3 plan.py            # no limit
    python3 plan.py 256        # at most 256 output tokens
    python3 plan.py 128 low    # at most 128, and think less
"""
import json, os, sys, time, urllib.request

MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PRICE_IN, PRICE_OUT = 0.75, 3.75   # dollars per million tokens; thinking is billed as out
ACTIONS = ["roll back", "read logs", "check provider", "page owner", "no action"]

ALERT = """payments-api: p95 latency 4.8 s for 6 min, error rate 0.9 %,
3 customer reports of failed checkout, last deploy 14 min ago."""
PROMPT = ("You are the on-call assistant. Alert:\n" + ALERT +
          "\nWrite the action plan: the severity, the service, the first move, "
          "then the steps to take in order, each one short.")

SCHEMA = {"type": "object", "properties": {
    "severity": {"type": "string", "enum": ["P1", "P2", "P3"]},
    "service": {"type": "string"},
    "first_move": {"type": "string", "enum": ACTIONS},
    "steps": {"type": "array", "items": {"type": "string"}}},
    "required": ["severity", "service", "first_move", "steps"]}

config = {"responseMimeType": "application/json", "responseSchema": SCHEMA}
if len(sys.argv) > 1:
    config["maxOutputTokens"] = int(sys.argv[1])
if len(sys.argv) > 2:
    config["thinkingConfig"] = {"thinkingLevel": sys.argv[2]}


def cost_line(usage, secs):
    think = usage.get("thoughtsTokenCount", 0)
    n_in, n_out = usage["promptTokenCount"], usage.get("candidatesTokenCount", 0) + think
    cost = (n_in * PRICE_IN + n_out * PRICE_OUT) / 1e6
    return f"{MODEL} · {n_in:,} in / {n_out:,} out ({think:,} thinking) · ${cost:.4f} · {secs:.1f} s"


if __name__ == "__main__":
    body = {"contents": [{"parts": [{"text": PROMPT}]}], "generationConfig": config}
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
               "content-type": "application/json"}
    req = urllib.request.Request(URL, json.dumps(body).encode(), headers)
    t0 = time.time()
    resp = urllib.request.urlopen(req)
    r = json.load(resp)
    finish = r["candidates"][0]["finishReason"]
    print("HTTP", resp.status, "· finishReason", finish)
    print(cost_line(r["usageMetadata"], time.time() - t0))
    if finish != "STOP":   # HTTP 200 only means the call went through, not that the answer is whole
        sys.exit(f"stopped: finishReason is {finish}, not STOP, so this answer is not complete")
    text = "".join(p["text"] for p in r["candidates"][0]["content"]["parts"])
    print(text)
    plan = json.loads(text)
    print(json.dumps(plan, indent=2))
