import json, os, re, time, urllib.request
from collections import Counter

ALERT = """payments-api: p95 latency 4.8 s for 6 min, error rate 0.9 %,
3 customer reports of failed checkout, last deploy 14 min ago."""
PROMPT = f"""You are the on-call assistant. Alert:
{ALERT}
Reply in one line: P1 or P2, then the first action."""

MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PRICE_IN, PRICE_OUT = 0.75, 3.75    # dollars per million tokens


def ask(prompt):
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                 "content-type": "application/json"},
    )
    r = json.load(urllib.request.urlopen(req))
    text = "".join(p["text"] for p in r["candidates"][0]["content"]["parts"])
    usage = r["usageMetadata"]
    tokens_out = usage["candidatesTokenCount"] + usage.get("thoughtsTokenCount", 0)
    return text, usage["promptTokenCount"], tokens_out


tally, tokens_in, tokens_out, t0 = Counter(), 0, 0, time.time()
for _ in range(10):
    text, n_in, n_out = ask(PROMPT)
    severity = re.search(r"P[123]", text)
    tally[severity.group() if severity else "?"] += 1
    tokens_in, tokens_out = tokens_in + n_in, tokens_out + n_out
    print(text.strip().splitlines()[0])

cost = (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1e6
print(f"{MODEL}: {dict(tally)} · {tokens_in} in / {tokens_out} out"
      f" · ${cost:.4f} · {time.time() - t0:.1f} s")
