"""Ask for an action plan as JSON, with a limit on how long the answer may run.

    python3 plan.py            # no limit
    python3 plan.py 256        # at most 256 output tokens
"""
import json, os, sys, urllib.request

MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
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

if __name__ == "__main__":
    body = {"contents": [{"parts": [{"text": PROMPT}]}], "generationConfig": config}
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
               "content-type": "application/json"}
    req = urllib.request.Request(URL, json.dumps(body).encode(), headers)
    r = json.load(urllib.request.urlopen(req))
    print(r["candidates"][0]["finishReason"], r["usageMetadata"])
    text = "".join(p["text"] for p in r["candidates"][0]["content"]["parts"])
    plan = json.loads(text)
    print(json.dumps(plan, indent=2))
