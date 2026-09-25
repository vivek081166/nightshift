"""Ask the model what caused the incident. The log comes in on stdin."""
import json, os, sys, time, urllib.error, urllib.request

MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PRICE_IN, PRICE_OUT = 0.75, 3.75   # dollars per million tokens; thinking is billed as out


def cost_line(usage, secs):
    n_in = usage["promptTokenCount"]
    think = usage.get("thoughtsTokenCount", 0)
    n_out = usage["candidatesTokenCount"] + think
    cost = (n_in * PRICE_IN + n_out * PRICE_OUT) / 1e6
    return (f"{MODEL} · {n_in:,} in / {n_out:,} out ({think:,} thinking)"
            f" · ${cost:.4f} · {secs:.1f} s")


ALERT = """payments-api: p95 latency 4.8 s for 6 min, error rate 0.9 %,
3 customer reports of failed checkout, last deploy 14 min ago."""
QUESTION = ("You are the on-call assistant. Alert:\n" + ALERT +
            "\nThe log:\n{log}\n"
            "What is the root cause? Reply in two lines: the cause, "
            "then the one log line that shows it, copied exactly.")

log = "\n".join(sys.stdin.read().splitlines())
body = {"contents": [{"parts": [{"text": QUESTION.format(log=log)}]}]}
headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
           "content-type": "application/json"}
req = urllib.request.Request(URL, json.dumps(body).encode(), headers)
t0 = time.time()
try:
    r = json.load(urllib.request.urlopen(req))
except urllib.error.HTTPError as e:
    error = json.load(e)["error"]
    print(f"HTTP {e.code} {error['status']}\n{error['message']}")
    print(f"{MODEL} · refused, no answer · {time.time() - t0:.1f} s")
    sys.exit(1)
parts = r["candidates"][0]["content"]["parts"]
print("".join(p["text"] for p in parts).strip())
print(cost_line(r["usageMetadata"], time.time() - t0))
